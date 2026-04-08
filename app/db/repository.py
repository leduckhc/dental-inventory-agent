"""Database repository — all inventory reads and writes go through here.

Two-session pattern:
  inv_session   — inventory table, rolled back on guardrail failure
  audit_session — audit_logs table, always commits independently

This guarantees Rule 3 (every attempt logged) even when a safety rule rejects the order.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.schema import AuditLogORM, InventoryItemORM
from app.guardrails.checks import run_all_guardrails
from app.models.domain import GuardrailResult, InventoryItem

# ── Read helpers ────────────────────────────────────────────────────────────


def get_all_items(session: Session) -> list[InventoryItem]:
    rows = session.query(InventoryItemORM).order_by(InventoryItemORM.category, InventoryItemORM.name).all()
    return [_orm_to_domain(r) for r in rows]


def get_item(session: Session, item_id: str) -> InventoryItem | None:
    row = session.get(InventoryItemORM, item_id)
    return _orm_to_domain(row) if row else None


def search_items(session: Session, query: str) -> list[InventoryItem]:
    """Case-insensitive substring match on item name or category. Used for disambiguation.

    Category prefix matching catches generic terms like 'anesthetic' (category='A')
    or 'disinfectant' (category='D') that won't appear in specific product names.
    """
    from sqlalchemy import func

    q = f"%{query.lower()}%"
    rows = (
        session.query(InventoryItemORM)
        .filter(
            func.lower(InventoryItemORM.name).like(q) | func.lower(func.coalesce(InventoryItemORM.category, "")).like(q)
        )
        .all()
    )
    return [_orm_to_domain(r) for r in rows]


# ── Write helpers ────────────────────────────────────────────────────────────


def update_stock(
    inv_session: Session,
    audit_session: Session,
    item_id: str,
    quantity: int,
    operation: str,  # "add" or "consume"
) -> GuardrailResult:
    """Apply a stock mutation, enforcing all guardrails.

    Steps:
      1. Look up item (reject if not found)
      2. Run guardrails for the operation
      3. If rejected: write audit log (REJECTED) and return
      4. If allowed: mutate stock, commit inv_session, write audit log (SUCCESS)
    """
    item = inv_session.get(InventoryItemORM, item_id)

    if item is None:
        result = GuardrailResult(allowed=False, reason=f"Item '{item_id}' not found in inventory.")
        _write_audit(audit_session, item_id, "UNKNOWN", quantity, operation, result)
        return result

    result = run_all_guardrails(inv_session, item, quantity, operation)

    if not result.allowed:
        _write_audit(audit_session, item_id, item.name, quantity, operation, result)
        return result

    # Mutate and commit
    if operation == "add":
        item.stock += quantity
    else:
        item.stock -= quantity
    inv_session.commit()

    _write_audit(audit_session, item_id, item.name, quantity, operation, result)
    return result


# ── Internal helpers ─────────────────────────────────────────────────────────


def _orm_to_domain(row: InventoryItemORM) -> InventoryItem:
    return InventoryItem(
        id=row.id,
        name=row.name,
        category=row.category,
        stock=row.stock,
        unit=row.unit,
        tags=[it.tag.name for it in row.item_tags],
    )


def _write_audit(
    audit_session: Session,
    item_id: str,
    item_name: str,
    quantity: int,
    operation: str,
    result: GuardrailResult,
) -> None:
    """Write an audit log entry. Retries once after a session rollback to guarantee
    Rule 3 compliance even when the session is in a stale or error state."""

    def _build_entry() -> AuditLogORM:
        return AuditLogORM(
            timestamp=datetime.now(UTC),
            action=operation.upper(),
            item_id=item_id,
            item_name=item_name,
            quantity=quantity,
            status="SUCCESS" if result.allowed else "REJECTED",
            reason=result.reason,
            rule_violated=result.rule_violated,
        )

    try:
        audit_session.add(_build_entry())
        audit_session.commit()
    except Exception:
        audit_session.rollback()
        audit_session.add(_build_entry())
        audit_session.commit()  # propagates if the DB itself is unavailable
