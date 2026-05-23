from __future__ import annotations

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

os.environ["LANGGRAPH_FAST_API"] = "true"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from dependency_injector.wiring import Provide, inject

from src.api.schemas import UpdateStateRequest, ForkThreadRequest
from src.container import ApplicationContainer, get_container, init_container
from src.core.log import configure_logging, get_logger

logger = get_logger("api")


def _to_agui_message(data: dict):
    role = data.get("role", "")
    if role == "user":
        from ag_ui.core.types import UserMessage
        return UserMessage(**data)
    elif role == "assistant":
        from ag_ui.core.types import AssistantMessage
        return AssistantMessage(**data)
    elif role == "tool":
        from ag_ui.core.types import ToolMessage
        return ToolMessage(**data)
    elif role == "system":
        from ag_ui.core.types import SystemMessage
        return SystemMessage(**data)
    raise HTTPException(status_code=400, detail=f"Unsupported message role: {role}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_container()
    c = get_container()

    logger.info(
        "server_startup",
        agent=c.settings().agent_name,
    )

    try:
        pool = c.db_pool()
        if pool is not None and pool.closed:
            if sys.platform == "win32":
                loop = asyncio.get_running_loop()
                if isinstance(loop, asyncio.ProactorEventLoop):
                    raise RuntimeError(
                        "psycopg requires SelectorEventLoop on Windows. "
                        "Run via 'python main.py' instead of uvicorn/gunicorn directly."
                    )
            await pool.open()
            checkpointer = c.checkpointer()
            await checkpointer.setup()
    except Exception:
        logger.warning("db_checkpointer_setup_failed", exc_info=True)

    yield

    logger.info("server_shutdown")
    await c.queue().shutdown()


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
        method = request.method
        path = request.url.path
        logger.info("request_start", request_id=request_id, method=method, path=path)
        try:
            response = await call_next(request)
            logger.info(
                "request_end",
                request_id=request_id,
                method=method,
                path=path,
                status_code=response.status_code,
            )
            return response
        except Exception:
            logger.exception("request_error", request_id=request_id, method=method, path=path)
            raise

    @app.post("/agent")
    @inject
    async def agent_endpoint(
        input_data: RunAgentInput,
        request: Request,
        rate_limiter = Provide[ApplicationContainer.rate_limiter],
        queue = Provide[ApplicationContainer.queue],
        settings = Provide[ApplicationContainer.settings],
    ):
        user_id = request.headers.get("X-User-Id", "anonymous")

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

        run_id = await queue.publish(settings.agent_name, input_data)
        encoder = EventEncoder(
            accept=request.headers.get("accept", "text/event-stream")
        )

        logger.info(
            "agent_request_queued",
            run_id=run_id,
            agent=settings.agent_name,
            user_id=user_id,
            thread_id=input_data.thread_id,
        )

        async def event_generator():
            try:
                async for event in queue.subscribe(run_id):
                    yield encoder.encode(event)
            except Exception:
                logger.exception("sse_stream_error", run_id=run_id)
                raise

        return StreamingResponse(
            event_generator(),
            media_type=encoder.get_content_type(),
        )

    @app.get("/agent/health")
    @inject
    async def agent_health(settings = Provide[ApplicationContainer.settings]):
        return {
            "status": "ok",
            "agent": {"name": settings.agent_name},
        }

    @app.get("/health")
    @inject
    async def health(settings = Provide[ApplicationContainer.settings]):
        return {"status": "ok", "service": settings.app_name}

    @app.get("/agents")
    @inject
    async def list_agents(settings = Provide[ApplicationContainer.settings]):
        return {
            "agents": [
                {
                    "name": settings.agent_name,
                    "endpoint": "/agent",
                }
            ]
        }

    @app.get("/threads/{thread_id}/state/history")
    @inject
    async def get_thread_state_history(thread_id: str, graph = Provide[ApplicationContainer.graph]):
        config = {"configurable": {"thread_id": thread_id}}
        from ag_ui_langgraph.utils import langchain_messages_to_agui

        entries = []
        try:
            async for snapshot in graph.aget_state_history(config):
                agui_messages = (
                    langchain_messages_to_agui(
                        snapshot.values.get("messages", [])
                    )
                    if snapshot.values
                    else []
                )
                entries.append(
                    {
                        "checkpoint_id": snapshot.config["configurable"].get(
                            "checkpoint_id"
                        )
                        if snapshot.config and snapshot.config.get("configurable")
                        else None,
                        "message_count": len(agui_messages),
                        "messages": agui_messages,
                        "next": list(snapshot.next) if snapshot.next else [],
                    }
                )
        except Exception:
            logger.exception(
                "get_thread_state_history_error", thread_id=thread_id
            )
            raise HTTPException(
                status_code=500, detail="Failed to read state history"
            )

        return {"thread_id": thread_id, "checkpoints": entries}

    @app.get("/threads/{thread_id}/state")
    @inject
    async def get_thread_state(thread_id: str, graph = Provide[ApplicationContainer.graph]):
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await graph.aget_state(config)
        except Exception:
            logger.exception("get_thread_state_error", thread_id=thread_id)
            raise HTTPException(
                status_code=500, detail="Failed to read thread state"
            )

        if state.values is None:
            logger.info("get_thread_state_empty", thread_id=thread_id)
            return {"thread_id": thread_id, "messages": []}

        from ag_ui_langgraph.utils import langchain_messages_to_agui
        from langchain_core.messages.modifier import RemoveMessage

        raw = state.values.get("messages", [])
        clean = [m for m in raw if not isinstance(m, RemoveMessage)]
        messages = langchain_messages_to_agui(clean)
        checkpoint_id = (
            state.config.get("configurable", {}).get("checkpoint_id")
            if state.config else None
        )
        return {"thread_id": thread_id, "checkpoint_id": checkpoint_id, "messages": messages}

    @app.patch("/threads/{thread_id}/state")
    @inject
    async def update_thread_state(
        thread_id: str,
        body: UpdateStateRequest,
        graph = Provide[ApplicationContainer.graph],
    ):
        if not body.messages:
            raise HTTPException(status_code=400, detail="messages required")

        from ag_ui_langgraph.utils import agui_messages_to_langchain, langchain_messages_to_agui
        from langchain_core.messages.modifier import RemoveMessage

        agui_objects = [_to_agui_message(m) for m in body.messages]
        lc_messages = agui_messages_to_langchain(agui_objects)
        edited_ids = {getattr(m, "id", None) for m in lc_messages}

        # Load the *latest* checkpoint of this thread.
        latest_config = {"configurable": {"thread_id": thread_id}}
        latest_snap = await graph.aget_state(latest_config)
        current = list(latest_snap.values.get("messages", [])) if latest_snap.values else []

        # Find the last position of any edited message in the current list.
        last_edited_idx = -1
        for idx, m in enumerate(current):
            if getattr(m, "id", None) in edited_ids:
                last_edited_idx = idx

        if last_edited_idx == -1:
            raise HTTPException(
                status_code=404,
                detail="Edited message not found in the latest thread state",
            )

        # Build clean message list: keep before edit, replace edited, drop rest.
        new_msgs = []
        for m in current[:last_edited_idx + 1]:
            mid = getattr(m, "id", None)
            if mid in edited_ids:
                for em in lc_messages:
                    if getattr(em, "id", None) == mid:
                        new_msgs.append(em)
                        break
            else:
                new_msgs.append(m)

        # Write via aupdate_state — cleanest approach, no RemoveMessage artifacts
        await graph.aupdate_state(latest_config, {"messages": new_msgs})

        # Read back, filter any leftover RemoveMessage artifacts from prior corruptions
        # (can happen when tool messages had id=None on this thread).
        new_state = await graph.aget_state(latest_config)
        raw = list(new_state.values.get("messages", [])) if new_state.values else []
        raw = [m for m in raw if not isinstance(m, RemoveMessage)]
        checkpoint_id = (
            new_state.config.get("configurable", {}).get("checkpoint_id")
            if new_state.config else None
        )
        agui_msgs = langchain_messages_to_agui(raw)

        return {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "messages": agui_msgs,
        }

    @app.post("/threads/{thread_id}/fork")
    @inject
    async def fork_thread(
        thread_id: str,
        body: ForkThreadRequest,
        graph = Provide[ApplicationContainer.graph],
    ):
        source_config = {"configurable": {"thread_id": thread_id}}
        if body.source_checkpoint_id:
            source_config["configurable"]["checkpoint_id"] = body.source_checkpoint_id

        source_state = await graph.aget_state(source_config)
        if source_state.values is None:
            raise HTTPException(status_code=404, detail="Source thread has no state")

        new_thread_id = body.new_thread_id or str(uuid.uuid4())
        new_config = {"configurable": {"thread_id": new_thread_id}}

        # aupdate_state does NOT persist DeltaChannel writes on brand-new
        # threads (aput_writes is skipped when saved=None).  astream is the
        # only robust way to initialise a new thread with full middleware
        # processing for deepagents.
        stream = graph.astream(
            dict(source_state.values),
            stream_mode="updates",
            config=new_config,
            interrupt_before=["model"],
        )
        async for _ in stream:
            pass

        target_state = await graph.aget_state({"configurable": {"thread_id": new_thread_id}})
        from ag_ui_langgraph.utils import langchain_messages_to_agui

        raw = (target_state.values or {}).get("messages", [])
        agui_msgs = langchain_messages_to_agui(raw)
        return {
            "thread_id": new_thread_id,
            "messages": agui_msgs,
        }

    return app


app = create_app()
