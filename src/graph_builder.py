from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from ag_ui_langgraph import LangGraphAgent
from langchain.agents.structured_output import ResponseFormat
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
from psycopg_pool import AsyncConnectionPool

from src.agent.tools.search_tool import SEARCH_TOOLS
from src.core.log import get_logger

logger = get_logger("graph_builder")

SYSTEM_PROMPT = """Bạn là trợ lý AI chuyên tư vấn tài liệu tài chính - kế toán.

## Nhiệm vụ
- Tra cứu và giải thích các văn bản pháp luật, thông tư, nghị định về kế toán - tài chính
- Hỗ trợ tìm kiếm tài liệu chuyên ngành (chuẩn mực kế toán VAS, IFRS, báo cáo tài chính...)
- Phân tích và tổng hợp thông tin từ nhiều tài liệu
- Giải đáp thắc mắc về quy trình, nghiệp vụ kế toán

## Công cụ tra cứu
- **search_by_name**: Tìm tài liệu theo tên file (fuzzy search)
- **vector_search**: Tìm kiếm ngữ nghĩa trong nội dung tài liệu
- **read_document**: Đọc nội dung chi tiết của tài liệu
- **get_documents**: Xem danh sách tài liệu gần đây

## Hướng dẫn
1. Tra cứu tài liệu để tìm thông tin liên quan đến câu hỏi
2. Đọc kỹ nội dung trước khi trả lời
3. Trích dẫn nguồn tài liệu khi đưa ra thông tin
4. Với câu hỏi phức tạp, hãy chia nhỏ và sử dụng subagent chuyên biệt
5. Nếu cần tra cứu sâu, hãy giao việc cho subagent phù hợp qua task() tool"""



# init in DI
def build_deep_agent(
    model: Any,
    tools: Optional[list] = None,
    system_prompt: Optional[str] = None,
    subagent_configs: Optional[Sequence[Any]] = None,
    checkpointer: Optional[AsyncPostgresSaver] = None,
    store: Optional[Any] = None,
    interrupt_on: Optional[dict[str, Any]] = None,
    response_format: Optional[ResponseFormat | type | dict[str, Any]] = None,
    name: str = "lm-assistant",
) -> CompiledStateGraph:
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=model,
        tools=tools or SEARCH_TOOLS,
        system_prompt=system_prompt or SYSTEM_PROMPT,
        subagents=subagent_configs or [],
        checkpointer=checkpointer,
        store=store or InMemoryStore(),
        interrupt_on=interrupt_on,
        response_format=response_format,
        name=name,
        debug=False,
    )


# ─── Container factories ───────────────────────────────────────────


def create_db_pool(database_uri: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(database_uri, open=False, kwargs={"autocommit": True})
    return pool


def create_checkpointer(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
    return AsyncPostgresSaver(conn=pool)


def create_agent_inst(
    name: str,
    description: str | None,
    graph: CompiledStateGraph,
) -> LangGraphAgent:
    return LangGraphAgent(name=name, description=description, graph=graph)
