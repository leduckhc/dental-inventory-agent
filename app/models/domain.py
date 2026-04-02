"""Pydantic domain models — validation layer for all tool inputs and domain objects."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ItemAttributes(BaseModel):
    flammable: bool
    vasoconstrictor: bool


class InventoryItem(BaseModel):
    id: str
    name: str
    category: str
    stock: float
    unit: str
    attributes: ItemAttributes


class StockUpdateInput(BaseModel):
    """Input validation for update_stock and consume_stock tools."""
    item_id: str = Field(
        pattern=r"^[A-Z][0-9]{3}$",
        description="Inventory item ID, e.g. A101 or D500",
    )
    quantity: float = Field(gt=0, description="Must be a positive number")
    operation: Literal["add", "consume"]


class GuardrailResult(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    rule_violated: Optional[str] = None
    current_total: Optional[float] = None   # relevant quantity before the operation
    max_allowed: Optional[float] = None     # the limit that would be exceeded


class AuditLogEntry(BaseModel):
    id: Optional[int] = None
    timestamp: datetime
    action: str
    item_id: str
    item_name: str
    quantity: float
    status: Literal["SUCCESS", "REJECTED"]
    reason: Optional[str] = None
    rule_violated: Optional[str] = None
