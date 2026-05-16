from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

os.environ["LANGGRAPH_FAST_API"] = "true"

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder

from src.container import get_queue, get_rate_limiter, get_settings, init_container
from src.core.log import bind_context, clear_context, configure_logging, get_logger
from src.graph_builder import create_agent, get_checkpointer, graph as agent_graph

logger = get_logger("api")


class ThreadCreate(BaseModel):
    thread_id: Optional[str] = None
    metadata: Optional[dict] = None


class ThreadResponse(BaseModel):
    thread_id: str
    metadata: dict = {}


class ThreadStateUpdate(BaseModel):
    messages: list[dict]
    """List of AG-UI messages to append to thread state."""


AGUI_ROLE_MAP: dict[str, type] = {}


def _get_agui_message_class(role: str):
    global AGUI_ROLE_MAP
    if not AGUI_ROLE_MAP:
        from ag_ui.core import (
            AssistantMessage,
            SystemMessage,
            ToolMessage,
            UserMessage,
        )

        AGUI_ROLE_MAP = {
            "user": UserMessage,
            "assistant": AssistantMessage,
            "system": SystemMessage,
            "tool": ToolMessage,
        }
    cls = AGUI_ROLE_MAP.get(role)
    if cls is None:
        raise ValueError(f"Unknown AG-UI message role: {role}")
    return cls


_threads: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_container()
    settings = get_settings()

    agents = _build_agents()

    logger.info(
        "server_startup",
        backend=settings.queue_backend,
        agent=settings.agent_name,
    )

    if settings.queue_backend == "inprocess":
        queue = get_queue()
        await queue.start_worker(agents)

    yield

    logger.info("server_shutdown")
    await get_queue().shutdown()


def _build_agents() -> dict:
    settings = get_settings()
    agent = create_agent(name=settings.agent_name, description=settings.agent_description)
    return {settings.agent_name: agent}


def create_app() -> FastAPI:
    from src.core.config import settings as default_settings

    configure_logging(
        level=default_settings.log_level,
        json_format=default_settings.log_json,
        service=default_settings.log_service,
    )

    app = FastAPI(
        title=default_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        logger.info("request_start")
        try:
            response = await call_next(request)
            logger.info("request_end", status_code=response.status_code)
            return response
        except Exception:
            logger.exception("request_error")
            raise
        finally:
            clear_context()

    @app.post("/agent")
    async def agent_endpoint(input_data: RunAgentInput, request: Request):
        rate_limiter = get_rate_limiter()
        queue = get_queue()

        client_ip = request.client.host if request.client else "unknown"
        user_id = input_data.thread_id or client_ip

        bind_context(
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
            user_id=user_id,
        )

        result = await rate_limiter.check(user_id)
        if not result.allowed:
            logger.warning(
                "rate_limit_exceeded",
                user_id=user_id,
                retry_after=result.retry_after,
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "retry_after": result.retry_after,
                },
            )

        run_id = await queue.publish(
            get_settings().agent_name, input_data
        )
        encoder = EventEncoder(
            accept=request.headers.get("accept", "text/event-stream")
        )

        logger.info(
            "agent_request_queued",
            run_id=run_id,
            agent=get_settings().agent_name,
        )

        async def event_generator():
            try:
                async for event in queue.subscribe(run_id):
                    yield encoder.encode(event)
            except Exception:
                logger.exception("sse_stream_error")
                raise

        return StreamingResponse(
            event_generator(),
            media_type=encoder.get_content_type(),
        )

    @app.get("/agent/health")
    async def agent_health():
        return {
            "status": "ok",
            "agent": {"name": get_settings().agent_name},
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": get_settings().app_name}

    @app.get("/agents")
    async def list_agents():
        return {
            "agents": [
                {
                    "name": get_settings().agent_name,
                    "endpoint": "/agent",
                }
            ]
        }

    @app.post("/threads", response_model=ThreadResponse)
    async def create_thread(body: ThreadCreate):
        tid = body.thread_id or str(uuid.uuid4())
        _threads[tid] = {"thread_id": tid, "metadata": body.metadata or {}}

        # Initialize checkpointer state so GET .../state has a record
        config = {"configurable": {"thread_id": tid}}
        try:
            await agent_graph.aupdate_state(
                config, {"messages": []}, as_node="agent"
            )
        except Exception:
            logger.info(
                "create_thread_checkpointer_skip",
                thread_id=tid,
            )

        logger.info("thread_created", thread_id=tid)
        return _threads[tid]

    @app.get("/threads")
    async def list_threads():
        return {"threads": list(_threads.values())}

    @app.get("/threads/{thread_id}")
    async def get_thread(thread_id: str):
        thread = _threads.get(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread

    @app.get("/threads/{thread_id}/state/history")
    async def get_thread_state_history(thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        from ag_ui_langgraph.utils import langchain_messages_to_agui

        entries = []
        try:
            async for snapshot in agent_graph.aget_state_history(config):
                messages = langchain_messages_to_agui(
                    snapshot.values.get("messages", []) if snapshot.values else []
                )
                entries.append(
                    {
                        "checkpoint_id": snapshot.config["configurable"].get(
                            "checkpoint_id"
                        )
                        if snapshot.config and snapshot.config.get("configurable")
                        else None,
                        "message_count": len(messages),
                        "next": list(snapshot.next) if snapshot.next else [],
                    }
                )
        except Exception:
            logger.exception("get_thread_state_history_error", thread_id=thread_id)
            raise HTTPException(
                status_code=500, detail="Failed to read state history"
            )

        return {"thread_id": thread_id, "checkpoints": entries}

    @app.delete("/threads/{thread_id}")
    async def delete_thread(thread_id: str):
        _threads.pop(thread_id, None)
        # Clear checkpointer state
        try:
            await get_checkpointer().adelete_thread(thread_id)
        except Exception:
            logger.exception("delete_thread_checkpointer_error", thread_id=thread_id)
        logger.info("thread_deleted", thread_id=thread_id)
        return {"status": "deleted", "thread_id": thread_id}

    @app.get("/threads/{thread_id}/state")
    async def get_thread_state(thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await agent_graph.aget_state(config)
        except Exception:
            logger.exception("get_thread_state_error", thread_id=thread_id)
            raise HTTPException(status_code=500, detail="Failed to read thread state")

        if state.values is None:
            logger.info("get_thread_state_empty", thread_id=thread_id)
            return {"thread_id": thread_id, "messages": []}

        from ag_ui_langgraph.utils import langchain_messages_to_agui

        raw = state.values.get("messages", [])
        logger.info(
            "get_thread_state_found",
            thread_id=thread_id,
            message_count=len(raw),
        )
        messages = langchain_messages_to_agui(raw)
        return {"thread_id": thread_id, "messages": messages}

    @app.put("/threads/{thread_id}/state")
    async def update_thread_state(thread_id: str, body: ThreadStateUpdate):
        from ag_ui_langgraph.utils import agui_messages_to_langchain

        agui_messages = [
            _get_agui_message_class(m["role"])(**m) for m in body.messages
        ]
        langchain_messages = agui_messages_to_langchain(agui_messages)
        config = {"configurable": {"thread_id": thread_id}}

        try:
            # as_node="agent" is required for LangGraph checkpointer
            # to disambiguate which node produced the update
            await agent_graph.aupdate_state(
                config, {"messages": langchain_messages}, as_node="agent"
            )
        except Exception:
            logger.exception("update_thread_state_error", thread_id=thread_id)
            raise HTTPException(status_code=500, detail="Failed to save thread state")

        state = await agent_graph.aget_state(config)
        raw = state.values.get("messages", []) if state.values else []

        if state.values is None:
            logger.warning("update_thread_state_no_values", thread_id=thread_id)
            return {"thread_id": thread_id, "messages": []}

        from ag_ui_langgraph.utils import langchain_messages_to_agui

        return {
            "thread_id": thread_id,
            "messages": langchain_messages_to_agui(raw),
        }

    return app


app = create_app()
