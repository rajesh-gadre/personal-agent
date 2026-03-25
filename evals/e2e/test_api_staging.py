"""E2E tests for staging CRUD endpoints and duplicate check."""
import pytest

from api import mgr
from evals.fixtures.receipt_data import GROCERY_RECEIPT, RESTAURANT_RECEIPT

pytestmark = pytest.mark.e2e


@pytest.fixture
def staged_id(mock_llm, sample_image_path):
    """Stage a grocery receipt via the manager and return its staging_id."""
    mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
    result = mgr.analyze(str(sample_image_path))
    return result["staging_id"]


def _approve_body(staged_id: str) -> dict:
    """Build a minimal valid ReceiptEditData body from the staged receipt."""
    staged = mgr.get_staged(staged_id)
    data = staged["extracted_data"]
    return {
        "merchant_name": data["merchant_name"],
        "total": data["total"],
        "date": data.get("date"),
        "category": data.get("category", "other"),
        "currency": data.get("currency", "USD"),
    }


class TestListStaged:
    def test_empty_list(self, api_client):
        resp = api_client.get("/api/receipts/staged")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_staged_receipt(self, api_client, staged_id):
        resp = api_client.get("/api/receipts/staged")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["staging_id"] == staged_id

    def test_response_has_required_fields(self, api_client, staged_id):
        item = api_client.get("/api/receipts/staged").json()[0]
        assert "staging_id" in item
        assert "image_url" in item
        assert "extracted_data" in item
        assert "staged_at" in item


class TestGetStaged:
    def test_get_existing(self, api_client, staged_id):
        resp = api_client.get(f"/api/receipts/staged/{staged_id}")
        assert resp.status_code == 200
        assert resp.json()["staging_id"] == staged_id

    def test_get_nonexistent_returns_404(self, api_client):
        resp = api_client.get("/api/receipts/staged/nonexistent_id")
        assert resp.status_code == 404

    def test_extracted_data_fields(self, api_client, staged_id):
        data = api_client.get(f"/api/receipts/staged/{staged_id}").json()["extracted_data"]
        assert data["merchant_name"] == "Whole Foods Market"
        assert data["total"] == 18.87
        assert data["category"] == "groceries"


class TestUpdateStaged:
    def test_update_persists(self, api_client, staged_id):
        body = _approve_body(staged_id)
        body["merchant_name"] = "Edited Store"
        body["total"] = 99.99
        resp = api_client.put(f"/api/receipts/staged/{staged_id}", json=body)
        assert resp.status_code == 200
        updated = api_client.get(f"/api/receipts/staged/{staged_id}").json()
        assert updated["extracted_data"]["merchant_name"] == "Edited Store"
        assert updated["extracted_data"]["total"] == 99.99

    def test_update_nonexistent_returns_404(self, api_client):
        body = {"merchant_name": "X", "total": 1.00}
        resp = api_client.put("/api/receipts/staged/nonexistent_id", json=body)
        assert resp.status_code == 404


class TestApproveStaged:
    def test_approve_returns_receipt_id(self, api_client, staged_id):
        resp = api_client.post(
            f"/api/receipts/staged/{staged_id}/approve",
            json=_approve_body(staged_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "receipt_id" in body
        assert isinstance(body["receipt_id"], int)
        assert body["receipt_id"] > 0

    def test_approve_removes_from_staged_list(self, api_client, staged_id):
        api_client.post(
            f"/api/receipts/staged/{staged_id}/approve",
            json=_approve_body(staged_id),
        )
        assert api_client.get("/api/receipts/staged").json() == []

    def test_approve_makes_visible_in_expenses(self, api_client, staged_id):
        api_client.post(
            f"/api/receipts/staged/{staged_id}/approve",
            json=_approve_body(staged_id),
        )
        expenses = api_client.get("/api/expenses").json()
        assert len(expenses) == 1
        assert expenses[0]["merchant_name"] == "Whole Foods Market"

    def test_approve_with_edited_data_saves_edits(self, api_client, staged_id):
        body = _approve_body(staged_id)
        body["merchant_name"] = "User Corrected Store"
        api_client.post(f"/api/receipts/staged/{staged_id}/approve", json=body)
        expenses = api_client.get("/api/expenses").json()
        assert expenses[0]["merchant_name"] == "User Corrected Store"

    def test_approve_nonexistent_returns_404(self, api_client):
        resp = api_client.post(
            "/api/receipts/staged/nonexistent_id/approve",
            json={"merchant_name": "X", "total": 1.00},
        )
        assert resp.status_code == 404


class TestRejectStaged:
    def test_reject_removes_from_staged_list(self, api_client, staged_id):
        resp = api_client.post(f"/api/receipts/staged/{staged_id}/reject")
        assert resp.status_code == 200
        assert api_client.get("/api/receipts/staged").json() == []

    def test_reject_does_not_appear_in_expenses(self, api_client, staged_id):
        api_client.post(f"/api/receipts/staged/{staged_id}/reject")
        assert api_client.get("/api/expenses").json() == []

    def test_reject_nonexistent_returns_200(self, api_client):
        # reject is idempotent — does not raise for missing IDs
        resp = api_client.post("/api/receipts/staged/nonexistent_id/reject")
        assert resp.status_code == 200


class TestReanalyzeStaged:
    def test_reanalyze_returns_new_staging_id(self, api_client, mock_llm, staged_id):
        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        resp = api_client.post(f"/api/receipts/staged/{staged_id}/reanalyze")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("error") is None
        assert body["staging_id"] is not None
        assert body["staging_id"] != staged_id

    def test_reanalyze_old_id_gone(self, api_client, mock_llm, staged_id):
        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        api_client.post(f"/api/receipts/staged/{staged_id}/reanalyze")
        assert api_client.get(f"/api/receipts/staged/{staged_id}").status_code == 404

    def test_reanalyze_nonexistent_returns_error(self, api_client):
        resp = api_client.post("/api/receipts/staged/nonexistent_id/reanalyze")
        assert resp.status_code == 200
        assert resp.json().get("error") is not None


class TestCheckDuplicate:
    def test_no_duplicate_empty_db(self, api_client):
        body = {"merchant_name": "Whole Foods Market", "total": 18.87, "date": "2026-03-15"}
        resp = api_client.post("/api/receipts/check-duplicate", json=body)
        assert resp.status_code == 200
        assert resp.json()["is_duplicate"] is False

    def test_duplicate_detected_after_approve(self, api_client, staged_id):
        api_client.post(
            f"/api/receipts/staged/{staged_id}/approve",
            json=_approve_body(staged_id),
        )
        body = {"merchant_name": "Whole Foods Market", "total": 18.87, "date": "2026-03-15"}
        resp = api_client.post("/api/receipts/check-duplicate", json=body)
        data = resp.json()
        assert data["is_duplicate"] is True
        assert data["existing_receipt"]["merchant_name"] == "Whole Foods Market"

    def test_no_duplicate_different_merchant(self, api_client, staged_id):
        api_client.post(
            f"/api/receipts/staged/{staged_id}/approve",
            json=_approve_body(staged_id),
        )
        body = {"merchant_name": "Target", "total": 18.87, "date": "2026-03-15"}
        resp = api_client.post("/api/receipts/check-duplicate", json=body)
        assert resp.json()["is_duplicate"] is False
