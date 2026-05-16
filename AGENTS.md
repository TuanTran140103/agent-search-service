# Agent Guidance

## Project Overview

Python 3.12 project using LangGraph + AG-UI protocol + FastAPI. Package lives under `src/`.

## Entrypoints

- **API server**: `python main.py` — runs `src.api.server:app` (gunicorn with uvicorn workers; falls back to uvicorn on Windows)
- **Background worker**: `python -m src.worker_main` — separate worker process for queue consumption
- **Root `main.py`** is a stub; all real code is under `src/`

## Infrastructure Prerequisites

- **PostgreSQL** (required by `langgraph.json` checkpointer): `postgresql://postgres:postgres@localhost:5432/lm_agent`
- **Redis** (optional, used when `QUEUE_BACKEND=redis` or `RATE_LIMIT_BACKEND=redis`): `redis://localhost:6379/0`

## Setup

```bash
cp .env.example .env
# Edit .env: set LLM_API_KEY at minimum (OPENAI_API_KEY maps to LLM_API_KEY in config)
uv sync
```

## Running

```bash
# API server (port 8000)
uv run python -m src.main

# Worker (separate terminal)
uv run python -m src.worker_main
```

When `QUEUE_BACKEND=inprocess` (default), the worker starts inline with the API server via `lifespan` in `src/api/server.py:42`.

## Testing

```bash
uv run pytest tests/
```

## Key Config (`src/core/config.py`)

| Variable | Default | Notes |
|---|---|---|
| `LLM_API_KEY` | — | Required (set via `OPENAI_API_KEY` env var) |
| `QUEUE_BACKEND` | `inprocess` | `redis` for distributed |
| `RATE_LIMIT_BACKEND` | `memory` | `redis` for distributed |
| `DATABASE_URI` | `postgresql://.../lm_agent` | LangGraph checkpointer |
| `LOG_LEVEL` | `INFO` | |

## Architecture

- `src/api/server.py:app` — FastAPI app, handles `/agent` (SSE streaming), `/threads`, `/health`
- `src/agent/graph.py` — LangGraph agent graph (`langgraph.json` references `./src/agent/graph.py:graph`)
- `src/graph_builder.py` — Graph definition, nodes: `agent` → `human_approval` → `tool_node`
- `src/agent/nodes/agent.py` — Single `agent_node` with both chat + search tools; routes to `human_approval` if tool_calls, else END
- `src/agent/nodes/human_approval.py` — Human-in-the-loop approval before tool execution
- `src/agent/nodes/supervisor.py` — unused (legacy)
- `src/agent/nodes/chat.py` — unused (legacy)
- `src/queue/` — `inprocess.py` or `redis.py` message queue backend
- `src/ratelimit/` — `memory.py` or `redis_impl.py` rate limiter
- DI container: `src/container.py`
- LLM provider agnostic via `ChatOpenAI` + `base_url`; config in `.env` (`LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`)

## Graph Flow

```
START → agent (chat + search tools)
  ├──→ (no tool_calls) → END
  └──→ (tool_calls) → human_approval
                        ├──→ (approve) → tool_node → agent
                        └──→ (reject) → agent
```

No supervisor overhead. Single agent call per user message. Tools only invoked when needed.