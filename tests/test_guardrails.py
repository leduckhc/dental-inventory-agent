"""Guardrail tests — no LLM, no network, pure Python + SQLite.

Inventory baseline (from inventory.json):
  Lidocaine     A101  stock=15  packs  tags=[]
  Septanest     A102  stock=8   packs  tags=[vasoconstrictor]
  Ubistesin     A103  stock=10  packs  tags=[vasoconstrictor]
  Ethanol       D500  stock=2   liters tags=[flammable]
  Isopropyl     D501  stock=3   liters tags=[flammable]
  Composite     K303  stock=4   tubes  tags=[]
  Latex Gloves  C201  stock=200 pcs    tags=[]

Derived totals:
  Total flammable:       2 + 3 = 5L
  Total vasoconstrictor: 8 + 10 = 18 packs
"""

from app.db.repository import update_stock
from app.db.schema import AuditLogORM, InventoryItemORM
from app.guardrails.checks import run_all_guardrails

# ── Rule 1: Flammable limit (10L) ───────────────────────────────────────────


def test_flammable_limit_rejected(db_sessions):
    """5L current + 8L order = 13L > 10L → REJECTED (test_scenarios.txt line 46)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "D500", 8, "add")
    assert not result.allowed
    assert result.rule_violated == "safety_regulation.txt Rule 1"
    assert result.current_total == 5


def test_flammable_limit_rejected_100L(db_sessions):
    """100L order → REJECTED (spec test case, test_scenarios.txt line 49)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "D500", 100, "add")
    assert not result.allowed
    assert result.rule_violated == "safety_regulation.txt Rule 1"


def test_flammable_exactly_at_limit_accepted(db_sessions):
    """5L current + 5L order = 10L = limit → ACCEPTED (boundary)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "D500", 5, "add")
    assert result.allowed


def test_flammable_isopropyl_exactly_at_limit_accepted(db_sessions):
    """5L current + 5L Isopropyl = 10L = limit → ACCEPTED.

    Note: test_scenarios.txt comment says '3+7=10L' which assumes Ethanol=0
    (post-consumption). We test with real baseline: 5L current + 5L = 10L.
    """
    inv, audit = db_sessions
    result = update_stock(inv, audit, "D501", 5, "add")
    assert result.allowed


def test_flammable_non_flammable_item_bypasses_check(db_sessions):
    """Ordering Lidocaine (no flammable tag) never triggers Rule 1."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "A101", 1000, "add")
    assert result.allowed


# ── Rule 2: Vasoconstrictor limit (20 packs) ────────────────────────────────


def test_vasoconstrictor_ubistesin_rejected(db_sessions):
    """18 current + 3 Ubistesin = 21 > 20 → REJECTED (test_scenarios.txt line 57)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "A103", 3, "add")
    assert not result.allowed
    assert result.rule_violated == "safety_regulation.txt Rule 2"
    assert result.current_total == 18


def test_vasoconstrictor_septanest_exactly_at_limit(db_sessions):
    """18 current + 2 Septanest = 20 = limit → ACCEPTED (test_scenarios.txt line 59)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "A102", 2, "add")
    assert result.allowed


def test_vasoconstrictor_septanest_rejected(db_sessions):
    """18 current + 3 Septanest = 21 > 20 → REJECTED (test_scenarios.txt line 62)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "A102", 3, "add")
    assert not result.allowed
    assert result.rule_violated == "safety_regulation.txt Rule 2"


# ── Negative stock (consume) ─────────────────────────────────────────────────


def test_negative_stock_rejected(db_sessions):
    """Consume 20 Lidocaine, only 15 in stock → REJECTED (test_scenarios.txt line 66)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "A101", 20, "consume")
    assert not result.allowed
    assert result.rule_violated == "Negative stock prevention"
    assert result.current_total == 15


def test_consume_exactly_at_stock_accepted(db_sessions):
    """Consume exactly 15 Lidocaine (full stock) → ACCEPTED."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "A101", 15, "consume")
    assert result.allowed


def test_consume_ethanol_exceeds_stock_rejected(db_sessions):
    """Consume 5L Ethanol, only 2L in stock → REJECTED (test_scenarios.txt line 69)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "D500", 5, "consume")
    assert not result.allowed
    assert result.rule_violated == "Negative stock prevention"


# ── Non-existent items ────────────────────────────────────────────────────────


def test_nonexistent_item_rejected(db_sessions):
    """Consume XYZ-999 (not in inventory) → REJECTED (test_scenarios.txt line 76)."""
    inv, audit = db_sessions
    result = update_stock(inv, audit, "X999", 2, "consume")
    assert not result.allowed
    assert "not found" in result.reason.lower()


# ── Audit log correctness (Rule 3) ───────────────────────────────────────────


def test_audit_written_on_success(db_sessions):
    """Successful order writes a SUCCESS audit entry."""
    inv, audit = db_sessions
    update_stock(inv, audit, "A101", 2, "add")
    entry = audit.query(AuditLogORM).filter_by(item_id="A101", status="SUCCESS").first()
    assert entry is not None
    assert entry.quantity == 2
    assert entry.action == "ADD"


def test_audit_written_on_rejection(db_sessions):
    """Rejected order writes a REJECTED audit entry — Rule 3 survives rollback."""
    inv, audit = db_sessions
    update_stock(inv, audit, "D500", 100, "add")  # will be rejected
    entry = audit.query(AuditLogORM).filter_by(item_id="D500", status="REJECTED").first()
    assert entry is not None
    assert entry.rule_violated == "safety_regulation.txt Rule 1"
    assert entry.reason is not None


def test_unknown_operation_rejected(db_sessions):
    """run_all_guardrails with unknown operation returns allowed=False (defensive fallback)."""
    inv, _ = db_sessions
    item = inv.get(InventoryItemORM, "A101")
    result = run_all_guardrails(inv, item, 1, "transfer")
    assert not result.allowed
    assert "Unknown operation" in result.reason


def test_audit_rejection_does_not_corrupt_inventory(db_sessions):
    """After a rejected order, stock must be unchanged."""
    inv, audit = db_sessions
    # Ethanol starts at 2L; trying to add 100L should be rejected
    update_stock(inv, audit, "D500", 100, "add")

    item = inv.get(InventoryItemORM, "D500")
    assert item.stock == 2  # unchanged
