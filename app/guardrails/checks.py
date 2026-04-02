"""Deterministic code-level guardrails.

These are plain Python functions — NOT LangChain tools.
The LLM has no ability to skip or override them.
They are called synchronously inside the repository layer before any DB write.

Rules:
  Rule 1 (safety_regulation.txt): Total flammable liquids in clinic ≤ 10 liters
  Rule 2 (safety_regulation.txt): Total vasoconstrictor anesthetics ≤ 20 packs
  (implicit): Stock cannot go negative on consume
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.schema import InventoryItemORM
from app.models.domain import GuardrailResult

FLAMMABLE_LIMIT = 10.0  # liters — safety_regulation.txt Rule 1
VASOCONSTRICTOR_LIMIT = 20  # packs — safety_regulation.txt Rule 2


def check_flammable_limit(session: Session, item: InventoryItemORM, quantity: float) -> GuardrailResult:
    """Only applies when item.flammable is True and operation is 'add'."""
    if not item.flammable:
        return GuardrailResult(allowed=True)

    current = (
        session.query(func.sum(InventoryItemORM.stock))
        .filter(InventoryItemORM.flammable == True)  # noqa: E712
        .scalar()
    ) or 0.0

    projected = current + quantity
    if projected > FLAMMABLE_LIMIT:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Would bring total flammable stock to {projected:.1f}L, "
                f"exceeding the {FLAMMABLE_LIMIT:.0f}L limit. "
                f"Current total: {current:.1f}L. "
                f"You can add at most {max(0.0, FLAMMABLE_LIMIT - current):.1f}L more."
            ),
            rule_violated="safety_regulation.txt Rule 1",
            current_total=current,
            max_allowed=max(0.0, FLAMMABLE_LIMIT - current),
        )
    return GuardrailResult(allowed=True, current_total=current)


def check_vasoconstrictor_limit(session: Session, item: InventoryItemORM, quantity: float) -> GuardrailResult:
    """Only applies when item.vasoconstrictor is True and operation is 'add'."""
    if not item.vasoconstrictor:
        return GuardrailResult(allowed=True)

    current = (
        session.query(func.sum(InventoryItemORM.stock))
        .filter(InventoryItemORM.vasoconstrictor == True)  # noqa: E712
        .scalar()
    ) or 0

    projected = current + quantity
    if projected > VASOCONSTRICTOR_LIMIT:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Would bring total vasoconstrictor stock to {projected:.0f} packs, "
                f"exceeding the {VASOCONSTRICTOR_LIMIT} pack limit. "
                f"Current total: {current:.0f} packs. "
                f"You can order at most {max(0, VASOCONSTRICTOR_LIMIT - int(current))} more."
            ),
            rule_violated="safety_regulation.txt Rule 2",
            current_total=float(current),
            max_allowed=float(max(0, VASOCONSTRICTOR_LIMIT - int(current))),
        )
    return GuardrailResult(allowed=True, current_total=float(current))


def check_negative_stock(item: InventoryItemORM, quantity: float) -> GuardrailResult:
    """Prevents consuming more than what is in stock."""
    if item.stock - quantity < 0:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Insufficient stock: only {item.stock} {item.unit} of {item.name!r} available, "
                f"but attempted to consume {quantity} {item.unit}."
            ),
            rule_violated="Negative stock prevention",
            current_total=item.stock,
            max_allowed=item.stock,
        )
    return GuardrailResult(allowed=True, current_total=item.stock)


def run_all_guardrails(
    session: Session,
    item: InventoryItemORM,
    quantity: float,
    operation: str,
) -> GuardrailResult:
    """Run all applicable guardrails in priority order.

    consume: check negative stock first (fast, no DB query)
    add:     check flammable, then vasoconstrictor
    Returns the first failing result, or GuardrailResult(allowed=True).
    """
    if operation == "consume":
        return check_negative_stock(item, quantity)

    if operation == "add":
        result = check_flammable_limit(session, item, quantity)
        if not result.allowed:
            return result
        return check_vasoconstrictor_limit(session, item, quantity)

    return GuardrailResult(allowed=False, reason=f"Unknown operation: {operation!r}")
