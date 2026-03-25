"""Integration tests for the full staging workflow: analyze → approve/reject → query."""
import pytest

from agents.receipt_analyzer.agent import ReceiptAnalyzerAgent
from agents.receipt_analyzer.staging import approve_staged, get_staged, list_staged, reject_staged
from agents.receipt_analyzer.storage import get_receipt_by_id, query_receipts
from shared.config.settings import settings
from evals.fixtures.receipt_data import GROCERY_RECEIPT, NOT_A_RECEIPT, RESTAURANT_RECEIPT

pytestmark = pytest.mark.integration


@pytest.fixture
def agent():
    return ReceiptAnalyzerAgent()


class TestApproveWorkflow:
    def test_approve_saves_to_db(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        receipt_id = approve_staged(result["staging_id"])
        record = get_receipt_by_id(receipt_id)
        assert record is not None
        assert record.merchant_name == "Whole Foods Market"
        assert record.total == pytest.approx(18.87)
        assert record.category == "groceries"

    def test_approve_removes_sidecar_from_staging(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staging_id = result["staging_id"]
        approve_staged(staging_id)
        assert get_staged(staging_id) is None
        assert list_staged() == []

    def test_approve_moves_image_to_archive(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staging_id = result["staging_id"]
        image_name = get_staged(staging_id)["image_path"].split("/")[-1]
        approve_staged(staging_id)
        assert (settings.receipt_archive_folder / image_name).exists()

    def test_approve_returns_positive_id(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        receipt_id = approve_staged(result["staging_id"])
        assert isinstance(receipt_id, int)
        assert receipt_id > 0

    def test_approve_nonexistent_raises(self):
        with pytest.raises(ValueError):
            approve_staged("nonexistent_staging_id")

    def test_multiple_approvals_all_queryable(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r1 = agent.process_receipt(str(sample_image_path))
        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        r2 = agent.process_receipt(str(sample_image_path))

        approve_staged(r1["staging_id"])
        approve_staged(r2["staging_id"])

        records = query_receipts()
        assert len(records) == 2
        categories = {r.category for r in records}
        assert "groceries" in categories
        assert "restaurant" in categories


class TestRejectWorkflow:
    def test_reject_removes_from_staging(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staging_id = result["staging_id"]
        reject_staged(staging_id)
        assert get_staged(staging_id) is None

    def test_reject_moves_image_to_rejected_folder(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staging_id = result["staging_id"]
        image_name = get_staged(staging_id)["image_path"].split("/")[-1]
        reject_staged(staging_id)
        assert (settings.receipt_rejected_folder / image_name).exists()

    def test_reject_moves_sidecar_to_rejected_folder(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staging_id = result["staging_id"]
        reject_staged(staging_id)
        assert (settings.receipt_rejected_folder / f"{staging_id}.json").exists()

    def test_reject_does_not_save_to_db(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        reject_staged(result["staging_id"])
        assert query_receipts() == []

    def test_reject_nonexistent_does_not_raise(self):
        reject_staged("nonexistent_staging_id")  # should not raise

    def test_invalid_receipt_can_be_rejected(self, agent, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        result = agent.process_receipt(str(sample_invalid_image_path))
        staging_id = result["staging_id"]
        reject_staged(staging_id)
        assert get_staged(staging_id) is None


class TestMixedWorkflow:
    def test_approve_one_reject_one(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        r1 = agent.process_receipt(str(sample_image_path))
        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        r2 = agent.process_receipt(str(sample_image_path))

        approve_staged(r1["staging_id"])
        reject_staged(r2["staging_id"])

        # Only the approved one in DB
        records = query_receipts()
        assert len(records) == 1
        assert records[0].category == "groceries"

        # Nothing left in staging
        assert list_staged() == []
