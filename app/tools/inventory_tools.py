"""LangChain tools exposed to the LangGraph agent.

Tool inputs are validated by Pydantic. Guardrails are NOT tools — they are
Python functions called inside the repository layer. The LLM cannot bypass them.

Tools:
  query_knowledge   — RAG over med_info.txt
  get_inventory     — read all stock levels
  search_inventory  — fuzzy name search (disambiguation)
  update_stock      — order / receive stock (Rule 1 & 2 enforced)
  consume_stock     — record usage (negative-stock check enforced)
"""

from langchain_core.tools import tool
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.repository import (
    get_all_items,
    search_items,
)
from app.db.repository import (
    update_stock as repo_update_stock,
)
from app.models.domain import StockUpdateInput
from app.rag.index import SIMILARITY_THRESHOLD, query_knowledge_base

# Sessions are injected at agent build time via closure. See agent/graph.py.
_inv_session = None
_audit_session = None


def set_sessions(inv_session: Session, audit_session: Session) -> None:
    global _inv_session, _audit_session
    _inv_session = inv_session
    _audit_session = audit_session


# ── RAG ──────────────────────────────────────────────────────────────────────


@tool
def query_knowledge(query: str) -> str:
    """Answer questions about dental materials, medications, contraindications,
    and storage requirements using the clinic's knowledge base (med_info.txt).

    Use this tool when the user asks about:
    - What a substance is used for
    - Contraindications or precautions
    - Storage conditions
    - Differences between two products
    - Safety warnings

    Do NOT use this tool for inventory or stock questions.
    """
    context, score = query_knowledge_base(query)

    if not context or score < SIMILARITY_THRESHOLD:
        return (
            "I don't have information about this topic in the clinic's knowledge base. "
            "Please consult a pharmacist or the product's official documentation."
        )

    return f"Based on the clinic's medical reference (med_info.txt):\n\n{context}\n\n[Relevance score: {score:.2f}]"


# ── Inventory reads ───────────────────────────────────────────────────────────


@tool
def get_inventory() -> str:
    """Show the current stock levels for all items in the clinic inventory.

    Use this tool when the user asks to see stock, check what's available,
    or get an overview of current inventory.
    """
    items = get_all_items(_inv_session)
    if not items:
        return "Inventory is empty."

    lines = [f"{'ID':<6} {'Name':<45} {'Stock':>8} {'Unit':<8} {'Flags'}"]
    lines.append("-" * 80)
    for item in items:
        flags = []
        if item.attributes.flammable:
            flags.append("FLAMMABLE")
        if item.attributes.vasoconstrictor:
            flags.append("VASOCONSTRICTOR")
        flag_str = ", ".join(flags) if flags else "-"
        lines.append(f"{item.id:<6} {item.name:<45} {item.stock:>8} {item.unit:<8} {flag_str}")
    return "\n".join(lines)


@tool
def search_inventory(query: str) -> str:
    """Search the inventory by partial item name. Returns all matching items.

    Use this tool when:
    - The user says a generic name (e.g. 'alcohol', 'anesthetic') that could match
      multiple items
    - You need to find the item_id before calling update_stock or consume_stock
    - You are unsure which specific item the user means

    Returns a list of matches. If more than one item matches, ask the user to
    clarify which one they mean before proceeding.
    """
    matches = search_items(_inv_session, query)
    if not matches:
        return f"No items found matching '{query}'."

    if len(matches) == 1:
        item = matches[0]
        return f"Found 1 item: {item.id}  {item.name}  (stock: {item.stock} {item.unit})"

    lines = [
        f"AMBIGUOUS — {len(matches)} items match '{query}'.",
        "You MUST ask the user which item they mean before calling update_stock or consume_stock.",
        "Do NOT proceed with any item until the user specifies.",
        "",
        "Matching items:",
    ]
    for item in matches:
        lines.append(f"  {item.id}  {item.name}  (stock: {item.stock} {item.unit})")
    return "\n".join(lines)


# ── Inventory writes ──────────────────────────────────────────────────────────


@tool
def update_stock(item_id: str, quantity: int) -> str:
    """Order or receive stock for an existing inventory item.

    This tool ADDS quantity to the current stock level.
    Safety guardrails (flammable ≤10L, vasoconstrictor ≤20 packs) are enforced
    automatically — they cannot be overridden.

    Args:
        item_id: The inventory ID of the item (e.g. 'A101', 'D500').
                 Use search_inventory to find the correct ID if unsure.
        quantity: The amount to add. Must be a positive number.

    Returns a confirmation message or a rejection reason.
    """
    try:
        validated = StockUpdateInput(item_id=item_id, quantity=quantity, operation="add")
    except ValidationError as e:
        return f"Invalid input: {e}"

    result = repo_update_stock(_inv_session, _audit_session, validated.item_id, validated.quantity, "add")
    if result.allowed:
        return f"[SUCCESS] Added {validated.quantity} to {item_id}. Stock updated."
    return (
        f"[REJECTED] Cannot order {validated.quantity} of {item_id}.\n"
        f"Reason: {result.reason}\nRule: {result.rule_violated}"
    )


@tool
def consume_stock(item_id: str, quantity: int) -> str:
    """Record consumption of an inventory item (e.g. after a procedure).

    This tool SUBTRACTS quantity from the current stock level.
    Consumption is rejected if it would bring stock below zero.

    Args:
        item_id: The inventory ID of the item (e.g. 'A101', 'D500').
                 Use search_inventory to find the correct ID if unsure.
        quantity: The amount consumed. Must be a positive number.

    Returns a confirmation message or a rejection reason.
    """
    try:
        validated = StockUpdateInput(item_id=item_id, quantity=quantity, operation="consume")
    except ValidationError as e:
        return f"Invalid input: {e}"

    result = repo_update_stock(_inv_session, _audit_session, validated.item_id, validated.quantity, "consume")
    if result.allowed:
        return f"[SUCCESS] Consumed {validated.quantity} of {item_id}. Stock updated."
    return (
        f"[REJECTED] Cannot consume {validated.quantity} of {item_id}.\n"
        f"Reason: {result.reason}\nRule: {result.rule_violated}"
    )


ALL_TOOLS = [query_knowledge, get_inventory, search_inventory, update_stock, consume_stock]
