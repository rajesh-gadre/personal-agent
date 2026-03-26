"""Live extraction tests: real LLM on real receipts, evaluated by OpenAI judge."""
import pytest

pytestmark = pytest.mark.live


# ── Grocery (HEIC format) ─────────────────────────────────────────────────────

class TestGroceryHeic:
    """Trader Joe's grocery receipt in HEIC format.

    Exercises: HEIC→JPEG conversion in the pipeline, grocery category extraction.
    Judge mode: ground truth (known category) + vision (full quality check).
    """

    def test_extraction_succeeds(self, live_mgr, grocery_heic):
        result = live_mgr.analyze(str(grocery_heic))
        assert result.get("error") is None
        assert result["staging_id"] is not None

    def test_is_valid_receipt(self, live_mgr, grocery_heic):
        result = live_mgr.analyze(str(grocery_heic))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is True

    def test_category_is_groceries(self, live_mgr, grocery_heic):
        result = live_mgr.analyze(str(grocery_heic))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["category"] == "groceries"

    def test_judge_ground_truth(self, live_mgr, grocery_heic, extraction_judge):
        result = live_mgr.analyze(str(grocery_heic))
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_ground_truth(
            staged["extracted_data"],
            {"is_valid_receipt": True, "category": "groceries", "currency": "USD"},
        )
        assert verdict.passed, f"Judge failed (score={verdict.overall_score}): {verdict.summary}"

    def test_judge_vision(self, live_mgr, grocery_heic, extraction_judge):
        result = live_mgr.analyze(str(grocery_heic))
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_image(
            staged["extracted_data"], grocery_heic
        )
        assert verdict.passed, f"Vision judge failed (score={verdict.overall_score}): {verdict.summary}"


# ── Restaurant (JPG) ──────────────────────────────────────────────────────────

class TestRestaurantJpg:
    """Italian restaurant receipt in JPG format.

    Exercises: tip field extraction, restaurant category.
    Judge mode: ground truth + vision.
    """

    def test_extraction_succeeds(self, live_mgr, restaurant_jpg):
        result = live_mgr.analyze(str(restaurant_jpg))
        assert result.get("error") is None
        assert result["staging_id"] is not None

    def test_is_valid_receipt(self, live_mgr, restaurant_jpg):
        result = live_mgr.analyze(str(restaurant_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is True

    def test_category_is_restaurant(self, live_mgr, restaurant_jpg):
        result = live_mgr.analyze(str(restaurant_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["category"] == "restaurant"

    def test_judge_ground_truth(self, live_mgr, restaurant_jpg, extraction_judge):
        result = live_mgr.analyze(str(restaurant_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_ground_truth(
            staged["extracted_data"],
            {"is_valid_receipt": True, "category": "restaurant", "currency": "USD"},
        )
        assert verdict.passed, f"Judge failed (score={verdict.overall_score}): {verdict.summary}"

    def test_judge_vision(self, live_mgr, restaurant_jpg, extraction_judge):
        result = live_mgr.analyze(str(restaurant_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_image(
            staged["extracted_data"], restaurant_jpg
        )
        assert verdict.passed, f"Vision judge failed (score={verdict.overall_score}): {verdict.summary}"


# ── Parking receipt (PDF) ─────────────────────────────────────────────────────

class TestParkingPdf:
    """Parking receipt as PDF.

    Exercises: PDF text extraction path (different code branch from images).
    Judge mode: ground truth only (vision not supported for PDFs).

    NOTE: Currently fails if the PDF is image-based (scanned, no text layer) —
    this is a known gap. Fix needed: OCR or image-extraction from PDF pages.
    """

    def test_extraction_succeeds(self, live_mgr, parking_pdf):
        result = live_mgr.analyze(str(parking_pdf))
        assert result.get("error") is None, (
            f"Pipeline error: {result.get('error')}. "
            "If this PDF is image-based/scanned, OCR support is needed."
        )
        assert result["staging_id"] is not None

    def test_is_valid_receipt(self, live_mgr, parking_pdf):
        result = live_mgr.analyze(str(parking_pdf))
        assert result.get("error") is None, result.get("error")
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is True

    def test_judge_ground_truth(self, live_mgr, parking_pdf, extraction_judge):
        result = live_mgr.analyze(str(parking_pdf))
        assert result.get("error") is None, result.get("error")
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_ground_truth(
            staged["extracted_data"],
            {"is_valid_receipt": True, "currency": "USD"},
        )
        assert verdict.passed, f"Judge failed (score={verdict.overall_score}): {verdict.summary}"


# ── Not a receipt ─────────────────────────────────────────────────────────────

class TestNotAReceipt:
    """Non-receipt image — the LLM must return is_valid_receipt=False.

    Judge mode: ground truth (verifies the flag is correct).
    """

    def test_extraction_succeeds(self, live_mgr, not_a_receipt_jpg):
        result = live_mgr.analyze(str(not_a_receipt_jpg))
        assert result.get("error") is None
        assert result["staging_id"] is not None

    def test_is_not_valid_receipt(self, live_mgr, not_a_receipt_jpg):
        result = live_mgr.analyze(str(not_a_receipt_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is False

    def test_judge_ground_truth(self, live_mgr, not_a_receipt_jpg, extraction_judge):
        result = live_mgr.analyze(str(not_a_receipt_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        # For invalid receipts, null fields are CORRECT — pass explicit nulls so the
        # judge doesn't penalise completeness.
        verdict = extraction_judge.evaluate_with_ground_truth(
            staged["extracted_data"],
            {"is_valid_receipt": False, "merchant_name": None, "total": None, "date": None},
        )
        assert verdict.passed, f"Judge failed (score={verdict.overall_score}): {verdict.summary}"


# ── Return receipt ────────────────────────────────────────────────────────────

class TestReturnReceipt:
    """Return/refund receipt — may have negative total or credit line items.

    Judge mode: vision (no fixed ground truth — judge reads the image to verify).
    """

    def test_extraction_succeeds(self, live_mgr, return_receipt_jpg):
        result = live_mgr.analyze(str(return_receipt_jpg))
        assert result.get("error") is None
        assert result["staging_id"] is not None

    def test_is_valid_receipt(self, live_mgr, return_receipt_jpg):
        result = live_mgr.analyze(str(return_receipt_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is True

    def test_judge_vision(self, live_mgr, return_receipt_jpg, extraction_judge):
        result = live_mgr.analyze(str(return_receipt_jpg))
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_image(
            staged["extracted_data"], return_receipt_jpg
        )
        assert verdict.passed, f"Vision judge failed (score={verdict.overall_score}): {verdict.summary}"


# ── Services receipt with negative line item (PNG) ────────────────────────────

class TestNegativeItemPng:
    """Services receipt with a negative line item (e.g. discount or credit).

    Exercises: negative amounts preserved through the pipeline.
    Judge mode: ground truth (verify negative item) + vision.
    """

    def test_extraction_succeeds(self, live_mgr, negative_item_png):
        result = live_mgr.analyze(str(negative_item_png))
        assert result.get("error") is None
        assert result["staging_id"] is not None

    def test_is_valid_receipt(self, live_mgr, negative_item_png):
        result = live_mgr.analyze(str(negative_item_png))
        staged = live_mgr.get_staged(result["staging_id"])
        assert staged["extracted_data"]["is_valid_receipt"] is True

    def test_has_negative_line_item(self, live_mgr, negative_item_png):
        result = live_mgr.analyze(str(negative_item_png))
        staged = live_mgr.get_staged(result["staging_id"])
        items = staged["extracted_data"].get("items") or []
        negatives = [i for i in items if i.get("total", 0) < 0]
        assert len(negatives) >= 1, "Expected at least one negative line item"

    def test_judge_vision(self, live_mgr, negative_item_png, extraction_judge):
        result = live_mgr.analyze(str(negative_item_png))
        staged = live_mgr.get_staged(result["staging_id"])
        verdict = extraction_judge.evaluate_with_image(
            staged["extracted_data"], negative_item_png
        )
        assert verdict.passed, f"Vision judge failed (score={verdict.overall_score}): {verdict.summary}"
