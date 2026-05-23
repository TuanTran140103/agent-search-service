# ToolRuntime Injection Bug (LangChain 1.4.0)

## Triệu chứng

```
TypeError: search_by_name() missing 1 required positional argument: 'runtime'
```

Xảy ra khi model gọi tool có parameter `runtime: ToolRuntime`. Tất cả các tool có runtime đều bị, không chỉ search_by_name.

## Nguyên nhân gốc rễ

**LangChain 1.4.0 bug**: `StructuredTool._injected_args_keys` trả về `frozenset()` (rỗng).

### Luồng lỗi

```
ToolNode._inject_tool_args(call, runtime, tool)
  → inject runtime vào call["args"] thành công
  → call_args = {**injected_call, "type": "tool_call"}
  
tool.ainvoke(call_args, config)
  → _prep_run_args: trích tool_input = call_args["args"]
  → _to_args_and_kwargs(tool_input):
      → _parse_input(tool_input):
          → model_validate(SearchByNameInput, tool_input)
              → schema chỉ có query_text → runtime bị DROP
          → _injected_args_keys = frozenset()  ← BUG!
          → loop _injected_args_keys: không chạy → runtime KHÔNG được add lại
      → return (), tool_input.copy()  ← thiếu runtime
  → _arun(**kwargs) → coroutine(query_text="test") → missing runtime!
```

### Chi tiết

| Component | Giá trị | Ghi chú |
|---|---|---|
| `_get_all_injected_args(tool)` | `runtime='runtime'` | Phát hiện đúng |
| `ToolNode._injected_args[tool]` | `runtime=runtime` | Đúng |
| `StructuredTool._injected_args_keys` | `frozenset()` | **Sai** — kế thừa từ BaseTool, không override |
| `_parse_input` loop | không chạy | Vì `_injected_args_keys` rỗng |

## Fix

### File sửa: `src/agent/tools/search_tool.py`

```python
from langgraph.prebuilt.tool_node import _get_all_injected_args
for _t in SEARCH_TOOLS:
    _injected = _get_all_injected_args(_t)
    _keys = set()
    if _injected.state:
        _keys.update(_injected.state)
    if _injected.store:
        _keys.add(_injected.store)
    if _injected.runtime:
        _keys.add(_injected.runtime)
    _t._injected_args_keys = frozenset(_keys)
```

### Cơ chế

`_injected_args_keys` là `cached_property` trên `BaseTool`. `StructuredTool` không override → luôn trả về rỗng. Set trực tiếp lên instance override được cached_property (Python lookup instance dict trước descriptor).

### Áp dụng

- Đã fix ở `src/agent/tools/search_tool.py` — tất cả tools trong `SEARCH_TOOLS` được patch.
- Nếu thêm tool mới có `runtime: ToolRuntime`, cần patch tương tự hoặc đảm bảo `_injected_args_keys` được set.

## Litmus test

```python
from src.agent.tools.search_tool import search_by_name
assert 'runtime' in search_by_name._injected_args_keys
```

## LangChain versions

| Version | Bug? |
|---|---|
| 1.4.0 | ✅ Có bug |
| > 1.4.0 | Cần kiểm tra lại |

## Related

- `_parse_input` trong `langchain_core/tools/structured.py` — nơi runtime bị drop
- `_inject_tool_args` trong `langgraph/prebuilt/tool_node.py` — nơi runtime được inject (đúng)
- `_get_all_injected_args` — detect injected args (đúng)
