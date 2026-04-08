"""Deterministic code-level guardrails.

These are plain Python functions — NOT LangChain tools.
The LLM has no ability to skip or override them.
They are called synchronously inside the repository layer before any DB write.

Rules are now data-driven: tag-based limits are stored in the safety_rules table.
Adding a new safety constraint requires only a new tag + rule row, not new code.

  (implicit): Stock cannot go negative on consume
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.schema import InventoryItemORM, ItemTagORM, SafetyRuleORM
from app.models.domain import GuardrailResult

ZERO = 0


def check_tag_limits(session: Session, item: InventoryItemORM, quantity: int) -> GuardrailResult:
    """Check all tag-based safety rules that apply to this item.

    For each tag on the item, look up whether a safety rule exists.
    If the projected total (current aggregate + quantity) exceeds the limit, reject.
    """
    for item_tag in item.item_tags:
        tag = item_tag.tag
        rule = session.query(SafetyRuleORM).filter(SafetyRuleORM.tag_id == tag.id).first()
        if rule is None:
            continue

        current = (
            session.query(func.sum(InventoryItemORM.stock))
            .join(ItemTagORM, ItemTagORM.item_id == InventoryItemORM.id)
            .filter(ItemTagORM.tag_id == tag.id)
            .scalar()
        ) or ZERO

        projected = current + quantity
        if projected > rule.limit_value:
            max_allowed = max(ZERO, rule.limit_value - current)
            return GuardrailResult(
                allowed=False,
                reason=(
                    f"Would bring total {tag.name} stock to {projected} {rule.limit_unit}, "
                    f"exceeding the {rule.limit_value} {rule.limit_unit} limit. "
                    f"Current total: {current} {rule.limit_unit}. "
                    f"You can add at most {max_allowed} {rule.limit_unit} more."
                ),
                rule_violated=rule.rule_reference,
                current_total=current,
                max_allowed=max_allowed,
            )

    return GuardrailResult(allowed=True)


def check_negative_stock(item: InventoryItemORM, quantity: int) -> GuardrailResult:
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
    quantity: int,
    operation: str,
) -> GuardrailResult:
    """Run all applicable guardrails in priority order.

    consume: check negative stock (fast, no DB query)
    add:     check all tag-based safety rules
    Returns the first failing result, or GuardrailResult(allowed=True).
    """
    if operation == "consume":
        return check_negative_stock(item, quantity)

    if operation == "add":
        return check_tag_limits(session, item, quantity)

    return GuardrailResult(allowed=False, reason=f"Unknown operation: {operation!r}")
