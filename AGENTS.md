# Agent Guidance

## Project Overview

Python 3.12 project using LangGraph + AG-UI protocol + FastAPI. Package lives under `src/`.

## Entrypoints

- **API server**: `python main.py` — runs `src.api.server:app` (gunicorn with uvicorn workers; falls back to uvicorn on Windows)
- **Background worker**: `python -m src.worker_main` — separate worker process that consumes Redis stream and runs agent

## Infrastructure Prerequisites

- **PostgreSQL** (required by `langgraph.json` checkpointer): `postgresql://postgres:postgres@localhost:5432/lm_agent`
- **Redis** (required for queue, rate limiter, and worker): `redis://localhost:6379/0`

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

## Testing

```bash
uv run pytest tests/
```

## Key Config (`src/core/config.py`)

| Variable | Default | Notes |
|---|---|---|
| `LLM_API_KEY` | — | Required (set via `OPENAI_API_KEY` env var) |
| `DATABASE_URI` | `postgresql://.../lm_agent` | LangGraph checkpointer |
| `REDIS_URI` | `redis://localhost:6379/0` | Queue + rate limiter + worker |
| `LOG_LEVEL` | `INFO` | |

## Architecture

```
                    ┌──────────────────┐
                    │   API Server      │  (server.py)
                    │  publishes to     │
                    │  Redis Stream     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   Redis Stream    │  (message bus)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │    Worker         │  (worker_main.py)
                    │  RedisStreamWorker│
                    │  consumes + runs  │
                    │  LangGraph agent  │
                    └──────────────────┘
```

- `src/api/server.py:app` — FastAPI app, handles `/agent` (SSE streaming via Redis pub/sub), `/threads`, `/health`
- `src/worker_main.py` — separate process running `RedisStreamWorker` that reads from Redis stream, runs agent, publishes events back via Redis pub/sub
- `src/agent/graph.py` — LangGraph agent graph (`langgraph.json` references `./src/agent/graph.py:graph`)
- `src/graph_builder.py` — Graph definition, nodes: `agent` → `human_approval` → `tool_node`
- `src/container.py` — DI container (dependency-injector), manages all dependencies

## Graph Flow

```
START → agent (chat + search tools)
  ├──→ (no tool_calls) → END
  └──→ (tool_calls) → human_approval
                        ├──→ (approve) → tool_node → agent
                        └──→ (reject) → agent
```

No supervisor overhead. Single agent call per user message. Tools only invoked when needed.
