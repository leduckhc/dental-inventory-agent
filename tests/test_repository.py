"""Unit tests for repository read helpers — no guardrail logic, pure DB reads."""

from app.db.repository import get_all_items, get_item, search_items


def test_get_all_items_returns_all(db_sessions):
    """All 7 seeded items are returned, ordered by category then name."""
    inv, _ = db_sessions
    items = get_all_items(inv)
    assert len(items) == 7
    assert all(item.stock >= 0 for item in items)


def test_get_item_found(db_sessions):
    inv, _ = db_sessions
    item = get_item(inv, "A101")
    assert item is not None
    assert item.id == "A101"
    assert item.stock == 15.0
    assert item.attributes.flammable is False


def test_get_item_not_found(db_sessions):
    inv, _ = db_sessions
    item = get_item(inv, "Z999")
    assert item is None


def test_search_items_exact_match(db_sessions):
    inv, _ = db_sessions
    results = search_items(inv, "Ethanol")
    assert len(results) == 1
    assert results[0].id == "D500"


def test_search_items_multiple_matches(db_sessions):
    """'adrenaline' matches both Septanest and Ubistesin — the disambiguation case."""
    inv, _ = db_sessions
    results = search_items(inv, "adrenaline")
    assert len(results) == 2
    ids = {r.id for r in results}
    assert "A102" in ids
    assert "A103" in ids


def test_search_items_category_match(db_sessions):
    """'anesthetic' matches all 3 items in the Anesthetics category (not in any name)."""
    inv, _ = db_sessions
    results = search_items(inv, "anesthetic")
    assert len(results) == 3
    ids = {r.id for r in results}
    assert "A101" in ids
    assert "A102" in ids
    assert "A103" in ids


def test_search_items_no_match(db_sessions):
    inv, _ = db_sessions
    results = search_items(inv, "Paracetamol")
    assert results == []


def test_search_items_case_insensitive(db_sessions):
    inv, _ = db_sessions
    results = search_items(inv, "LIDOCAINE")
    assert len(results) == 1
    assert results[0].id == "A101"
