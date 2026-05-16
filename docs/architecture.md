# LM Agent Service Architecture

## 1. Current Architecture (Single Process - không scale)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          User 10k Concurrent                            │
│                    POST /agent (RunAgentInput JSON)                     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Load Balancer (Nginx)                            │
│                         Round Robin / Least Connections                 │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Server (1 process)                         │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        uvicon Worker #1                         │    │
│  │                                                                 │    │
│  │  POST /agent ──► LangGraphAgent.run()                          │    │
│  │                      │                                          │    │
│  │                      ▼                                          │    │
│  │               graph.astream_events()                            │    │
│  │                      │                                          │    │
│  │                      ├── LLM call (OpenAI) ──── 5-30s           │    │
│  │                      ├── Tool execution      ──── 1-3s          │    │
│  │                      ├── PostgresSaver write  ──── 10-50ms      │    │
│  │                      │                                          │    │
│  │                      ▼                                          │    │
│  │               EventEncoder → SSE stream                          │    │
│  │                                                                 │    │
│  │  Memory: ~10MB / concurrent run                                 │    │
│  │  Limit: ~50-100 concurrent runs / worker                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ⚠ Bottlenecks:                                                        │
│  • 1 worker → 1 CPU core (GIL)                                        │
│  • astream_events() giữ RAM suốt LLM call                             │
│  • _threads in-memory dict: mất khi restart                           │
│  • SSE connection tie up HTTP handler                                 │
│  • Không backpressure: 10k request ập đến = crash                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Target Architecture (Queue-based - scale ngang)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          User 10k Concurrent                            │
│                    POST /agent (RunAgentInput JSON)                     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Load Balancer (Nginx)                            │
│                    keepalive, rate limit, SSL termination               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│                     │ │                     │ │                     │
│   FastAPI API GW    │ │   FastAPI API GW    │ │   FastAPI API GW    │
│   (N instances)      │ │   (N instances)      │ │   (N instances)      │
│                     │ │                     │ │                     │
│  Role:              │ │  Role:              │ │  Role:              │
│  • Receive POST     │ │  • Receive POST     │ │  • Receive POST     │
│  • Push queue       │ │  • Push queue       │ │  • Push queue       │
│  • Subscribe Redis  │ │  • Subscribe Redis  │ │  • Subscribe Redis  │
│  • Relay SSE        │ │  • Relay SSE        │ │  • Relay SSE        │
│                     │ │                     │ │                     │
│  Stateless:         │ │  Stateless:         │ │  Stateless:         │
│  Không giữ state    │ │  Không giữ state    │ │  Không giữ state    │
│  10k+ connections   │ │  10k+ connections   │ │  10k+ connections   │
│  ~200MB RAM         │ │  ~200MB RAM         │ │  ~200MB RAM         │
└──────────┬──────────┘ └──────────┬──────────┘ └──────────┬──────────┘
           │                      │                      │
           └──────────────────────┼──────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│                    Redis (Event Bus + Queue)                            │
│                                                                         │
│  ┌─────────────────────────┐    ┌──────────────────────────────┐       │
│  │  Stream: agent:requests │    │  Pub/Sub: agent:events:*      │       │
│  │                         │    │                               │       │
│  │  Consumer Groups:       │    │  Channel per run:             │       │
│  │  • agent-workers        │    │  • agent:events:{runId}       │       │
│  │                         │    │                               │       │
│  │  Backpressure:          │    │  Worker publish event →       │       │
│  │  • MAXLEN ~10000        │    │  API GW relay → SSE           │       │
│  │  • Block khi queue đầy  │    │                               │       │
│  └─────────────────────────┘    └──────────────────────────────┘       │
│                                                                         │
└───────────────────────────────────────────┬─────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              ▼                             ▼                             ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│                     │ │                     │ │                     │
│   Agent Worker #1   │ │   Agent Worker #2   │ │   Agent Worker #N   │
│   (Python process)  │ │   (Python process)  │ │   (Python process)  │
│                     │ │                     │ │                     │
│  XLAK: {            │ │  XLAK: {            │ │  XLAK: {            │
│    consume queue    │ │    consume queue    │ │    consume queue    │
│    run LangGraph    │ │    run LangGraph    │ │    run LangGraph    │
│    publish events   │ │    publish events   │ │    publish events   │
│    write Postgres   │ │    write Postgres   │ │    write Postgres   │
│  }                  │ │  }                  │ │  }                  │
│                     │ │                     │ │                     │
│  ~10 concurrent     │ │  ~10 concurrent     │ │  ~10 concurrent     │
│  runs / worker      │ │  runs / worker      │ │  runs / worker      │
│  ~100-200MB RAM     │ │  ~100-200MB RAM     │ │  ~100-200MB RAM     │
└──────────┬──────────┘ └──────────┬──────────┘ └──────────┬──────────┘
           │                      │                      │
           └──────────────────────┼──────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PostgreSQL                                      │
│                                                                         │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐ │
│  │  langgraph_checkpoints       │  │  threads (custom)                │ │
│  │  ─────────────────────────   │  │  ─────────────────────           │ │
│  │  thread_id │ checkpoint      │  │  id │ user_id │ meta │ created   │ │
│  │  checkpoint_id │ parent      │  │                                  │ │
│  │  type │ state │ metadata     │  │  ┌────────────────────────────────┐ │
│  │                              │  │  │  messages (optional archive)  │ │
│  │  Used by LangGraph's         │  │  └────────────────────────────────┘ │
│  │  PostgresSaver internally    │  │                                    │
│  └──────────────────────────────┘  └──────────────────────────────────┘ │
│                                                                         │
│  Connection Pool: asyncpg pool_size=50, PgBouncer phía trước           │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3. Luồng Request/Response chi tiết

```
┌──────┐          ┌──────────┐          ┌─────────────┐          ┌──────────┐         ┌──────────────┐
│Client│          │API GW    │          │Redis        │          │Worker    │         │PostgreSQL    │
└──┬───┘          └────┬─────┘          └──────┬──────┘          └────┬─────┘         └──────┬───────┘
   │                   │                      │                      │                      │
   │  POST /agent      │                      │                      │                      │
   │  {threadId,       │                      │                      │                      │
   │   runId,          │                      │                      │                      │
   │   messages}       │                      │                      │                      │
   ├──────────────────►│                      │                      │                      │
   │                   │                      │                      │                      │
   │                   │  XADD agent:requests  │                      │                      │
   │                   │  {runId, payload...}  │                      │                      │
   │                   ├─────────────────────►│                      │                      │
   │                   │                      │                      │                      │
   │  202 Accepted     │                      │                      │                      │
   │  SSE URL          │                      │                      │                      │
   │◄──────────────────┤                      │                      │                      │
   │                   │                      │                      │                      │
   │                   │  SUB agent:events:   │                      │                      │
   │                   │      {runId}         │                      │                      │
   │                   ├─────────────────────►│                      │                      │
   │                   │                      │                      │                      │
   │                   │                      │  XREADGROUP          │                      │
   │                   │                      │  agent-workers       │                      │
   │                   │                      │◄─────────────────────┤                      │
   │                   │                      ├──────────────────────►│                      │
   │                   │                      │                      │                      │
   │                   │                      │                      │  aget_state()         │
   │                   │                      │                      ├─────────────────────►│
   │                   │                      │                      │◄─────────────────────┤
   │                   │                      │                      │                      │
   │                   │                      │                      │  astream_events()     │
   │                   │                      │                      │  (LLM + tools)        │
   │                   │                      │                      │  │                    │
   │                   │                      │                      │  ├── checkpoint       │
   │                   │                      │                      │  │   (sau mỗi node)   │
   │                   │                      │                      │  ├──────────────────► │
   │                   │                      │                      │  │                    │
   │                   │                      │  PUBLISH             │  │                    │
   │                   │                      │  agent:events:{rid}  │  │                    │
   │                   │                      │  TEXT_MESSAGE_START │◄─┤                    │
   │                   │◄─────────────────────┤                      │  │                    │
   │                   │                      │                      │  │                    │
   │  SSE:             │                      │  PUBLISH             │  │                    │
   │  TEXT_MESSAGE_    │                      │  TEXT_MESSAGE_       │  │                    │
   │  CONTENT "Hello"  │                      │  CONTENT "Hello"    │◄─┤                    │
   │◄──────────────────┤◄─────────────────────┤                      │  │                    │
   │                   │                      │                      │  │                    │
   │  SSE:             │                      │  PUBLISH             │  │                    │
   │  TEXT_MESSAGE_END │                      │  TEXT_MESSAGE_END   │◄─┤                    │
   │◄──────────────────┤◄─────────────────────┤                      │  │                    │
   │                   │                      │                      │  │                    │
   │  SSE:             │                      │  PUBLISH             │  │                    │
   │  RUN_FINISHED     │                      │  RUN_FINISHED       │◄─┤                    │
   │◄──────────────────┤◄─────────────────────┤                      │  │                    │
   │                   │                      │                      │  │                    │
   │                   │  UNSUBSCRIBE         │                      │  │                    │
   │                   ├─────────────────────►│                      │  │                    │
   │                   │                      │                      │  │                    │
   │                   │                      │  XACK                │  │                    │
   │                   │                      │  (ack complete)      │◄─┤                    │
   │                   │─────────────────────►│                      │  │                    │
```

## 4. Component Details

### 4.1 API Gateway (FastAPI)

| Property | Value |
|---|---|
| Framework | FastAPI + uvicorn |
| Workers | 8-16 per machine (gunicorn) |
| Instances | 3-5 sau Nginx LB |
| Connection/instance | ~2000-5000 concurrent SSE |
| Memory/instance | ~200-500MB |

```
API Gateway responsibilities:
  1. Validate RunAgentInput
  2. Push request → Redis Stream "agent:requests"
  3. Return 202 + subscribe Redis Pub/Sub "agent:events:{runId}"
  4. Relay events → SSE response
  5. Handle disconnect → cleanup Redis subscription
```

### 4.2 Redis (Event Bus)

| Property | Value |
|---|---|
| Stream | `agent:requests` (Consumer Groups) |
| Pub/Sub | `agent:events:{runId}` (per-channel) |
| Max Pending | 10000 (backpressure) |
| Cleanup | TTL 1h trên pub/sub channels |

```
Redis responsibilities:
  1. Request queue với backpressure
  2. Event relay từ Worker → API Gateway
  3. Lock/mutex cho idempotency
```

### 4.3 Agent Worker (Python)

| Property | Value |
|---|---|
| Runtime | Python process (consumes queue) |
| Concurrency | 10-20 async runs / worker |
| Memory | ~200MB / worker |
| Scale | 20-50 workers (auto-scale based on queue depth) |

```
Worker responsibilities:
  1. XREADGROUP from "agent:requests"
  2. LangGraphAgent.run() với PostgresSaver
  3. PUBLISH từng AG-UI event → Redis
  4. XACK khi run complete
  5. Graceful shutdown: finish current run, then exit
```

### 4.4 PostgreSQL

| Property | Value |
|---|---|
| Checkpointer | `AsyncPostgresSaver` (langgraph-checkpoint-postgres) |
| Pool | asyncpg pool_size=50, PgBouncer frontend |
| Tables | langgraph_checkpoints, langgraph_writes (auto) |

## 5. Deployment Topology

```
Internet
    │
    ▼
┌──────────────────────────────────────────────────┐
│              Cloudflare / CDN                      │
│         DDoS protection, SSL termination           │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│              Nginx Load Balancer                   │
│         Round Robin, Rate Limit, Access Log        │
└──────┬──────────────────────┬────────────────────┘
       │                      │
       ▼                      ▼
┌──────────────┐    ┌──────────────┐
│   Machine 1   │    │   Machine 2   │     ... Machine N
│              │    │              │
│ API GW ×8    │    │ API GW ×8    │    Stateless, chạy nhiều
│ Worker ×10   │    │ Worker ×10   │    hoặc tách riêng
└──────┬───────┘    └──────┬───────┘
       │                   │
       └────────┬──────────┘
                │
                ▼
       ┌──────────────────┐
       │  Redis Cluster    │
       │  (3 master + 3   │
       │   replica)        │
       └──────────────────┘
                │
                ▼
       ┌──────────────────┐
       │  PostgreSQL       │
       │  (Primary +       │
       │   Replica for     │
       │   read)           │
       └──────────────────┘
```

## 6. Scaling Numbers

| Scenario | Users | Concurrent Runs | API GW | Workers | Redis QPS | PG Connections |
|---|---|---|---|---|---|---|
| Light | 1,000 | ~20 | 1 × 8 | 3 | 5/s | 20 |
| Medium | 5,000 | ~100 | 2 × 8 | 10 | 25/s | 50 |
| Heavy | 10,000 | ~200 | 3 × 8 | 20 | 50/s | 80 |
| Peak | 10,000 | ~500 | 5 × 8 | 50 | 125/s | 150 |

> **Concurrent runs = Users × (Avg response time / Avg think time)**
>
> User gõ 1 message mỗi 30s, LLM trả lời trong 5s:
> 10,000 × (5/30) = ~1,667 concurrent runs (peak worst case)
>
> Nhưng do cache + repeat questions + idle users, con số thực tế ~200-500.

## 7. Error Handling

```
Worker crash:
  ┌─ Redis pending entries không bị XACK
  └─ Consumer groups auto-redeliver sau timeout
  └─ Worker khác pick up → đảm bảo at-least-once

API Gateway crash:
  ┌─ Client nhận 502 / connection reset
  └─ Client retry với cùng threadId + messages
  └─ Worker có thể đã xử lý (check threadId trong queue trùng)

LLM API timeout:
  ┌─ Worker catch timeout → publish RUN_ERROR via Redis
  └─ API GW relay error event → client thấy lỗi
  └─ Worker XACK (vẫn đánh dấu done) → không retry
```

## 8. Implementation Priority

```
Phase 1 (Ngay bây giờ):
  └─ PostgresSaver cho checkpointing (thay MemorySaver)

Phase 2 (Tuần này):
  └─ Redis stream cho request queue
  └─ Agent Worker (consumer)
  └─ API Gateway relay SSE từ Redis

Phase 3 (Tuần sau):
  └─ Graceful shutdown workers
  └─ Health check + liveness probe
  └─ Dockerfile + docker-compose
  └─ Nginx config + rate limiting

Phase 4 (Sau):
  └─ Auto-scaling (K8s / Nomad)
  └─ Monitoring (Prometheus + Grafana)
  └─ Distributed tracing (OpenTelemetry)
  └─ A/B testing multiple agent versions
```
