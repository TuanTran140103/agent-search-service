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

RESEARCH_PROMPT = """Bạn là chuyên gia kiểm tra tuân thủ chuẩn mực kế toán (VAS, IFRS).

## Giai đoạn Tra cứu quy định
Sử dụng các công cụ để tìm kiếm văn bản pháp luật và quy định:

1. **search_by_name**: Tìm văn bản theo tên (thông tư, nghị định, chuẩn mực...)
2. **vector_search**: Tìm kiếm điều khoản, nội dung quy định
3. **read_document**: Đọc chi tiết văn bản

Cần tìm kiếm:
- Chuẩn mực kế toán (VAS, IFRS) liên quan
- Thông tư hướng dẫn của Bộ Tài chính
- Nghị định về quản lý tài chính
- Các quyết định, văn bản pháp luật khác

Đọc kỹ từng điều khoản trước khi đưa ra kết luận. Khi đã có đủ căn cứ pháp lý, hãy trả lời KHÔNG gọi tool."""

SYNTHESIS_PROMPT = """Bạn là chuyên gia kiểm tra tuân thủ chuẩn mực kế toán.

## Giai đoạn Đánh giá & Kết luận
Dựa trên các quy định đã tra cứu, hãy phân tích và đưa ra kết luận.

Cấu trúc báo cáo:
1. **Vấn đề được hỏi**: Tóm tắt nghiệp vụ/quy trình cần kiểm tra
2. **Căn cứ pháp lý**: Liệt kê các văn bản, điều khoản liên quan
3. **Phân tích**: Đối chiếu từng yêu cầu với quy định
4. **Kết luận**: Tuân thủ/Không tuân thủ/Cần bổ sung thông tin
5. **Khuyến nghị**: Đề xuất hướng xử lý nếu cần

Trích dẫn đầy đủ: tên văn bản, số hiệu, điều khoản cụ thể.
KHÔNG gọi bất kỳ tool nào ở giai đoạn này."""


def build_compliance_checker(
    model: Optional[BaseChatModel] = None,
    tools: Optional[list[BaseTool]] = None,
) -> CompiledStateGraph:
    checker_tools = tools or filter_tools(
        SEARCH_TOOLS,
        {"search_by_name", "vector_search", "read_document"},
    )
    if model is None:
        model = create_subagent_model(temperature=0.2)

    return build_subagent_workflow(
        model=model,
        research_tools=checker_tools,
        research_prompt=RESEARCH_PROMPT,
        synthesis_prompt=SYNTHESIS_PROMPT,
    )
