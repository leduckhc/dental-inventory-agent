"""Pydantic domain models — validation layer for all tool inputs and domain objects."""

from typing import Literal

from pydantic import BaseModel, Field


class ItemAttributes(BaseModel):
    flammable: bool
    vasoconstrictor: bool


class InventoryItem(BaseModel):
    id: str
    name: str
    category: str
    stock: int
    unit: str
    attributes: ItemAttributes


class StockUpdateInput(BaseModel):
    """Input validation for update_stock and consume_stock tools."""

    item_id: str = Field(
        pattern=r"^[A-Z][0-9]{3}$",
        description="Inventory item ID, e.g. A101 or D500",
    )
    quantity: int = Field(gt=0, strict=True, description="Must be a positive integer")
    operation: Literal["add", "consume"]


class GuardrailResult(BaseModel):
    allowed: bool
    reason: str | None = None
    rule_violated: str | None = None
    current_total: int | None = None  # relevant quantity before the operation
    max_allowed: int | None = None  # the limit that would be exceeded
