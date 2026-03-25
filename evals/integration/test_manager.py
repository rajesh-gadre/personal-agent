"""Integration tests for the ReceiptManager facade."""
import pytest

from agents.receipt_analyzer.manager import ReceiptManager
from agents.receipt_analyzer.storage import get_receipt_by_id
from evals.fixtures.receipt_data import (
    GROCERY_RECEIPT,
    NOT_A_RECEIPT,
    RESTAURANT_RECEIPT,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def mgr():
    return ReceiptManager()


class TestAnalyze:
    def test_analyze_returns_staging_id(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        assert result["staging_id"] is not None
        assert result.get("error") is None

    def test_analyze_invalid_is_staged_not_errored(self, mgr, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        result = mgr.analyze(str(sample_invalid_image_path))
        assert result.get("error") is None
        assert result["staging_id"] is not None

    def test_analyze_invalid_has_flag_false(self, mgr, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        result = mgr.analyze(str(sample_invalid_image_path))
        staged = mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is False


class TestGetPending:
    def test_empty_pending(self, mgr):
        assert mgr.get_pending() == []

    def test_pending_after_analyze(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        pending = mgr.get_pending()
        assert len(pending) == 1
        assert pending[0]["staging_id"] == result["staging_id"]

    def test_pending_cleared_after_approve(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        mgr.approve(result["staging_id"])
        assert mgr.get_pending() == []

    def test_pending_cleared_after_reject(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        mgr.reject(result["staging_id"])
        assert mgr.get_pending() == []

    def test_multiple_pending_items(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        mgr.analyze(str(sample_image_path))
        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        mgr.analyze(str(sample_image_path))
        assert len(mgr.get_pending()) == 2


class TestGetStaged:
    def test_get_staged_returns_data(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        staged = mgr.get_staged(result["staging_id"])
        assert staged is not None
        assert staged["staging_id"] == result["staging_id"]

    def test_get_staged_nonexistent_returns_none(self, mgr):
        assert mgr.get_staged("nonexistent_id") is None


class TestUpdateAndApprove:
    def test_update_then_approve_uses_updated_data(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        staging_id = result["staging_id"]

        staged = mgr.get_staged(staging_id)
        edited = {**staged["extracted_data"], "merchant_name": "Corrected Store", "total": 99.99}
        mgr.update_staged(staging_id, edited)

        receipt_id = mgr.approve(staging_id)
        record = get_receipt_by_id(receipt_id)
        assert record.merchant_name == "Corrected Store"
        assert record.total == pytest.approx(99.99)

    def test_update_nonexistent_does_not_raise(self, mgr):
        mgr.update_staged("nonexistent_id", {"merchant_name": "X"})


class TestQuery:
    def test_query_empty(self, mgr):
        assert mgr.query() == []

    def test_query_after_approve(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        mgr.approve(result["staging_id"])
        records = mgr.query()
        assert len(records) == 1
        assert records[0].merchant_name == "Whole Foods Market"

    def test_query_by_category(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r1 = mgr.analyze(str(sample_image_path))
        mgr.approve(r1["staging_id"])

        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        r2 = mgr.analyze(str(sample_image_path))
        mgr.approve(r2["staging_id"])

        groceries = mgr.query(category="groceries")
        assert len(groceries) == 1
        assert groceries[0].category == "groceries"

    def test_query_by_merchant(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r = mgr.analyze(str(sample_image_path))
        mgr.approve(r["staging_id"])
        results = mgr.query(merchant="Whole")
        assert len(results) == 1
        assert "Whole" in results[0].merchant_name

    def test_rejected_receipt_not_in_query(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = mgr.analyze(str(sample_image_path))
        mgr.reject(result["staging_id"])
        assert mgr.query() == []


class TestSummary:
    def test_summary_empty_db(self, mgr):
        stats = mgr.get_summary()
        assert stats["total_spent"] == 0.0
        assert stats["receipt_count"] == 0
        assert stats["by_category"] == {}

    def test_summary_after_approve(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r = mgr.analyze(str(sample_image_path))
        mgr.approve(r["staging_id"])
        stats = mgr.get_summary()
        assert stats["receipt_count"] == 1
        assert stats["total_spent"] == pytest.approx(18.87)
        assert "groceries" in stats["by_category"]
        assert stats["by_category"]["groceries"] == pytest.approx(18.87)

    def test_summary_multiple_categories(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r1 = mgr.analyze(str(sample_image_path))
        mgr.approve(r1["staging_id"])

        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        r2 = mgr.analyze(str(sample_image_path))
        mgr.approve(r2["staging_id"])

        stats = mgr.get_summary()
        assert stats["receipt_count"] == 2
        assert stats["total_spent"] == pytest.approx(18.87 + 45.97)
        assert "groceries" in stats["by_category"]
        assert "restaurant" in stats["by_category"]


class TestDelete:
    def test_delete_approved_receipt(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r = mgr.analyze(str(sample_image_path))
        receipt_id = mgr.approve(r["staging_id"])
        assert mgr.delete(receipt_id) is True
        assert mgr.query() == []

    def test_delete_nonexistent_returns_false(self, mgr):
        assert mgr.delete(99999) is False

    def test_delete_twice_returns_false(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r = mgr.analyze(str(sample_image_path))
        receipt_id = mgr.approve(r["staging_id"])
        mgr.delete(receipt_id)
        assert mgr.delete(receipt_id) is False


class TestCheckDuplicate:
    def test_duplicate_detected_after_approve(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r = mgr.analyze(str(sample_image_path))
        mgr.approve(r["staging_id"])

        dup = mgr.check_duplicate({
            "merchant_name": "Whole Foods Market",
            "date": "2026-03-15",
            "total": 18.87,
        })
        assert dup is not None
        assert dup.merchant_name == "Whole Foods Market"

    def test_no_duplicate_for_different_merchant(self, mgr, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r = mgr.analyze(str(sample_image_path))
        mgr.approve(r["staging_id"])

        assert mgr.check_duplicate({
            "merchant_name": "Target",
            "date": "2026-03-15",
            "total": 18.87,
        }) is None

    def test_no_duplicate_before_approve(self, mgr, mock_llm, sample_image_path):
        """Staged but not approved receipts don't count as duplicates."""
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        mgr.analyze(str(sample_image_path))

        assert mgr.check_duplicate({
            "merchant_name": "Whole Foods Market",
            "date": "2026-03-15",
            "total": 18.87,
        }) is None
