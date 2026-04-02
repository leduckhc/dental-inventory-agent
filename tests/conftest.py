"""Pytest fixtures: fresh in-memory SQLite per test, seeded from inventory.json."""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.schema import Base, InventoryItemORM

INVENTORY_JSON = Path(__file__).parent.parent / "case" / "inventory.json"


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

    # Seed inventory from JSON
    with open(INVENTORY_JSON) as f:
        items = json.load(f)
    for raw in items:
        attrs = raw.get("attributes", {})
        inv_session.merge(
            InventoryItemORM(
                id=raw["id"],
                name=raw["name"],
                category=raw["category"],
                stock=float(raw["stock"]),
                unit=raw["unit"],
                flammable=bool(attrs.get("flammable", False)),
                vasoconstrictor=bool(attrs.get("vasoconstrictor", False)),
            )
        )
    inv_session.commit()

    yield inv_session, audit_session

    inv_session.close()
    audit_session.close()
    engine.dispose()
