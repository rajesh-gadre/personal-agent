"""Unit tests for DB CRUD operations in storage.py."""
import datetime

import pytest

from agents.receipt_analyzer.schemas import LineItem, ReceiptRecord
from agents.receipt_analyzer.storage import (
    delete_receipt,
    get_categories,
    get_receipt_by_id,
    get_summary_stats,
    query_receipts,
    save_receipt,
)


pytestmark = pytest.mark.unit


def _make_receipt(**kwargs) -> ReceiptRecord:
    defaults = dict(
        merchant_name="Test Store",
        date=datetime.date(2026, 3, 15),
        total=50.00,
        subtotal=45.00,
        tax=5.00,
        category="groceries",
        file_path="/data/archive/test.jpg",
    )
    defaults.update(kwargs)
    return ReceiptRecord(**defaults)


class TestSaveAndGet:
    def test_save_returns_id(self):
        receipt_id = save_receipt(_make_receipt())
        assert isinstance(receipt_id, int)
        assert receipt_id > 0

    def test_get_by_id_round_trip(self):
        r = _make_receipt(merchant_name="Whole Foods", total=18.87)
        receipt_id = save_receipt(r)
        fetched = get_receipt_by_id(receipt_id)
        assert fetched.merchant_name == "Whole Foods"
        assert fetched.total == 18.87
        assert fetched.category == "groceries"

    def test_get_nonexistent_returns_none(self):
        assert get_receipt_by_id(99999) is None

    def test_optional_fields_preserved(self):
        r = _make_receipt(
            merchant_address="123 Main St",
            payment_method="VISA",
            tip=5.00,
            currency="USD",
        )
        receipt_id = save_receipt(r)
        fetched = get_receipt_by_id(receipt_id)
        assert fetched.merchant_address == "123 Main St"
        assert fetched.payment_method == "VISA"
        assert fetched.tip == 5.00

    def test_line_items_round_trip(self):
        r = _make_receipt(
            items=[
                LineItem(description="Milk", quantity=1, unit_price=4.99, total=4.99),
                LineItem(description="Bread", quantity=1, unit_price=6.49, total=6.49),
            ]
        )
        receipt_id = save_receipt(r)
        fetched = get_receipt_by_id(receipt_id)
        assert len(fetched.items) == 2
        assert fetched.items[0].description == "Milk"

    def test_negative_line_item_preserved(self):
        r = _make_receipt(
            items=[LineItem(description="Trade-in", quantity=1, unit_price=-350.00, total=-350.00)]
        )
        receipt_id = save_receipt(r)
        fetched = get_receipt_by_id(receipt_id)
        assert fetched.items[0].total == -350.00


class TestDelete:
    def test_delete_existing(self):
        receipt_id = save_receipt(_make_receipt())
        result = delete_receipt(receipt_id)
        assert result is True
        assert get_receipt_by_id(receipt_id) is None

    def test_delete_nonexistent_returns_false(self):
        assert delete_receipt(99999) is False

    def test_delete_twice_returns_false(self):
        receipt_id = save_receipt(_make_receipt())
        delete_receipt(receipt_id)
        assert delete_receipt(receipt_id) is False


class TestQuery:
    def test_query_all(self):
        save_receipt(_make_receipt())
        save_receipt(_make_receipt())
        results = query_receipts()
        assert len(results) == 2

    def test_query_by_date_range(self):
        save_receipt(_make_receipt(date=datetime.date(2026, 3, 1)))
        save_receipt(_make_receipt(date=datetime.date(2026, 3, 15)))
        save_receipt(_make_receipt(date=datetime.date(2026, 4, 1)))

        results = query_receipts(start_date="2026-03-01", end_date="2026-03-31")
        assert len(results) == 2

    def test_query_by_category(self):
        save_receipt(_make_receipt(category="groceries"))
        save_receipt(_make_receipt(category="restaurant"))
        results = query_receipts(category="restaurant")
        assert len(results) == 1
        assert results[0].category == "restaurant"

    def test_query_by_merchant(self):
        save_receipt(_make_receipt(merchant_name="Whole Foods"))
        save_receipt(_make_receipt(merchant_name="Target"))
        results = query_receipts(merchant="Whole")
        assert len(results) == 1
        assert "Whole" in results[0].merchant_name

    def test_query_empty_db(self):
        assert query_receipts() == []

    def test_query_ordered_newest_first(self):
        save_receipt(_make_receipt(date=datetime.date(2026, 1, 1)))
        save_receipt(_make_receipt(date=datetime.date(2026, 3, 1)))
        results = query_receipts()
        assert results[0].date >= results[1].date


class TestCategories:
    def test_empty_db_returns_empty(self):
        assert get_categories() == []

    def test_returns_distinct_sorted(self):
        save_receipt(_make_receipt(category="restaurant"))
        save_receipt(_make_receipt(category="groceries"))
        save_receipt(_make_receipt(category="restaurant"))  # duplicate
        cats = get_categories()
        assert cats == ["groceries", "restaurant"]

    def test_custom_category_included(self):
        save_receipt(_make_receipt(category="pet-care"))
        assert "pet-care" in get_categories()


class TestSummaryStats:
    def test_empty_db(self):
        stats = get_summary_stats()
        assert stats["total_spent"] == 0.0
        assert stats["receipt_count"] == 0
        assert stats["by_category"] == {}

    def test_totals(self):
        save_receipt(_make_receipt(total=50.00, tax=5.00, category="groceries"))
        save_receipt(_make_receipt(total=30.00, tax=3.00, category="restaurant"))
        stats = get_summary_stats()
        assert stats["total_spent"] == 80.00
        assert stats["total_tax"] == 8.00
        assert stats["receipt_count"] == 2

    def test_by_category(self):
        save_receipt(_make_receipt(total=50.00, category="groceries"))
        save_receipt(_make_receipt(total=30.00, category="groceries"))
        save_receipt(_make_receipt(total=45.00, category="restaurant"))
        stats = get_summary_stats()
        assert stats["by_category"]["groceries"] == 80.00
        assert stats["by_category"]["restaurant"] == 45.00

    def test_date_range_filter(self):
        save_receipt(_make_receipt(total=100.00, date=datetime.date(2026, 1, 1)))
        save_receipt(_make_receipt(total=50.00, date=datetime.date(2026, 3, 15)))
        stats = get_summary_stats(start_date="2026-03-01", end_date="2026-03-31")
        assert stats["total_spent"] == 50.00
        assert stats["receipt_count"] == 1
