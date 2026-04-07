# Architecture: AI Dental Inventory Agent

A CLI-based LangGraph ReAct agent for dental clinic inventory management. Deterministic Python guardrails enforce safety rules at the code level — they cannot be overridden by user input or prompt injection.

---

## System overview

```
stdin
  │
  ▼
main.py  ──────────────────────────────────────────────────────────
  │  CLI loop: reads user input, calls agent.invoke(), prints reply
  │
  ▼
app/agent/graph.py  (LangGraph ReAct graph)
  │
  │  START
  │    │
  │    ▼
  │  agent_node  ──────────────────────────────────────────────────
  │    │  ChatOpenAI → vLLM (Qwen3.5-9B)
  │    │  reasoning field isolated from content ← no <think> contamination
  │    │
  │    ├── no tool calls? ──────────────────────────────► END
  │    │
  │    └── tool calls?
  │          │
  │          ▼
  │        tool_node  (ToolNode prebuilt)
  │          │
  │          ├── query_knowledge(query)
  │          │     └── FAISS similarity search over med_info.txt
  │          │         (bge-base-en-v1.5, cached via @lru_cache)
  │          │
  │          ├── get_inventory()
  │          │     └── repository.get_all_items(inv_session)
  │          │
  │          ├── search_inventory(query)
  │          │     └── repository.search_items(inv_session, query)
  │          │         substring match on name OR category
  │          │
  │          ├── update_stock(item_id, quantity)   ┐
  │          │     └── StockUpdateInput (Pydantic)  │ validated first
  │          │         └── repository.update_stock() │
  │          │               ├── guardrails → reject │
  │          │               └── inv_session.commit()│
  │          │                   audit_session.commit│
  │          │                                       │
  │          └── consume_stock(item_id, quantity)   ┘
  │
  └── back to agent_node
```

---

## Component map

```
main.py                         CLI loop + session lifecycle
app/
├── agent/
│   └── graph.py                LangGraph graph, vLLM config, system prompt
├── tools/
│   └── inventory_tools.py      5 @tool functions; Pydantic input validation
├── guardrails/
│   └── checks.py               Pure Python safety rules (not tools)
├── db/
│   ├── schema.py               SQLAlchemy ORM: InventoryItemORM, AuditLogORM
│   ├── migrate.py              inventory.json → SQLite (upsert, re-runnable)
│   └── repository.py           DB reads/writes; two-session audit pattern
├── rag/
│   ├── loader.py               med_info.txt → 12 Documents (one per item)
│   └── index.py                FAISS index + query_knowledge_base()
└── models/
    └── domain.py               Pydantic: InventoryItem, StockUpdateInput, GuardrailResult
tests/
├── conftest.py                 In-memory SQLite fixture, seeded from inventory.json
├── test_guardrails.py          Guardrail correctness + audit log + DB state
├── test_pydantic.py            StockUpdateInput validation edge cases
└── test_repository.py          Read helper unit tests (get_item, search, category)
```

---

## Guardrail flow

Safety rules run synchronously in Python before any DB write. The LLM has no path to bypass them — they are not tools and are not in the prompt.

```
update_stock tool called
        │
        ▼
  StockUpdateInput  ──── invalid? ──► ValidationError → tool returns error string
  (Pydantic)
        │ valid
        ▼
  repository.update_stock(inv_session, audit_session, item_id, qty, op)
        │
        ├── item not found? ──────────────────────────────────────────┐
        │                                                              │
        ▼                                                              │
  run_all_guardrails(inv_session, item, qty, op)                       │
        │                                                              │
        │  consume → check_negative_stock()                           │
        │  add     → check_flammable_limit()                          │
        │            → check_vasoconstrictor_limit()                  │
        │                                                              │
        ├── REJECTED ────────────────────────────────────────────────►│
        │              [inv_session untouched]                         │
        │                                                              │
        ▼                                                              │
  inv_session.commit()   ← inventory written                           │
        │                                                              │
        ▼                                                              ▼
  _write_audit(audit_session, ..., SUCCESS)    _write_audit(audit_session, ..., REJECTED)
        │                                              │
        └──────────────────┬───────────────────────────┘
                           ▼
                  audit_session.commit()
                  (retry once on session error — Rule 3 guarantee)
```

---

## Two-session audit pattern

Rule 3 (`safety_regulation.txt`) requires logging every attempt, including rejections.

With a single session: a guardrail rejection triggers rollback → audit entry lost.

With two sessions:

```
inv_session    — inventory table; rolled back on guardrail failure
audit_session  — audit_logs table; always commits independently

Result: every attempt is logged, success or rejection, with no exceptions.
```

The `_write_audit` function retries once after a session rollback to handle transient session state errors. If the second attempt also fails, the exception propagates — failures are never swallowed silently.

---

## RAG pipeline

```
startup
  │
  └── app/rag/index.py: get_index()  [@lru_cache — called once]
        │
        ├── load_med_documents()     parse med_info.txt by numbered section
        │   → 12 Documents, one per item (semantic chunking preserves clinical context)
        │
        └── FAISS.from_documents(docs, HuggingFaceEmbeddings("BAAI/bge-base-en-v1.5"))
            normalize_embeddings=True, device=cpu

query_knowledge(query) tool call
  │
  └── query_knowledge_base(query, k=3)
        ├── similarity_search_with_score → top-3 chunks + L2 distances
        ├── convert to similarity: sim = 1 / (1 + dist)
        └── best_score < 0.4? → "I don't have information about this topic"
            best_score ≥ 0.4? → return combined context to LLM
```

Note: the similarity threshold (0.4) is calibrated to the `1/(1+dist)` formula, not raw cosine. Consistent throughout — the threshold can be tuned empirically.

---

## Data models

### SQLAlchemy ORM

```python
class InventoryItemORM(Base):
    id           String  PK        # e.g. "A101", "D500"
    name         String  NOT NULL
    category     String  NOT NULL  # "Anesthetics", "Disinfectants", ...
    stock        Integer NOT NULL
    unit         String  NOT NULL  # "packs", "liters", "tubes", "pcs"
    flammable    Boolean NOT NULL  # drives Rule 1 guardrail
    vasoconstrictor Boolean NOT NULL  # drives Rule 2 guardrail

class AuditLogORM(Base):
    id           Integer PK  autoincrement
    timestamp    DateTime    UTC
    action       String      "ADD" or "CONSUME"
    item_id      String
    item_name    String
    quantity     Integer
    status       String      "SUCCESS" or "REJECTED"
    reason       String?     populated on rejection
    rule_violated String?    e.g. "safety_regulation.txt Rule 1"
```

### Pydantic domain models

```python
class StockUpdateInput(BaseModel):
    item_id:   str = Field(pattern=r"^[A-Z][0-9]{3}$")  # e.g. A101, D500
    quantity:  int = Field(gt=0, strict=True)
    operation: Literal["add", "consume"]

class GuardrailResult(BaseModel):
    allowed:       bool
    reason:        Optional[str]    # human-readable rejection message
    rule_violated: Optional[str]    # e.g. "safety_regulation.txt Rule 1"
    current_total: int | None        # stock/total before the operation
    max_allowed:   int | None        # the limit that would be exceeded
```

---

## Safety rules

Defined in `safety_regulation.txt`, enforced in `app/guardrails/checks.py`.

| Rule | Limit | Applies to | Check |
|------|-------|-----------|-------|
| Rule 1 | Total flammable liquids ≤ 10L per room | `item.flammable = True`, operation = add | `SELECT SUM(stock) WHERE flammable = TRUE` |
| Rule 2 | Total vasoconstrictor anesthetics ≤ 20 packs | `item.vasoconstrictor = True`, operation = add | `SELECT SUM(stock) WHERE vasoconstrictor = TRUE` |
| Rule 3 | Every attempt logged | All operations | `_write_audit()` always called, success or rejection |
| implicit | Stock cannot go negative | operation = consume | `item.stock - quantity >= 0` |

Rule 1 note: the regulation specifies per-room. The current schema has no room field — the global sum is equivalent for a single-room clinic. `clinic_room_id` is listed in Future Extensions.

---

## vLLM / model configuration

Model: `Qwen/Qwen3.5-9B` on A100-PCIE-40GB.

```bash
vllm serve Qwen/Qwen3.5-9B \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --port 9000
```

Critical setting in `app/agent/graph.py`:

```python
ChatOpenAI(
    base_url=VLLM_BASE_URL,   # from .env: VLLM_BASE_URL
    model=MODEL_NAME,          # from .env: VLLM_MODEL
    temperature=0,             # deterministic tool selection
)
```

Qwen3.5 uses an XML tool call format (`<tool_call><function=name><parameter=key>value</parameter></function></tool_call>`) that requires `--tool-call-parser qwen3_coder`. The `hermes` parser (correct for Qwen2.5) does not understand this format and passes the raw XML through as plain text — tool calls appear in the chat output instead of executing.

`--reasoning-parser qwen3` separates the `<think>` tokens into the `reasoning` field. LangChain reads `content`, so the thinking chain never reaches the agent loop. No client-side `enable_thinking` flag is needed.

---

## Test strategy

All 31 tests run without a live LLM or network connection. The in-memory SQLite fixture in `conftest.py` seeds from `inventory.json` and gives each test a clean slate.

```
tests/test_guardrails.py  (16 tests)
  ├── Rule 1: flammable limit rejected, accepted at boundary, bypassed for non-flammable
  ├── Rule 2: vasoconstrictor limit rejected, accepted at boundary
  ├── Negative stock: consume beyond stock rejected, exact consumption accepted
  ├── Non-existent item: returns "not found" rejection
  ├── Unknown operation: run_all_guardrails defensive fallback
  └── Audit log: SUCCESS entry written, REJECTED entry written, stock unchanged after reject

tests/test_pydantic.py  (7 tests)
  ├── quantity = 0 → ValidationError
  ├── quantity < 0 → ValidationError
  ├── item_id = "INVALID" → ValidationError (pattern mismatch)
  ├── item_id = "a101" → ValidationError (lowercase)
  ├── operation = "order" → ValidationError (not Literal["add","consume"])
  └── valid add / valid consume → pass

tests/test_repository.py  (8 tests)
  ├── get_all_items: returns all 7 seeded items
  ├── get_item: found / not found
  ├── search_items: exact match, multiple matches, no match, case-insensitive
  └── search_items: category match ("anesthetic" → all 3 Anesthetics)
```

Coverage intentionally excludes RAG (requires 90MB model download) and tool layer (requires LLM). Those are integration-tested manually against the live vLLM server.

---

## Key design decisions

**Deterministic guardrails over prompt-based**
Prompt instructions can be overridden by injection. A Python function that runs before `inv_session.commit()` cannot be — it is not in the prompt. The guardrail logic is a SQL aggregate query and a numeric comparison.

**Two-session audit pattern over single session**
A single session would rollback the audit entry alongside the inventory transaction on guardrail failure. A separate `audit_session` that always commits independently guarantees Rule 3 regardless of inventory outcome.

**SQLite over a plain text audit log**
Rule 3 requires the log to be durable, queryable, and corruption-resistant. SQLite satisfies all three with no deployment overhead. Switching to PostgreSQL is a `make_engine()` one-liner (plus removing `connect_args`).

**Semantic chunking over fixed-token chunking**
Each item in `med_info.txt` is a clinical unit. Splitting at token boundaries can separate a contraindication from its drug name. Chunking by numbered section preserves complete clinical context in each vector.

**Category search in `search_items()`**
Product names like "Lidocaine", "Septanest", and "Ubistesin" don't contain the word "anesthetic". Extending substring search to also match `item.category` lets staff use generic terms for disambiguation without touching the tool interface.
