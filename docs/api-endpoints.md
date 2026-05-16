# API Endpoints — Frontend Integration Guide

Base URL: `http://<host>:8000`

---

## 1. Send Message (SSE Stream)

**`POST /agent`**

### Request

```json
{
  "threadId": "550e8400-e29b-41d4-a716-446655440000",
  "runId": "660e8400-e29b-41d4-a716-446655440001",
  "state": {},
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": "Hello, how are you?"
    }
  ],
  "tools": [],
  "context": [],
  "forwardedProps": {}
}
```

#### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `threadId` | string | **yes** | UUID của thread. Tạo mới hoặc dùng lại thread cũ |
| `runId` | string | **yes** | UUID của run này (mỗi lần gửi là 1 run) |
| `state` | object | **yes** | State hiện tại, thường là `{}` |
| `messages` | array | **yes** | Danh sách messages gửi đi (thường chỉ 1 message) |
| `tools` | array | **yes** | Tools definition (có thể để `[]`) |
| `context` | array | **yes** | Context (có thể để `[]`) |
| `forwardedProps` | object | **yes** | Props đặc biệt (có thể để `{}`) |

#### Message Types

**User message:**
```json
{
  "id": "uuid",
  "role": "user",
  "content": "Hello"
}

// Hoặc multimodal:
{
  "id": "uuid",
  "role": "user",
  "content": [
    {"type": "text", "text": "What's in this image?"},
    {"type": "image", "source": {"type": "url", "value": "https://..."}}
  ]
}
```

**Assistant message (từ response):**
```json
{
  "id": "uuid",
  "role": "assistant",
  "content": "I'm fine, thank you!",
  "toolCalls": null
}
// Với tool calls:
{
  "id": "uuid",
  "role": "assistant",
  "content": null,
  "toolCalls": [
    {
      "id": "call-uuid",
      "type": "function",
      "function": {"name": "search_by_name", "arguments": "{\"query\": \"...\"}"}
    }
  ]
}
```

**Tool result message:**
```json
{
  "id": "uuid",
  "role": "tool",
  "content": "Search results: ...",
  "toolCallId": "call-uuid"
}
```

---

### Response — SSE Stream

Content-Type: `text/event-stream`

Mỗi event là 1 dòng `data: {json}\n\n`

#### Event Flow (thứ tự typical)

```
RUN_STARTED
    ↓
STEP_STARTED ("agent")
    ↓
TEXT_MESSAGE_START / TOOL_CALL_START
    ↓   (lặp lại nhiều lần)
TEXT_MESSAGE_CONTENT / TOOL_CALL_ARGS
    ↓
TEXT_MESSAGE_END / TOOL_CALL_END
    ↓
MESSAGES_SNAPSHOT (gửi lại toàn bộ messages cuối cùng)
    ↓
RUN_FINISHED
```

#### Event Types

**RUN_STARTED**
```json
{
  "type": "RUN_STARTED",
  "threadId": "uuid",
  "runId": "uuid",
  "input": null
}
```

**RUN_FINISHED**
```json
{
  "type": "RUN_FINISHED",
  "threadId": "uuid",
  "runId": "uuid",
  "result": null
}
```

**RUN_ERROR**
```json
{
  "type": "RUN_ERROR",
  "message": "Error description",
  "code": null
}
```

**STEP_STARTED** — Khi một node trong graph bắt đầu chạy:
```json
{
  "type": "STEP_STARTED",
  "stepName": "agent"
}
```

**STEP_FINISHED** — Khi một node kết thúc:
```json
{
  "type": "STEP_FINISHED",
  "stepName": "agent"
}
```

**TEXT_MESSAGE_START** — Bắt đầu stream 1 assistant message:
```json
{
  "type": "TEXT_MESSAGE_START",
  "messageId": "uuid",
  "role": "assistant"
}
```

**TEXT_MESSAGE_CONTENT** — Từng chunk của message (delta):
```json
{
  "type": "TEXT_MESSAGE_CONTENT",
  "messageId": "uuid",
  "delta": "Xin ch"
}
// → tiếp theo:
{ "type": "TEXT_MESSAGE_CONTENT", "messageId": "uuid", "delta": "ào, t" }
// → tiếp theo:
{ "type": "TEXT_MESSAGE_CONTENT", "messageId": "uuid", "delta": "ôi là " }
// → ...
```

**TEXT_MESSAGE_END** — Kết thúc message:
```json
{
  "type": "TEXT_MESSAGE_END",
  "messageId": "uuid"
}
```

**TOOL_CALL_START** — Bắt đầu 1 tool call:
```json
{
  "type": "TOOL_CALL_START",
  "toolCallId": "call-uuid",
  "toolCallName": "search_by_name",
  "parentMessageId": "uuid"
}
```

**TOOL_CALL_ARGS** — Từng chunk của tool arguments:
```json
{
  "type": "TOOL_CALL_ARGS",
  "toolCallId": "call-uuid",
  "delta": "{\"query\": \"sa"
}
// → tiếp theo:
{ "type": "TOOL_CALL_ARGS", "toolCallId": "call-uuid", "delta": "les repor" }
// → tiếp theo:
{ "type": "TOOL_CALL_ARGS", "toolCallId": "call-uuid", "delta": "t\"}" }
```

**TOOL_CALL_END** — Kết thúc tool call:
```json
{
  "type": "TOOL_CALL_END",
  "toolCallId": "call-uuid"
}
```

**TOOL_CALL_RESULT** — Kết quả tool execution:
```json
{
  "type": "TOOL_CALL_RESULT",
  "messageId": "uuid",
  "toolCallId": "call-uuid",
  "content": "{...result...}",
  "role": "tool"
}
```

**STATE_SNAPSHOT** — State hiện tại của graph:
```json
{
  "type": "STATE_SNAPSHOT",
  "snapshot": { ... }
}
```

**MESSAGES_SNAPSHOT** — Danh sách messages hiện tại (dùng để sync frontend):
```json
{
  "type": "MESSAGES_SNAPSHOT",
  "messages": [
    {"id": "...", "role": "user", "content": "Hello"},
    {"id": "...", "role": "assistant", "content": "Hi!"}
  ]
}
```

**CUSTOM** — Event custom:
```json
{
  "type": "CUSTOM",
  "name": "event_name",
  "value": ...
}
```

---

## 2. List Threads

**`GET /threads`**

### Response

```json
{
  "threads": [
    {
      "thread_id": "550e8400-e29b-41d4-a716-446655440000",
      "metadata": {}
    }
  ]
}
```

---

## 3. Create Thread

**`POST /threads`**

Tự động khởi tạo checkpointer state cho thread mới (nên `GET .../state` luôn trả về hợp lệ).

### Request

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `thread_id` | string | no | Tự sinh UUID nếu không truyền |
| `metadata` | object | no | Metadata tuỳ ý |

### Response

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {}
}
```

---

## 4. Get Thread Detail

**`GET /threads/{thread_id}`**

### Response

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {}
}
```

> Chỉ trả về metadata, **không** có messages.

---

## 5. Get Thread Messages (State)

**`GET /threads/{thread_id}/state`**

Lấy toàn bộ messages từ LangGraph checkpointer. Cần gọi API này khi:
- F5 refresh page
- Mở lại app sau khi đóng

Luôn trả về 200 với `messages` array. Nếu thread chưa có tin nhắn nào, trả về `[]` (không 404).

### Response

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": "Hello"
    },
    {
      "id": "msg-002",
      "role": "assistant",
      "content": "Hi! How can I help you today?"
    }
  ]
}
```

> Messages format giống hệt `messages` trong `MESSAGES_SNAPSHOT` event.

---

## 6. Save Messages to Thread

**`PUT /threads/{thread_id}/state`**

Ghi messages vào checkpointer. Dùng để:
- Sync messages từ frontend lên server (nếu cần)
- Append thêm messages vào thread history
- Khôi phục state khi cần

### Request

```json
{
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": "Hello"
    },
    {
      "id": "msg-002",
      "role": "assistant",
      "content": "Hi! How can I help you today?"
    }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `messages` | array | **yes** | Danh sách messages AG-UI format. Mỗi message cần có `role`, `id`, `content`. Messages mới được append vào existing history (add_messages reducer). |

### Response

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {"id": "msg-001", "role": "user", "content": "Hello"},
    {"id": "msg-002", "role": "assistant", "content": "Hi! How can I help you today?"}
  ]
}
```

> **Lưu ý:** Sau khi `POST /agent` hoàn tất, worker tự động persist messages vào checkpointer. Chỉ cần dùng PUT này nếu frontend muốn sync state thủ công.

---

## 7. Thread State History (Debug)

**`GET /threads/{thread_id}/state/history`**

Liệt kê tất cả checkpoints của thread. Dùng để debug kiểm tra xem state có được lưu không.

### Response

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "checkpoints": [
    {
      "checkpoint_id": "1f1510c7-2c62-6d34-8000-fa90626048d7",
      "message_count": 0,
      "next": []
    },
    {
      "checkpoint_id": "2f1510c7-2c62-6d34-8000-fa90626048d8",
      "message_count": 2,
      "next": []
    }
  ]
}
```

| Field | Description |
|---|---|
| `checkpoint_id` | UUID của checkpoint |
| `message_count` | Số messages trong checkpoint đó |
| `next` | Các node tiếp theo (rỗng nếu graph đã kết thúc) |

> Checkpoints được sắp xếp từ mới nhất tới cũ nhất.

---

## 8. Delete Thread

**`DELETE /threads/{thread_id}`**

Xoá cả metadata (`_threads` dict) và checkpointer state (MemorySaver). Thread sẽ không còn xuất hiện trong `GET /threads` và `GET .../state` trả về `messages: []`.

### Response

```json
{
  "status": "deleted",
  "thread_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 9. List Agents

**`GET /agents`**

### Response

```json
{
  "agents": [
    {
      "name": "lm-assistant",
      "endpoint": "/agent"
    }
  ]
}
```

---

## 10. Health Check

**`GET /health`**
```json
{
  "status": "ok",
  "service": "LM Agent Service"
}
```

**`GET /agent/health`**
```json
{
  "status": "ok",
  "agent": {"name": "lm-assistant"}
}
```

---

## SSE Format Detail

Mỗi event là 1 dòng:

```
data: {"type":"RUN_STARTED","threadId":"uuid","runId":"uuid"}

data: {"type":"TEXT_MESSAGE_START","messageId":"uuid","role":"assistant"}

data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"uuid","delta":"Hello"}

data: {"type":"TEXT_MESSAGE_END","messageId":"uuid"}

data: {"type":"RUN_FINISHED","threadId":"uuid","runId":"uuid"}

```

- Mỗi event kết thúc bằng `\n\n`
- Field names dùng camelCase (`by_alias=True`)
- Field `null` bị exclude (`exclude_none=True`)

---

## Typical Frontend Flow

```
1. Mở app:
   GET /threads ───→ list thread titles

2. Click vào thread cũ:
   Nếu có cache local → show messages ngay
   Nếu không (F5)   → GET /threads/{id}/state → show messages

3. Gửi message:
   POST /agent (SSE) → nhận token stream → render real-time
                       nhận MESSAGES_SNAPSHOT → update local cache
                       → worker tự động persist messages vào checkpointer

4. Tạo thread mới:
   POST /threads → lấy thread_id → POST /agent với thread_id đó
```

## Data Persistence Summary

| Dữ liệu | Lưu ở đâu | Cách ghi | Cách đọc |
|---|---|---|---|
| Thread metadata | In-memory `_threads` dict | `POST /threads` | `GET /threads`, `GET /threads/{id}` |
| Messages / State | LangGraph MemorySaver checkpointer | Tự động sau `POST /agent` hoặc `PUT /threads/{id}/state` | `GET /threads/{id}/state` |
| Checkpoint history | MemorySaver | Tự động mỗi lần graph chạy | `GET /threads/{id}/state/history` |

> ⚠️ MemorySaver là in-memory, mất khi restart server. Để persist qua restart, cấu hình PostgreSQL checkpointer trong `langgraph.json`.
