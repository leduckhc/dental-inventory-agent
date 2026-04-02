# Architecture: Conversational AI Dental Agent

## Overview

A conversational AI agent built with LangGraph/LangChain, featuring layered guardrails, real-time streaming of agent reasoning, and a split-panel chat UI. Designed for dental/medical domain use cases with appropriate safety, privacy, and compliance controls.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  Next.js + Auth Provider (Clerk/Auth0)                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │  Chat Panel   │ │Thinking Panel│ │ Consent Banner       ││
│  └──────────────┘ └──────────────┘ └──────────────────────┘│
└───────────────────────┬─────────────────────────────────────┘
                        │ SSE + JWT Bearer token
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     API Gateway / Middleware                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Auth     │ │ Rate     │ │ Request  │ │ CORS / HTTPS  │  │
│  │ (JWT)    │ │ Limiter  │ │ Logging  │ │               │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LangGraph Agent                          │   │
│  │                                                       │   │
│  │  ┌─────────┐   ┌──────────┐   ┌─────────────────┐   │   │
│  │  │ Input   │──►│ Reasoning│──►│ Tool Execution  │   │   │
│  │  │ Guard   │   │ (+ retry │   │ (+ timeout      │   │   │
│  │  │ (PII,   │   │  + timeout)│  │  + allowlist)   │   │   │
│  │  │ inject) │   └──────────┘   └────────┬────────┘   │   │
│  │  └────┬────┘                           │            │   │
│  │       │ blocked                        ▼            │   │
│  │       ▼           ┌─────────────────────────────┐   │   │
│  │  ┌─────────┐      │ Output Guard               │   │   │
│  │  │ Block   │      │ (toxicity, PII leakage,    │   │   │
│  │  │ Response│      │  hallucination check)       │   │   │
│  │  └─────────┘      └─────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────┐  ┌────────────────────────────────┐   │
│  │ Structured       │  │ OpenTelemetry Instrumentation  │   │
│  │ Logging          │  │ (traces per request + LLM call)│   │
│  │ (structlog/JSON) │  │                                │   │
│  └────────┬────────┘  └──────────────┬─────────────────┘   │
└───────────┼──────────────────────────┼──────────────────────┘
            ▼                          ▼
┌───────────────────┐    ┌──────────────────────────────────┐
│ Log Aggregator    │    │ Observability                     │
│ (ELK / CloudWatch │    │ ┌───────────┐ ┌───────────────┐  │
│  / Loki)          │    │ │ Prometheus│ │ LangSmith /   │  │
└───────────────────┘    │ │ + Grafana │ │ LangFuse      │  │
                         │ └───────────┘ └───────────────┘  │
                         └──────────────────────────────────┘
            ┌──────────────────────────────┐
            │ Persistence                   │
            │ ┌──────────┐ ┌─────────────┐ │
            │ │ PostgreSQL│ │ Redis       │ │
            │ │ (state,   │ │ (rate limit,│ │
            │ │  threads, │ │  sessions)  │ │
            │ │  audit)   │ │             │ │
            │ └──────────┘ └─────────────┘ │
            └──────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Agent framework** | LangGraph, LangChain | Stateful agent graph, LLM wrappers, tool integrations |
| **Backend API** | FastAPI, Uvicorn | Streaming HTTP server with SSE |
| **Guardrails** | NeMo Guardrails + custom | Input/output safety checks |
| **Frontend** | Next.js 14+ (App Router) | Chat UI with real-time thinking panel |
| **UI components** | Tailwind CSS, shadcn/ui | Styling and component library |
| **Streaming SDK** | Vercel AI SDK (`ai`) | First-class SSE/streaming support on the frontend |
| **Auth** | OAuth 2.0 / OIDC (Auth0, Clerk, or Keycloak) | Identity and access management |
| **Persistence** | PostgreSQL | Conversation state, threads, audit trail |
| **Caching / Rate Limiting** | Redis | Session store, per-user rate limits |
| **Logging** | structlog (JSON) | Structured, context-rich application logs |
| **Metrics** | Prometheus + Grafana | Request, token, guardrail, and error metrics |
| **Tracing** | OpenTelemetry | Distributed traces across API and agent nodes |
| **LLM Observability** | LangSmith or LangFuse | Prompt versioning, cost tracking, conversation replay |

---

## Project Structure

```
ai-dental-agent/
├── backend/
│   ├── pyproject.toml                # Python dependencies
│   ├── app/
│   │   ├── main.py                   # FastAPI app, streaming endpoint, middleware
│   │   ├── agent/
│   │   │   ├── graph.py              # LangGraph state machine definition
│   │   │   ├── nodes.py              # Individual node functions
│   │   │   ├── state.py              # AgentState TypedDict
│   │   │   └── tools.py              # Tool definitions and allowlists
│   │   ├── guardrails/
│   │   │   ├── input_guard.py        # Input validation (PII, injection, topic)
│   │   │   ├── output_guard.py       # Output validation (toxicity, hallucination)
│   │   │   └── config/               # NeMo Guardrails YAML configs
│   │   ├── auth/
│   │   │   ├── jwt.py                # JWT verification and user extraction
│   │   │   └── permissions.py        # Role-based tool/feature access
│   │   ├── middleware/
│   │   │   ├── logging.py            # Request logging middleware
│   │   │   ├── rate_limit.py         # Per-user rate limiting
│   │   │   └── error_handler.py      # Global exception handling
│   │   ├── observability/
│   │   │   ├── metrics.py            # Prometheus metric definitions
│   │   │   └── tracing.py            # OpenTelemetry setup
│   │   ├── config.py                 # pydantic-settings configuration
│   │   └── schemas.py                # Pydantic request/response models
│   └── tests/
│       ├── test_nodes.py             # Unit tests for individual agent nodes
│       ├── test_graph.py             # Integration tests for full graph execution
│       ├── test_guardrails.py        # Guardrail edge case tests
│       └── test_streaming.py         # SSE streaming contract tests
├── frontend/
│   ├── package.json
│   ├── app/
│   │   ├── layout.tsx                # Root layout with auth provider
│   │   ├── page.tsx                  # Main chat page
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx         # Message list and input
│   │   │   ├── ThinkingPanel.tsx     # Real-time agent reasoning display
│   │   │   ├── MessageBubble.tsx     # Individual message rendering
│   │   │   └── ConsentBanner.tsx     # AI-generated content disclaimer
│   │   └── hooks/
│   │       └── useStreamingChat.ts   # SSE streaming hook
│   └── tailwind.config.ts
├── docker-compose.yml                # Local dev: app + postgres + redis
└── README.md
```

---

## Agent Graph Design

The agent is modeled as a LangGraph state machine. Each node performs a single responsibility, and conditional edges control routing.

### State Definition

```python
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    thinking: Annotated[list[str], operator.add]
    guardrail_flags: dict
    thread_id: str
    user_id: str
```

### Graph Topology

```
                    ┌───────────────┐
        ┌──────────│ entry_point    │
        │          └───────┬───────┘
        │                  ▼
        │          ┌───────────────┐
        │          │ input_guard   │
        │          └───────┬───────┘
        │                  │
        │          ┌───────┴───────┐
        │          │ conditional   │
        │          │ should_block? │
        │          └──┬─────────┬──┘
        │    blocked  │         │  allowed
        │             ▼         ▼
        │  ┌──────────────┐  ┌─────────────────┐
        │  │blocked_resp  │  │ agent_reasoning  │◄──┐
        │  └──────┬───────┘  └────────┬────────┘   │
        │         │                   │             │
        │         │          ┌────────┴────────┐    │
        │         │          │ conditional     │    │
        │         │          │ needs_tool?     │    │
        │         │          └──┬───────────┬──┘    │
        │         │    yes      │           │  no   │
        │         │             ▼           │       │
        │         │   ┌─────────────────┐   │       │
        │         │   │ tool_executor   │───┘       │
        │         │   └─────────────────┘  (loops   │
        │         │                        back)    │
        │         │             ┌────────────────┐  │
        │         │             │ output_guard   │  │
        │         │             └───────┬────────┘  │
        │         │                     │           │
        │         ▼                     ▼           │
        │       ┌─────────────────────────┐        │
        └──────►│          END            │        │
                └─────────────────────────┘
```

### Recursion Limit

The graph is compiled with `recursion_limit=25` to prevent infinite loops between reasoning and tool execution.

---

## Guardrails Strategy

Safety is enforced at multiple layers, not as an afterthought.

### Layered Guardrail Model

| Layer | Location | Checks | Implementation |
|-------|----------|--------|----------------|
| **Input Guardrail** | Before agent reasoning | Prompt injection detection, PII detection, off-topic/blocked topic filtering | NeMo Guardrails + custom regex classifiers |
| **Tool Guardrail** | Conditional edge before tool execution | Tool allowlist per user role, rate limiting on tool calls | LangGraph conditional edges + role-based allowlist |
| **Output Guardrail** | After agent reasoning, before response | Toxicity filtering, PII leakage prevention, hallucination check | LLM-as-judge or Guardrails AI validators |
| **Token Limits** | LLM configuration | Prevents runaway cost | `max_tokens` on LLM + LangGraph `recursion_limit` |

### Guardrail Configuration (NeMo)

Guardrail policies are defined in YAML and loaded at startup. Topic blocklists, canonical forms, and dialog flows are version-controlled alongside application code.

---

## Streaming Architecture

Real-time visibility into agent reasoning is achieved through Server-Sent Events (SSE).

### Why SSE over WebSocket

- Simpler -- unidirectional from server to client is sufficient for chat streaming
- LangGraph natively supports SSE via `astream_events`
- No connection upgrade negotiation overhead
- Automatic reconnection built into the browser `EventSource` API

### Event Protocol

The streaming endpoint emits JSON events over SSE with the following types:

| Event Type | Payload | Description |
|-----------|---------|-------------|
| `thinking` | `{ content: string }` | Agent reasoning step (node entry, guardrail result, tool decision) |
| `token` | `{ content: string }` | Single token from the LLM response stream |
| `tool_call` | `{ name: string, args: object }` | Tool invocation details |
| `tool_result` | `{ name: string, result: string }` | Tool execution result |
| `error` | `{ message: string }` | Recoverable error during processing |
| `done` | `{}` | Stream complete |

### Streaming Implementation

LangGraph's `astream_events(version="v2")` provides granular events for every node entry, LLM token, and tool call. These are mapped to the event types above and sent as SSE to the frontend.

For models that support extended thinking (e.g., Anthropic Claude), the model's internal chain-of-thought is surfaced as `thinking` events, providing genuine reasoning visibility rather than just execution trace.

---

## Authentication & Authorization

### Identity

- OAuth 2.0 / OIDC via Auth0, Clerk, or Keycloak
- JWT tokens issued on login, attached as `Bearer` token to every API request
- Frontend auth provider wraps the application and handles token refresh

### API Authentication

- FastAPI `Depends()` middleware validates JWT signature, expiry, and audience on every request
- `thread_id` is scoped to the authenticated user -- cross-user thread access is rejected with 403

### Role-Based Access

- User roles determine which agent tools are available (e.g., admin users can access data export tools, regular users cannot)
- Rate limits are enforced per-user via Redis-backed counters

---

## Logging

### Principles

- **Structured JSON logs** via `structlog` -- every log entry is machine-parseable
- **Context propagation** -- `request_id`, `user_id`, and `thread_id` are bound to every log entry via `contextvars`
- **PII redaction** -- raw user messages and LLM responses are NEVER logged in production; only redacted summaries or metadata

### Log Levels by Layer

| Layer | Log Level | What's Logged |
|-------|-----------|--------------|
| Request middleware | INFO | Method, path, status, latency |
| Agent node entry/exit | INFO | Node name, duration, tokens used |
| Guardrail decisions | INFO/WARN | Check type, pass/fail, reason (redacted) |
| LLM calls | INFO | Model, prompt/completion tokens, latency, cost estimate |
| Tool execution | INFO | Tool name, duration, success/failure |
| Errors | ERROR | Stack trace, node where failure occurred, partial state |

### Log Aggregation

Logs are shipped to a centralized aggregator (ELK, CloudWatch, or Grafana Loki) for search, alerting, and dashboarding.

---

## Observability & Monitoring

### Three Pillars

```
Metrics (Prometheus)     Traces (OpenTelemetry)     LLM Observability (LangSmith/LangFuse)
        │                        │                              │
        └────────────────────────┴──────────────────────────────┘
                                 │
                            Grafana Dashboards
```

### Key Metrics (Prometheus)

| Metric | Type | Description |
|--------|------|-------------|
| `agent_request_total` | Counter | Total requests by status |
| `agent_request_duration_seconds` | Histogram | End-to-end request latency |
| `llm_tokens_total{type=prompt\|completion}` | Counter | Token usage for cost tracking |
| `guardrail_blocked_total{guard=input\|output}` | Counter | Blocked requests by guardrail type |
| `agent_error_total{node=...}` | Counter | Errors by graph node |
| `tool_call_duration_seconds{tool=...}` | Histogram | Per-tool execution latency |
| `active_streams` | Gauge | Currently open SSE connections |

### Distributed Tracing (OpenTelemetry)

Each request generates a trace with spans for:
- HTTP request handling
- Each LangGraph node execution
- Each LLM API call
- Each tool invocation

### LLM-Specific Observability (LangSmith / LangFuse)

- Prompt version tracking
- Per-conversation token costs
- Conversation replay and debugging
- Quality scoring and A/B prompt testing
- Enabled via environment variables (`LANGCHAIN_TRACING_V2=true`)

---

## Error Handling & Resilience

### Agent-Specific Failure Modes

| Failure | Mitigation |
|---------|-----------|
| **LLM timeout** (>30s reasoning) | `asyncio.wait_for` with 60s timeout per node; graceful fallback message |
| **LLM rate limit** (429) | Exponential backoff retry (3 attempts, 1-10s wait) via `tenacity` |
| **Tool failure** (external API down) | Per-tool timeout; error captured in state, agent can reason about failure |
| **Infinite loop** (agent cycles between reasoning and tools) | `recursion_limit=25` on graph compilation |
| **Context overflow** (conversation exceeds context window) | Token counting per turn; automatic conversation summarization or truncation |
| **Malformed LLM output** (unparseable tool call) | Output parsing with fallback; retry with simplified prompt |

### Global Error Handler

A FastAPI exception handler catches unhandled errors, logs them with full context, and returns a safe generic error message to the client. The SSE stream emits an `error` event so the frontend can display a user-friendly message.

---

## Data Privacy & Compliance

Especially relevant given the dental/medical domain.

| Concern | Approach |
|---------|---------|
| **PII in prompts** | Input guardrail detects and redacts PII (names, SSNs, health records) before sending to LLM |
| **Data residency** | LLM API calls routed to region-specific endpoints (e.g., Azure OpenAI in-region) if HIPAA/GDPR applies |
| **Conversation storage** | Encrypted at rest (AES-256); retention policy with automatic purge; right-to-deletion support |
| **Audit trail** | Immutable log of who asked what, when, and what the agent responded (stored separately from application logs) |
| **User consent** | Frontend displays a consent banner acknowledging AI-generated content is not medical advice |

---

## Configuration Management

All configuration is externalized via environment variables and validated at startup using `pydantic-settings`.

### Key Configuration Groups

| Group | Variables | Defaults |
|-------|----------|----------|
| **LLM** | `AGENT_LLM_PROVIDER`, `AGENT_LLM_MODEL`, `AGENT_LLM_TEMPERATURE`, `AGENT_LLM_MAX_TOKENS`, `AGENT_LLM_TIMEOUT_SECONDS` | `openai`, `gpt-4o`, `0.1`, `4096`, `60` |
| **Guardrails** | `AGENT_GUARDRAIL_ENABLED`, `AGENT_GUARDRAIL_INPUT_CHECKS`, `AGENT_GUARDRAIL_OUTPUT_CHECKS` | `true`, `[pii, injection, topic]`, `[toxicity, pii_leakage]` |
| **Auth** | `AGENT_JWT_SECRET`, `AGENT_JWT_ALGORITHM`, `AGENT_JWT_AUDIENCE` | -, `RS256`, `dental-agent` |
| **Limits** | `AGENT_MAX_CONVERSATION_TURNS`, `AGENT_MAX_TOKENS_PER_CONVERSATION`, `AGENT_RATE_LIMIT_PER_USER_PER_MINUTE` | `50`, `100000`, `20` |
| **Observability** | `AGENT_LANGSMITH_ENABLED`, `AGENT_LOG_LEVEL` | `true`, `INFO` |

---

## Frontend Architecture

### UI Layout

Split-panel design with chat on the left and live agent reasoning on the right.

```
┌──────────────────────────────────────────────┐
│                  Header                       │
├────────────────────────┬─────────────────────┤
│                        │   Thinking Panel     │
│    Chat Panel          │   ┌───────────────┐  │
│                        │   │ > Input check  │  │
│   User: Hi there       │   │ > Reasoning... │  │
│   Bot:  Hello! ...     │   │ > Tool: search │  │
│                        │   │ > Output check │  │
│   [  Type a message  ] │   └───────────────┘  │
└────────────────────────┴─────────────────────┘
```

### Streaming Consumption

The frontend reads the SSE stream and routes events to two separate render targets:
- `thinking` events → Thinking Panel (appended with animation)
- `token` events → Chat Panel (progressive text rendering)
- `done` event → Marks streaming complete, re-enables input

### Auth Integration

The auth provider (Clerk/Auth0) wraps the app layout. JWT tokens are automatically attached to API requests. Unauthenticated users are redirected to login.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Streaming transport** | SSE over WebSocket | Simpler, LangGraph native support, sufficient for unidirectional chat streaming |
| **Guardrails library** | NeMo Guardrails + custom | NeMo for topic control and dialog management; custom for PII detection and prompt injection |
| **Thinking visibility** | `astream_events` (v2) | Most granular: exposes node transitions, individual LLM tokens, and tool calls |
| **State persistence** | PostgreSQL (production), MemorySaver (dev) | PostgreSQL for durability and multi-instance support; in-memory for fast local development |
| **LLM provider** | OpenAI or Anthropic (configurable) | Both supported via LangChain abstractions; Anthropic preferred when extended thinking visibility is desired |
| **Frontend framework** | Next.js 14+ App Router | SSR for initial load, React Server Components for auth, excellent streaming support |
| **API versioning** | URL prefix (`/v1/chat/stream`) | Simple, explicit, easy to deprecate |

---

## Health Checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe -- returns 200 if the process is running |
| `GET /ready` | Readiness probe -- returns 200 if LLM connection is established, DB is reachable, and guardrails are loaded |

---

## Dependencies

### Backend (`pyproject.toml`)

```toml
[project]
dependencies = [
    "langgraph",
    "langchain",
    "langchain-openai",
    "langchain-anthropic",
    "fastapi",
    "uvicorn",
    "nemoguardrails",
    "pydantic>=2.0",
    "pydantic-settings",
    "structlog",
    "prometheus-client",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-instrumentation-fastapi",
    "redis",
    "psycopg[binary]",
    "tenacity",
    "python-jose[cryptography]",
]
```

### Frontend (`package.json`)

```json
{
  "dependencies": {
    "next": "^15",
    "react": "^19",
    "react-dom": "^19",
    "tailwindcss": "^4",
    "ai": "^4",
    "@clerk/nextjs": "^6"
  }
}
```
