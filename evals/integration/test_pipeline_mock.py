"""Integration tests for the full LangGraph pipeline with mocked LLM."""
import pytest

from agents.receipt_analyzer.agent import ReceiptAnalyzerAgent
from agents.receipt_analyzer.staging import get_staged
from evals.fixtures.receipt_data import (
    GROCERY_BAD_MATH,
    GROCERY_CORRECTED,
    GROCERY_RECEIPT,
    NOT_A_RECEIPT,
    RESTAURANT_RECEIPT,
    TRADE_IN_RECEIPT,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def agent():
    return ReceiptAnalyzerAgent()


class TestValidReceipt:
    def test_two_llm_calls_for_valid_receipt(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        agent.process_receipt(str(sample_image_path))
        assert mock_llm.call_count == 2

    def test_valid_receipt_has_no_error(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        assert result.get("error") is None

    def test_valid_receipt_has_staging_id(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        assert result["staging_id"] is not None
        parts = result["staging_id"].split("_")
        assert len(parts) == 3

    def test_staged_data_matches_mock_output(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staged = get_staged(result["staging_id"])
        data = staged["extracted_data"]
        assert data["merchant_name"] == "Whole Foods Market"
        assert data["total"] == 18.87
        assert data["category"] == "groceries"
        assert data["is_valid_receipt"] is True

    def test_validation_output_used_when_available(self, agent, mock_llm, sample_image_path):
        """Validation LLM output (call 2) should override extraction (call 1)."""
        mock_llm.add_response(GROCERY_BAD_MATH).add_response(GROCERY_CORRECTED)
        result = agent.process_receipt(str(sample_image_path))
        staged = get_staged(result["staging_id"])
        # validated_data has corrected total (12.88), not bad extraction (99.99)
        assert staged["extracted_data"]["total"] == pytest.approx(12.88)

    def test_line_items_preserved_in_staging(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staged = get_staged(result["staging_id"])
        items = staged["extracted_data"]["items"]
        assert len(items) == 3
        assert items[0]["description"] == "Organic Milk"


class TestInvalidReceipt:
    def test_one_llm_call_for_invalid_receipt(self, agent, mock_llm, sample_invalid_image_path):
        """Validation node must be skipped for non-receipts."""
        mock_llm.add_response(NOT_A_RECEIPT)
        agent.process_receipt(str(sample_invalid_image_path))
        assert mock_llm.call_count == 1

    def test_invalid_receipt_staged_with_flag(self, agent, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        result = agent.process_receipt(str(sample_invalid_image_path))
        staged = get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is False

    def test_invalid_receipt_has_no_error(self, agent, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        result = agent.process_receipt(str(sample_invalid_image_path))
        assert result.get("error") is None

    def test_invalid_receipt_has_staging_id(self, agent, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        result = agent.process_receipt(str(sample_invalid_image_path))
        assert result["staging_id"] is not None


class TestUnsupportedFileType:
    def test_unsupported_extension_returns_error(self, agent, tmp_path):
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("not a receipt")
        result = agent.process_receipt(str(txt_file))
        assert result["error"] is not None

    def test_no_llm_call_for_unsupported_type(self, agent, mock_llm, tmp_path):
        mock_llm.add_response(GROCERY_RECEIPT)  # should never be consumed
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("not a receipt")
        agent.process_receipt(str(txt_file))
        assert mock_llm.call_count == 0

    def test_no_staging_id_on_error(self, agent, tmp_path):
        txt_file = tmp_path / "scan.doc"
        txt_file.write_text("not a receipt")
        result = agent.process_receipt(str(txt_file))
        assert result.get("staging_id") is None


class TestNegativeLineItems:
    def test_trade_in_negative_item_preserved(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(TRADE_IN_RECEIPT).add_response(TRADE_IN_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staged = get_staged(result["staging_id"])
        items = staged["extracted_data"]["items"]
        negatives = [i for i in items if i["total"] < 0]
        assert len(negatives) == 1
        assert negatives[0]["total"] == pytest.approx(-350.0)

    def test_trade_in_total_correct(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(TRADE_IN_RECEIPT).add_response(TRADE_IN_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staged = get_staged(result["staging_id"])
        assert staged["extracted_data"]["total"] == pytest.approx(1025.0)

    def test_trade_in_has_two_items(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(TRADE_IN_RECEIPT).add_response(TRADE_IN_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        staged = get_staged(result["staging_id"])
        assert len(staged["extracted_data"]["items"]) == 2


class TestReanalyze:
    def test_reanalyze_removes_old_staging_id(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        old_id = result["staging_id"]

        # Add responses for the reanalyze pipeline run
        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        agent.reanalyze(old_id)

        assert get_staged(old_id) is None

    def test_reanalyze_creates_new_staging_entry(self, agent, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        result = agent.process_receipt(str(sample_image_path))
        old_id = result["staging_id"]

        mock_llm.add_response(RESTAURANT_RECEIPT).add_response(RESTAURANT_RECEIPT)
        new_result = agent.reanalyze(old_id)

        new_id = new_result.get("staging_id")
        assert new_id is not None
        assert new_id != old_id
        assert get_staged(new_id) is not None

    def test_reanalyze_nonexistent_returns_error(self, agent):
        result = agent.reanalyze("nonexistent_id")
        assert "error" in result
