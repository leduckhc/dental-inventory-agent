"""One-time migration: load inventory.json and safety_rules.json into SQLite.

Reads the legacy `attributes` format from inventory.json and transforms
boolean flags into tag associations automatically.

Usage:
    python -m app.db.migrate                   # creates dental.db in cwd
    python -m app.db.migrate --db-url sqlite:///path/to/custom.db
"""

import argparse
import json
from pathlib import Path

from app.db.schema import (
    InventoryItemORM,
    ItemTagORM,
    SafetyRuleORM,
    SafetyTagORM,
    create_tables,
    make_engine,
    make_session_factory,
)

CASE_DIR = Path(__file__).parent.parent.parent / "case"
INVENTORY_JSON = CASE_DIR / "inventory.json"
SAFETY_RULES_JSON = CASE_DIR / "safety_rules.json"

# Maps legacy boolean attribute names in inventory.json to tag names.
# When inventory.json says {"attributes": {"flammable": true}}, we create
# a tag named "flammable" and associate it with the item.
ATTRIBUTE_TO_TAG = ("flammable", "vasoconstrictor")


def load_inventory(db_url: str = "sqlite:///dental.db", json_path: Path = INVENTORY_JSON) -> None:
    engine = make_engine(db_url)
    create_tables(engine)
    Session = make_session_factory(engine)

    with open(json_path) as f:
        items = json.load(f)

    with open(SAFETY_RULES_JSON) as f:
        rules = json.load(f)

    session = Session()
    try:
        # 1. Collect and upsert safety tags from both the rules file and inventory attributes
        tag_names: set[str] = set()
        for rule in rules:
            tag_names.add(rule["tag"])
        for raw in items:
            attrs = raw.get("attributes", {})
            for attr_name in ATTRIBUTE_TO_TAG:
                if attrs.get(attr_name):
                    tag_names.add(attr_name)

        tag_orm_map: dict[str, SafetyTagORM] = {}
        for name in sorted(tag_names):
            existing = session.query(SafetyTagORM).filter_by(name=name).first()
            if existing:
                tag_orm_map[name] = existing
            else:
                tag = SafetyTagORM(name=name)
                session.add(tag)
                session.flush()
                tag_orm_map[name] = tag

        # 2. Upsert safety rules
        for rule in rules:
            tag = tag_orm_map[rule["tag"]]
            existing = session.query(SafetyRuleORM).filter_by(tag_id=tag.id).first()
            if existing:
                existing.limit_value = rule["limit"]
                existing.limit_unit = rule["unit"]
                existing.rule_reference = rule["rule_reference"]
            else:
                session.add(
                    SafetyRuleORM(
                        tag_id=tag.id,
                        limit_value=rule["limit"],
                        limit_unit=rule["unit"],
                        rule_reference=rule["rule_reference"],
                    )
                )

        # 3. Upsert inventory items and their tag associations
        for raw in items:
            item = InventoryItemORM(
                id=raw["id"],
                name=raw["name"],
                category=raw["category"],
                stock=int(raw["stock"]),
                unit=raw["unit"],
            )
            session.merge(item)
            session.flush()

            # Transform legacy boolean attributes into tag associations
            attrs = raw.get("attributes", {})
            for attr_name in ATTRIBUTE_TO_TAG:
                if attrs.get(attr_name):
                    tag = tag_orm_map[attr_name]
                    existing = session.query(ItemTagORM).filter_by(item_id=raw["id"], tag_id=tag.id).first()
                    if not existing:
                        session.add(ItemTagORM(item_id=raw["id"], tag_id=tag.id))

        session.commit()
        print(f"Loaded {len(items)} items and {len(rules)} safety rules into {db_url}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", default="sqlite:///dental.db")
    args = parser.parse_args()
    load_inventory(args.db_url)
