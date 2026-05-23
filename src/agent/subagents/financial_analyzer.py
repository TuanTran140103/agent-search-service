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

RESEARCH_PROMPT = """Bạn là chuyên gia phân tích báo cáo tài chính.

## Giai đoạn Thu thập dữ liệu
Sử dụng các công cụ để tìm kiếm và đọc báo cáo tài chính:

1. **vector_search**: Tìm kiếm số liệu tài chính trong nội dung báo cáo
2. **read_document**: Đọc chi tiết báo cáo, bảng cân đối kế toán, KQKD

Cần tìm kiếm các thông tin:
- Doanh thu, lợi nhuận qua các kỳ
- Tổng tài sản, nợ phải trả, vốn chủ sở hữu
- Các chỉ số tài chính đặc thù
- Thuyết minh báo cáo tài chính

Hãy đọc nhiều báo cáo để có dữ liệu so sánh. Khi đã có đủ số liệu, hãy trả lời KHÔNG gọi tool để chuyển sang giai đoạn phân tích."""

SYNTHESIS_PROMPT = """Bạn là chuyên gia phân tích báo cáo tài chính.

## Giai đoạn Phân tích & Báo cáo
Dựa trên dữ liệu đã thu thập, hãy phân tích và trình bày báo cáo.

Yêu cầu:
- Tính toán các chỉ số tài chính: ROA, ROE, biên lợi nhuận, tỷ số thanh khoản...
- So sánh kết quả qua các kỳ (nếu có dữ liệu nhiều kỳ)
- Nhận định xu hướng và điểm bất thường
- Trình bày dưới dạng bảng biểu nếu phù hợp
- Trích dẫn nguồn báo cáo cụ thể cho từng số liệu
- KHÔNG gọi bất kỳ tool nào"""


def build_financial_analyzer(
    model: Optional[BaseChatModel] = None,
    tools: Optional[list[BaseTool]] = None,
) -> CompiledStateGraph:
    analyzer_tools = tools or filter_tools(
        SEARCH_TOOLS,
        {"vector_search", "read_document"},
    )
    if model is None:
        model = create_subagent_model(temperature=0.2)

    return build_subagent_workflow(
        model=model,
        research_tools=analyzer_tools,
        research_prompt=RESEARCH_PROMPT,
        synthesis_prompt=SYNTHESIS_PROMPT,
    )
