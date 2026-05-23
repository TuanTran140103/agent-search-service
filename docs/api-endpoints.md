# API Endpoints — Frontend Integration Guide

Base URL: `http://<host>:8000`

> **Authentication**: Mọi request được nginx proxy qua, nginx inject header `X-User-Id`. Frontend không cần tự gửi auth.

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

## 2. Edit Message (No LLM)

**`PATCH /threads/{thread_id}/state`**

Edit message hiện có và xóa toàn bộ messages phía sau nó. **Không gọi LLM** — chỉ commit state mới và trả về messages list.

> Dùng khi user nhấn "Edit" trên một message. Sau đó frontend tự gọi `POST /agent` để lấy AI response mới.

### Request

```json
{
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": "Nội dung mới sau khi edit"
    }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `messages` | array | **yes** | Messages cần edit (phải có `id` trùng với message hiện có). Có thể gửi nhiều message cùng lúc. |

**Quy tắc:**
- `id` trong body **phải trùng** với 1 message trong thread hiện tại
- Server tìm **vị trí cuối cùng** của message được edit trong danh sách hiện tại
- Giữ nguyên tất cả messages **trước** message đó
- **Thay thế** message bằng nội dung mới (dùng `RemoveMessage` của LangChain, tương thích với `DeltaChannel` reducer của DeepAgents)
- **Xóa toàn bộ** messages phía sau

### Response — Full Conversation List

Server trả về **toàn bộ các messages còn lại** sau khi edit (không phải chỉ riêng message vừa edit).

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "checkpoint_id": "1f154ff6-dcb0-6055-8003-333ac6e023b8",
  "messages": [
    {"id": "msg-000", "role": "user", "content": "Hello"},
    {"id": "msg-001", "role": "user", "content": "Nội dung mới sau khi edit"}
  ]
}
```

| Field | Description |
|---|---|
| `thread_id` | UUID thread |
| `checkpoint_id` | Checkpoint mới vừa được tạo (`next=["model"]` - đang chờ LLM) |
| `messages` | **Full conversation list** (tất cả messages còn lại) |

### Frontend Flow

```
User nhấn "Edit" message msg-001
  |
  ├── Frontend xóa UI các messages phía dưới msg-001
  ├── User nhập nội dung mới
  ├── PATCH /threads/{id}/state
  │     Body: {"messages": [{"id":"msg-001","role":"user","content":"mới"}]}
  │     → Server: giữ msg-000, thay msg-001, xóa msg-002,003...
  │     ← Response: { messages: [msg-000, msg-001(mới)] }  ← full list
  ├── Frontend update UI với messages từ response
  └── POST /agent
        Body: {
          "threadId": "...",
          "runId": "uuid-mới",
          "messages": [msg-000, msg-001(mới)]   ← copy từ PATCH response
        }
        → Worker: load checkpoint, nhận diện messages đều có trong checkpoint
        → Chạy agent trên checkpoint hiện tại (không append message mới)
        → SSE stream AI response mới
        → Append AI response vào UI
```

> 💡 **Tại sao 2 bước?** PATCH chỉ commit state (không gọi LLM). POST /agent chạy LLM. Tách biệt cho phép frontend hiển thị "đang typing" hoặc xử lý UI trước khi stream bắt đầu.
>
> 🔹 **Quan trọng**: Client gửi `messages` trong POST /agent giống hệt `messages` từ PATCH response. Worker tự dùng checkpoint làm source of truth — chỉ append message thực sự mới (ID chưa có trong checkpoint), ignore stale data.

---

## 3. Get Thread Messages (State)

**`GET /threads/{thread_id}/state`**

Lấy toàn bộ messages từ PostgreSQL (PostgresSaver checkpointer). Cần gọi API này khi:
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

## 4. Thread State History (Debug)

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
      "next": [],
      "messages": []
    },
    {
      "checkpoint_id": "2f1510c7-2c62-6d34-8000-fa90626048d8",
      "message_count": 2,
      "next": [],
      "messages": [
        {"id": "msg-001", "role": "user", "content": "Hello"},
        {"id": "msg-002", "role": "assistant", "content": "Hi!"}
      ]
    }
  ]
}
```

| Field | Description |
|---|---|
| `checkpoint_id` | UUID của checkpoint |
| `message_count` | Số messages trong checkpoint đó |
| `messages` | Danh sách messages (ag-ui format) |
| `next` | Các node tiếp theo (rỗng nếu graph đã kết thúc) |

> Checkpoints được sắp xếp từ mới nhất tới cũ nhất.

---

## 5. List Agents

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

## 6. Health Check

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
1. Mở app (thread cũ):
   Nếu có cache local → show messages ngay
   Nếu không (F5)   → GET /threads/{threadId}/state → show messages

2. Chat tiếp trong thread cũ:
   POST /agent (SSE) với threadId + messages hiện tại
   → Worker: checkpoint = source of truth, chỉ append user message thực sự mới
   → Nhận token stream → render real-time
   → Nhận MESSAGES_SNAPSHOT → update local cache
   → Checkpointer tự động lưu messages

3. Edit message (giống ChatGPT):
   a. User nhấn "Edit" trên message N
   b. Frontend xóa UI tất cả messages phía dưới message N
   c. User nhập nội dung mới
   d. PATCH /threads/{threadId}/state {"messages": [{"id":"...","content":"mới"}]}
      ← Response: { messages: [full conversation list] }
   e. Frontend update UI với messages từ response
   f. POST /agent với messages = response.messages (copy nguyên bản)
      → Worker: load checkpoint, payload IDs đều trong checkpoint
      → Chạy agent trên checkpoint → stream AI response
      → Append AI response vào UI

4. Tạo thread mới:
   Frontend tự sinh UUID làm threadId
   → POST /agent với threadId mới
   → checkpointer auto-create thread khi lần đầu chạy
```

## Data Persistence Summary

| Endpoint | Method | Purpose |
|---|---|---|
| `/agent` | POST | Gửi message → stream AI response (SSE) |
| `/threads/{id}/state` | GET | Lấy messages hiện tại của thread |
| `/threads/{id}/state` | PATCH | Edit message + xóa messages sau (không gọi LLM) |
| `/threads/{id}/state/history` | GET | Liệt kê checkpoint history (debug) |
| `/threads/{id}/fork` | POST | Copy thread sang thread mới |

| Dữ liệu | Lưu ở đâu | Cách ghi | Cách đọc |
|---|---|---|---|
| Messages / State | PostgreSQL checkpoints table (PostgresSaver) | Tự động khi graph chạy (`astream`) | `GET /threads/{id}/state` |
| Checkpoint history | PostgreSQL checkpoints table (PostgresSaver) | Tự động mỗi lần graph chạy | `GET /threads/{id}/state/history` |

> ✅ Dữ liệu được persist trong PostgreSQL. Restart server không mất dữ liệu.
> 🔹 ThreadId do **frontend tự tạo** (UUID). Server không quản lý CRUD thread.
> 🔹 Quan hệ thread ↔ user do **server khác** quản lý.
