"""SQLAlchemy ORM models for inventory and audit log."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class InventoryItemORM(Base):
    __tablename__ = "inventory"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    stock = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    flammable = Column(Boolean, default=False, nullable=False)
    vasoconstrictor = Column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<InventoryItem id={self.id} name={self.name!r} stock={self.stock} {self.unit}>"


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    action = Column(String, nullable=False)  # "ADD" or "CONSUME"
    item_id = Column(String, nullable=False)
    item_name = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # "SUCCESS" or "REJECTED"
    reason = Column(String, nullable=True)
    rule_violated = Column(String, nullable=True)


def make_engine(db_url: str = "sqlite:///dental.db") -> Engine:
    return create_engine(db_url, connect_args={"check_same_thread": False})


def make_session_factory(engine: Engine) -> type[Session]:
    return sessionmaker(bind=engine)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)
