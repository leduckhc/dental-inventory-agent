"""One-time migration: load inventory.json into SQLite.

Usage:
    python -m app.db.migrate                   # creates dental.db in cwd
    python -m app.db.migrate --db-url sqlite:///path/to/custom.db
"""

import argparse
import json
from pathlib import Path

from app.db.schema import InventoryItemORM, create_tables, make_engine, make_session_factory

INVENTORY_JSON = Path(__file__).parent.parent.parent / "case" / "inventory.json"


def load_inventory(db_url: str = "sqlite:///dental.db", json_path: Path = INVENTORY_JSON) -> None:
    engine = make_engine(db_url)
    create_tables(engine)
    Session = make_session_factory(engine)

    with open(json_path) as f:
        items = json.load(f)

    session = Session()
    try:
        for raw in items:
            attrs = raw.get("attributes", {})
            item = InventoryItemORM(
                id=raw["id"],
                name=raw["name"],
                category=raw["category"],
                stock=float(raw["stock"]),
                unit=raw["unit"],
                flammable=bool(attrs.get("flammable", False)),
                vasoconstrictor=bool(attrs.get("vasoconstrictor", False)),
            )
            session.merge(item)  # upsert — safe to re-run
        session.commit()
        print(f"Loaded {len(items)} items into {db_url}")
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
