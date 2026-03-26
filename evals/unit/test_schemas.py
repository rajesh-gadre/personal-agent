"""Unit tests for Pydantic schema models."""
import datetime

import pytest
from pydantic import ValidationError

from agents.receipt_analyzer.schemas import ExtractionResult, LineItem, ReceiptData, ReceiptRecord


pytestmark = pytest.mark.unit


class TestLineItem:
    def test_basic(self):
        item = LineItem(description="Milk", quantity=1, unit_price=4.99, total=4.99)
        assert item.description == "Milk"
        assert item.total == 4.99

    def test_default_quantity(self):
        item = LineItem(description="Bread", unit_price=3.99, total=3.99)
        assert item.quantity == 1.0

    def test_negative_total_trade_in(self):
        item = LineItem(description="Trade-in credit", quantity=1, unit_price=-350.00, total=-350.00)
        assert item.total == -350.00

    def test_negative_total_discount(self):
        item = LineItem(description="Coupon", quantity=1, unit_price=-3.00, total=-3.00)
        assert item.total < 0

    def test_fractional_quantity(self):
        item = LineItem(description="Deli Turkey", quantity=0.75, unit_price=8.00, total=6.00)
        assert item.quantity == 0.75


class TestExtractionResult:
    def test_valid_receipt_all_fields(self):
        result = ExtractionResult(
            is_valid_receipt=True,
            merchant_name="Whole Foods",
            date=datetime.date(2026, 3, 15),
            total=18.87,
            category="groceries",
        )
        assert result.is_valid_receipt is True
        assert result.currency == "USD"  # default

    def test_invalid_receipt_all_none(self):
        result = ExtractionResult(is_valid_receipt=False)
        assert result.merchant_name is None
        assert result.total is None
        assert result.date is None

    def test_optional_fields_absent(self):
        result = ExtractionResult(is_valid_receipt=True, merchant_name="Test", total=10.00)
        assert result.merchant_address is None
        assert result.items is None
        assert result.tip is None

    def test_custom_currency(self):
        result = ExtractionResult(is_valid_receipt=True, total=3.99, currency="GBP")
        assert result.currency == "GBP"

    def test_is_valid_receipt_required(self):
        with pytest.raises(ValidationError):
            ExtractionResult()

    def test_with_line_items(self):
        result = ExtractionResult(
            is_valid_receipt=True,
            merchant_name="Store",
            total=10.00,
            items=[LineItem(description="Item A", unit_price=10.00, total=10.00)],
        )
        assert len(result.items) == 1

    def test_model_dump_json_mode(self):
        result = ExtractionResult(
            is_valid_receipt=True,
            merchant_name="Store",
            date=datetime.date(2026, 1, 1),
            total=10.00,
        )
        dumped = result.model_dump(mode="json")
        assert dumped["date"] == "2026-01-01"
        assert isinstance(dumped["is_valid_receipt"], bool)


class TestReceiptData:
    def test_required_fields(self):
        r = ReceiptData(merchant_name="Store", total=10.00)
        assert r.category == "other"  # default
        assert r.currency == "USD"
        assert r.items == []

    def test_missing_merchant_name_raises(self):
        with pytest.raises(ValidationError):
            ReceiptData(total=10.00)

    def test_missing_total_raises(self):
        with pytest.raises(ValidationError):
            ReceiptData(merchant_name="Store")


class TestReceiptRecord:
    def test_extends_receipt_data(self):
        r = ReceiptRecord(merchant_name="Store", total=10.00)
        assert r.id is None
        assert r.file_path == ""

    def test_with_id_and_path(self):
        r = ReceiptRecord(id=42, merchant_name="Store", total=10.00, file_path="/data/archive/x.jpg")
        assert r.id == 42
        assert r.file_path == "/data/archive/x.jpg"
