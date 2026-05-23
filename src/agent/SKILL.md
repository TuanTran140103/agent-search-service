# SubAgent Development Guide

## Tổng quan

SubAgent là các "agent con" có workflow riêng, được main agent (DeepAgent) gọi qua tool `task()`.  
Mỗi subAgent có một **LangGraph `CompiledStateGraph`** độc lập — bạn hoàn toàn kiểm soát luồng xử lý.

```
User → Main Agent → task("document-researcher", "phân tích...")
                   → CompiledSubAgent.runnable.invoke({"messages": [HumanMessage(...)]})
                   → Custom graph chạy (search → read → synthesize)
                   → Trả kết quả về Main Agent
```

## Cấu trúc thư mục

```
src/agent/subagents/
├── __init__.py                      # Export các build function
├── base.py                          # Shared utilities
├── document_researcher.py           # Mẫu subAgent
├── financial_analyzer.py
└── compliance_checker.py
```

## Cách tạo một SubAgent mới

### Bước 1: Tạo file subagent

```python
# src/agent/subagents/my_subagent.py
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

# Prompt cho giai đoạn 1 — Tra cứu (có tool)
RESEARCH_PROMPT = """Hướng dẫn cho LLM trong giai đoạn tìm kiếm thông tin.
Khi đã đủ dữ liệu, trả lời KHÔNG gọi tool."""

# Prompt cho giai đoạn 2 — Tổng hợp (không tool)
SYNTHESIS_PROMPT = """Hướng dẫn cho LLM trong giai đoạn tổng hợp kết quả."""


def build_my_subagent(
    model: Optional[BaseChatModel] = None,
    tools: Optional[list[BaseTool]] = None,
) -> CompiledStateGraph:
    # Chọn tool cho subAgent này
    my_tools = tools or filter_tools(
        SEARCH_TOOLS,
        {"search_by_name", "vector_search", "read_document"},
    )
    if model is None:
        model = create_subagent_model()

    return build_subagent_workflow(
        model=model,
        research_tools=my_tools,
        research_prompt=RESEARCH_PROMPT,
        synthesis_prompt=SYNTHESIS_PROMPT,
    )
```

### Bước 2: Export trong `__init__.py`

```python
# src/agent/subagents/__init__.py
from src.agent.subagents.my_subagent import build_my_subagent

__all__ = [
    ...,
    "build_my_subagent",
]
```

### Bước 3: Đăng ký với Main Agent (trong DI)

Trong `src/container.py`, import `build_my_subagent`, tạo `CompiledSubAgent`:

```python
from deepagents.middleware.subagents import CompiledSubAgent
from src.subagents.my_subagent import build_my_subagent

# Build graph với model mặc định
my_subagent_graph = build_my_subagent()

# Wrap thành CompiledSubAgent
my_subagent = CompiledSubAgent(
    name="my-subagent",
    description="Mô tả ngắn để main agent biết khi nào gọi",
    runnable=my_subagent_graph,
)

# Pass vào build_deep_agent
graph = providers.Singleton(
    build_deep_agent,
    subagent_configs=[my_subagent, ...],  # list[CompiledSubAgent]
    ...
)
```

## Kiến trúc SubAgent Workflow

Mỗi subAgent dùng **two-phase workflow** từ `base.build_subagent_workflow()`:

```
START → Research Phase (LLM + tools loop)
         ├── tool_calls → ToolNode → quay lại Research
         └── no tools → Synthesis Phase (LLM-only) → END
```

| Phase | Tools | Mục đích |
|---|---|---|
| **Research** | Có (tuỳ chỉnh) | Thu thập thông tin, tra cứu tài liệu |
| **Synthesis** | Không | Tổng hợp, phân tích, tạo kết quả cuối cùng |

Lợi ích của cấu trúc này:
- **Ràng buộc thứ tự**: Research luôn trước Synthesis
- **Không tool ở Synthesis**: LLM không thể "trì hoãn" kết luận bằng cách gọi tool thêm
- **Mỗi phase có prompt riêng**: Tối ưu hóa cho từng giai đoạn

## Tạo workflow tùy chỉnh (nâng cao)

Nếu two-phase không đủ, bạn có thể tự định nghĩa graph riêng thay vì dùng `build_subagent_workflow`:

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage

def build_custom_subagent(model, tools) -> CompiledStateGraph:
    def step1_search(state):
        # Bắt buộc search trước
        ...

    def step2_filter(state):
        # Lọc kết quả
        ...

    def step3_read(state):
        # Đọc tài liệu
        ...

    def step4_report(state):
        # Tạo báo cáo
        ...

    workflow = StateGraph(MessagesState)
    workflow.add_node("search", step1_search)
    workflow.add_node("filter", step2_filter)
    workflow.add_node("read", step3_read)
    workflow.add_node("report", step4_report)

    workflow.add_edge(START, "search")
    workflow.add_edge("search", "filter")
    workflow.add_edge("filter", "read")
    workflow.add_edge("read", "report")
    workflow.add_edge("report", END)

    return workflow.compile()
```

## CompiledSubAgent Contract

Khi main agent gọi `task(name, description)`, `SubAgentMiddleware` tạo state:

```python
{"messages": [HumanMessage(content=description)]}
```

Graph của bạn **phải**:
- Accept state với key `"messages"`
- Return state với key `"messages"`
- Message cuối cùng trong `messages` là kết quả trả về cho main agent

## Testing SubAgent

```python
from src.agent.subagents.document_researcher import build_document_researcher

graph = build_document_researcher()
result = graph.invoke({
    "messages": [("human", "Tìm thông tư 200/2014/TT-BTC")]
})
print(result["messages"][-1].content)
```
