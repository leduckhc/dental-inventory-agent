"""SQLAlchemy ORM models for inventory, safety tags, rules, and audit log."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class SafetyTagORM(Base):
    __tablename__ = "safety_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    item_tags = relationship("ItemTagORM", back_populates="tag")
    rules = relationship("SafetyRuleORM", back_populates="tag")


class SafetyRuleORM(Base):
    __tablename__ = "safety_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_id = Column(Integer, ForeignKey("safety_tags.id"), nullable=False, unique=True)
    limit_value = Column(Integer, nullable=False)
    limit_unit = Column(String, nullable=False)
    rule_reference = Column(String, nullable=False)

    tag = relationship("SafetyTagORM", back_populates="rules")


class ItemTagORM(Base):
    __tablename__ = "item_tags"

    item_id = Column(String, ForeignKey("inventory.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("safety_tags.id"), primary_key=True)

    item = relationship("InventoryItemORM", back_populates="item_tags")
    tag = relationship("SafetyTagORM", back_populates="item_tags", lazy="joined")


class InventoryItemORM(Base):
    __tablename__ = "inventory"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    stock = Column(Integer, nullable=False)
    unit = Column(String, nullable=False)

    item_tags = relationship("ItemTagORM", back_populates="item", lazy="joined")

    def __repr__(self) -> str:
        return f"<InventoryItem id={self.id} name={self.name!r} stock={self.stock} {self.unit}>"


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    action = Column(String, nullable=False)  # "ADD" or "CONSUME"
    item_id = Column(String, nullable=False)
    item_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # "SUCCESS" or "REJECTED"
    reason = Column(String, nullable=True)
    rule_violated = Column(String, nullable=True)


def make_engine(db_url: str = "sqlite:///dental.db") -> Engine:
    return create_engine(db_url, connect_args={"check_same_thread": False})


def make_session_factory(engine: Engine) -> type[Session]:
    return sessionmaker(bind=engine)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)
