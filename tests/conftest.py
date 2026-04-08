"""Pytest fixtures: fresh in-memory SQLite per test, seeded from inventory.json + safety_rules.json."""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.schema import Base, InventoryItemORM, ItemTagORM, SafetyRuleORM, SafetyTagORM

CASE_DIR = Path(__file__).parent.parent / "case"
INVENTORY_JSON = CASE_DIR / "inventory.json"
SAFETY_RULES_JSON = CASE_DIR / "safety_rules.json"

# Maps legacy boolean attribute names in inventory.json to tag names.
ATTRIBUTE_TO_TAG = ("flammable", "vasoconstrictor")


@pytest.fixture
def db_sessions():
    """Return (inv_session, audit_session) backed by fresh in-memory SQLite.

    Both sessions share the same engine so audit queries can inspect
    audit_logs alongside inventory in a single test.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    inv_session = Session()
    audit_session = Session()

    # 1. Seed safety tags and rules
    with open(SAFETY_RULES_JSON) as f:
        rules = json.load(f)

    tag_orm_map: dict[str, SafetyTagORM] = {}
    for rule in rules:
        tag_name = rule["tag"]
        if tag_name not in tag_orm_map:
            tag = SafetyTagORM(name=tag_name)
            inv_session.add(tag)
            inv_session.flush()
            tag_orm_map[tag_name] = tag

        tag = tag_orm_map[rule["tag"]]
        inv_session.add(
            SafetyRuleORM(
                tag_id=tag.id,
                limit_value=rule["limit"],
                limit_unit=rule["unit"],
                rule_reference=rule["rule_reference"],
            )
        )

    # 2. Seed inventory items and tag associations
    with open(INVENTORY_JSON) as f:
        items = json.load(f)

    for raw in items:
        inv_session.merge(
            InventoryItemORM(
                id=raw["id"],
                name=raw["name"],
                category=raw["category"],
                stock=int(raw["stock"]),
                unit=raw["unit"],
            )
        )
        inv_session.flush()

        attrs = raw.get("attributes", {})
        for attr_name in ATTRIBUTE_TO_TAG:
            if attrs.get(attr_name) and attr_name in tag_orm_map:
                inv_session.add(ItemTagORM(item_id=raw["id"], tag_id=tag_orm_map[attr_name].id))

    inv_session.commit()

    yield inv_session, audit_session

    inv_session.close()
    audit_session.close()
    engine.dispose()
