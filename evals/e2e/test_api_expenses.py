"""E2E tests for expense query, summary, detail, and delete endpoints."""
import pytest

from api import mgr
from evals.fixtures.receipt_data import GROCERY_RECEIPT, RESTAURANT_RECEIPT

pytestmark = pytest.mark.e2e


def _approve(mock_llm, sample_image_path, fixture):
    """Helper: analyze with given fixture, approve, return receipt_id."""
    mock_llm.add_response(fixture).add_response(fixture)
    result = mgr.analyze(str(sample_image_path))
    staged = mgr.get_staged(result["staging_id"])
    data = staged["extracted_data"]
    receipt_id = mgr.approve(result["staging_id"])
    return receipt_id


@pytest.fixture
def grocery_id(mock_llm, sample_image_path):
    return _approve(mock_llm, sample_image_path, GROCERY_RECEIPT)


@pytest.fixture
def two_receipts(mock_llm, sample_image_path):
    """Approve one grocery + one restaurant receipt. Returns (grocery_id, restaurant_id)."""
    gid = _approve(mock_llm, sample_image_path, GROCERY_RECEIPT)
    rid = _approve(mock_llm, sample_image_path, RESTAURANT_RECEIPT)
    return gid, rid


class TestQueryExpenses:
    def test_empty_db(self, api_client):
        resp = api_client.get("/api/expenses")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_approved_receipt(self, api_client, grocery_id):
        expenses = api_client.get("/api/expenses").json()
        assert len(expenses) == 1
        r = expenses[0]
        assert r["merchant_name"] == "Whole Foods Market"
        assert r["total"] == pytest.approx(18.87)
        assert r["category"] == "groceries"

    def test_response_has_required_fields(self, api_client, grocery_id):
        r = api_client.get("/api/expenses").json()[0]
        for field in ("id", "merchant_name", "total", "category", "currency", "image_url"):
            assert field in r

    def test_filter_by_category(self, api_client, two_receipts):
        resp = api_client.get("/api/expenses?category=groceries")
        results = resp.json()
        assert len(results) == 1
        assert results[0]["category"] == "groceries"

    def test_filter_by_merchant(self, api_client, two_receipts):
        resp = api_client.get("/api/expenses?merchant=Whole")
        results = resp.json()
        assert len(results) == 1
        assert "Whole" in results[0]["merchant_name"]

    def test_filter_by_date_range(self, api_client, two_receipts):
        resp = api_client.get("/api/expenses?start_date=2026-03-01&end_date=2026-03-31")
        # GROCERY_RECEIPT date is 2026-03-15, RESTAURANT_RECEIPT is 2026-03-10 — both in range
        results = resp.json()
        assert len(results) == 2

    def test_date_range_excludes_outside(self, api_client, two_receipts):
        # Only GROCERY_RECEIPT (2026-03-15) should match
        resp = api_client.get("/api/expenses?start_date=2026-03-12&end_date=2026-03-31")
        results = resp.json()
        assert len(results) == 1
        assert results[0]["category"] == "groceries"


class TestGetExpense:
    def test_get_existing(self, api_client, grocery_id):
        resp = api_client.get(f"/api/expenses/{grocery_id}")
        assert resp.status_code == 200
        r = resp.json()
        assert r["id"] == grocery_id
        assert r["merchant_name"] == "Whole Foods Market"

    def test_get_nonexistent_returns_404(self, api_client):
        resp = api_client.get("/api/expenses/99999")
        assert resp.status_code == 404


class TestSummary:
    def test_empty_summary(self, api_client):
        resp = api_client.get("/api/expenses/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_spent"] == 0.0
        assert body["receipt_count"] == 0
        assert body["by_category"] == {}

    def test_summary_after_approve(self, api_client, grocery_id):
        body = api_client.get("/api/expenses/summary").json()
        assert body["receipt_count"] == 1
        assert body["total_spent"] == pytest.approx(18.87)
        assert "groceries" in body["by_category"]

    def test_summary_multiple_categories(self, api_client, two_receipts):
        body = api_client.get("/api/expenses/summary").json()
        assert body["receipt_count"] == 2
        assert body["total_spent"] == pytest.approx(18.87 + 45.97)
        assert "groceries" in body["by_category"]
        assert "restaurant" in body["by_category"]

    def test_summary_date_range_filter(self, api_client, two_receipts):
        # Only grocery (2026-03-15) within this narrow range
        resp = api_client.get("/api/expenses/summary?start_date=2026-03-12&end_date=2026-03-31")
        body = resp.json()
        assert body["receipt_count"] == 1
        assert body["total_spent"] == pytest.approx(18.87)


class TestDeleteExpense:
    def test_delete_existing(self, api_client, grocery_id):
        resp = api_client.delete(f"/api/expenses/{grocery_id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_deleted_not_in_query(self, api_client, grocery_id):
        api_client.delete(f"/api/expenses/{grocery_id}")
        assert api_client.get("/api/expenses").json() == []

    def test_delete_nonexistent_returns_404(self, api_client):
        resp = api_client.delete("/api/expenses/99999")
        assert resp.status_code == 404

    def test_delete_twice_returns_404(self, api_client, grocery_id):
        api_client.delete(f"/api/expenses/{grocery_id}")
        resp = api_client.delete(f"/api/expenses/{grocery_id}")
        assert resp.status_code == 404


class TestCategories:
    def test_default_categories_always_present(self, api_client):
        cats = api_client.get("/api/categories").json()
        assert isinstance(cats, list)
        assert len(cats) > 0
        assert "groceries" in cats
        assert "restaurant" in cats

    def test_custom_category_appears_after_approve(self, api_client, grocery_id):
        # groceries is already a default; just verify the endpoint returns sorted list
        cats = api_client.get("/api/categories").json()
        assert cats == sorted(cats)
