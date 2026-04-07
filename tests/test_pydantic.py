"""Pydantic validation tests — no DB, no LLM."""

import pytest
from pydantic import ValidationError

from app.models.domain import StockUpdateInput


def test_zero_quantity_rejected():
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="A101", quantity=0, operation="add")


def test_negative_quantity_rejected():
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="A101", quantity=-5, operation="consume")


def test_string_quantity_rejected():
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="A101", quantity="5", operation="add")


def test_float_quantity_rejected():
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="A101", quantity=1.5, operation="add")


def test_invalid_item_id_format():
    """Item IDs must be one uppercase letter + 3 digits (e.g. A101, D500)."""
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="INVALID", quantity=1, operation="add")


def test_invalid_item_id_lowercase():
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="a101", quantity=1, operation="add")


def test_invalid_operation():
    with pytest.raises(ValidationError):
        StockUpdateInput(item_id="A101", quantity=1, operation="order")


def test_valid_input_add():
    inp = StockUpdateInput(item_id="A101", quantity=3, operation="add")
    assert inp.quantity == 3
    assert inp.operation == "add"


def test_valid_input_consume():
    inp = StockUpdateInput(item_id="D500", quantity=1, operation="consume")
    assert inp.item_id == "D500"
    assert inp.operation == "consume"
