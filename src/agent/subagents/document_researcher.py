from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from src.agent.subagents.base import (
    build_subagent_workflow,
    create_subagent_model,
    filter_tools,
)
from src.agent.tools.search_tool import SEARCH_TOOLS

RESEARCH_PROMPT = """Bạn là chuyên gia tra cứu tài liệu tài chính - kế toán.

## Giai đoạn Tra cứu
Sử dụng các công cụ dưới đây để tìm kiếm thông tin:

1. **search_by_name**: Tìm tài liệu theo tên file
2. **vector_search**: Tìm kiếm ngữ nghĩa trong nội dung
3. **read_document**: Đọc nội dung chi tiết
4. **get_documents**: Xem danh sách tài liệu gần đây

Hãy chủ động tìm kiếm nhiều nguồn khác nhau. Đọc kỹ nội dung trước khi kết luận là đã có đủ thông tin.
Khi bạn đã thu thập đầy đủ thông tin, hãy trả lời mà KHÔNG gọi tool — hệ thống sẽ tự động chuyển sang giai đoạn tổng hợp."""

SYNTHESIS_PROMPT = """Bạn là chuyên gia tra cứu tài liệu tài chính - kế toán.

## Giai đoạn Tổng hợp
Dựa trên toàn bộ thông tin đã tra cứu, hãy tổng hợp thành câu trả lời hoàn chỉnh.

Yêu cầu:
- Trình bày rõ ràng, có cấu trúc (mục, tiêu đề nếu cần)
- Trích dẫn nguồn tài liệu cụ thể (tên file, điều khoản...)
- Nếu thông tin không đầy đủ, hãy nêu rõ những gì cần bổ sung
- KHÔNG gọi bất kỳ tool nào ở giai đoạn này"""


def build_document_researcher(
    model: Optional[BaseChatModel] = None,
    tools: Optional[list[BaseTool]] = None,
) -> CompiledStateGraph:
    researcher_tools = tools or filter_tools(
        SEARCH_TOOLS,
        {"search_by_name", "vector_search", "read_document", "get_documents"},
    )
    if model is None:
        model = create_subagent_model()

    return build_subagent_workflow(
        model=model,
        research_tools=researcher_tools,
        research_prompt=RESEARCH_PROMPT,
        synthesis_prompt=SYNTHESIS_PROMPT,
    )
