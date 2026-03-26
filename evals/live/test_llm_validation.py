"""Live validation tests: verify the validation LLM corrects and normalises extraction output."""
import pytest

pytestmark = pytest.mark.live

# Tolerance for floating-point arithmetic checks
ARITHMETIC_TOLERANCE = 0.10  # $0.10


def _staged_data(live_mgr, path) -> dict:
    result = live_mgr.analyze(str(path))
    assert result.get("error") is None, f"Pipeline error: {result.get('error')}"
    staged = live_mgr.get_staged(result["staging_id"])
    return staged["extracted_data"]


# ── Arithmetic consistency ────────────────────────────────────────────────────

class TestArithmeticConsistency:
    """After the full pipeline (extract + validate), totals must be consistent.

    The validation LLM is responsible for correcting arithmetic errors from
    the extraction step. These tests verify the final staged output is coherent.
    """

    def test_grocery_totals_consistent(self, live_mgr, grocery_heic):
        data = _staged_data(live_mgr, grocery_heic)
        assert data.get("is_valid_receipt") is True, "LLM incorrectly classified a grocery receipt as invalid"
        _assert_arithmetic(data)

    def test_restaurant_totals_consistent(self, live_mgr, restaurant_jpg):
        data = _staged_data(live_mgr, restaurant_jpg)
        assert data.get("is_valid_receipt") is True, "LLM incorrectly classified a restaurant receipt as invalid"
        _assert_arithmetic(data)

    def test_parking_pdf_totals_consistent(self, live_mgr, parking_pdf):
        data = _staged_data(live_mgr, parking_pdf)
        assert data.get("is_valid_receipt") is True, "LLM incorrectly classified a parking receipt as invalid"
        _assert_arithmetic(data)

    def test_negative_item_totals_consistent(self, live_mgr, negative_item_png):
        data = _staged_data(live_mgr, negative_item_png)
        assert data.get("is_valid_receipt") is True, "LLM incorrectly classified a services receipt as invalid"
        _assert_arithmetic(data)


def _assert_arithmetic(data: dict):
    """Assert subtotal + tax + tip ≈ total (within tolerance)."""
    total = data.get("total")
    subtotal = data.get("subtotal")
    tax = data.get("tax") or 0.0
    tip = data.get("tip") or 0.0

    if total is None or subtotal is None:
        return  # not enough data to check

    expected = subtotal + tax + tip
    diff = abs(total - expected)
    assert diff <= ARITHMETIC_TOLERANCE, (
        f"Arithmetic inconsistency: subtotal({subtotal}) + tax({tax}) + tip({tip}) "
        f"= {expected:.2f}, but total = {total:.2f} (diff={diff:.2f})"
    )


# ── Category normalisation ────────────────────────────────────────────────────

class TestCategoryNormalisation:
    """The validation step must produce lowercase category values."""

    def test_grocery_category_lowercase(self, live_mgr, grocery_heic):
        data = _staged_data(live_mgr, grocery_heic)
        if data.get("category"):
            assert data["category"] == data["category"].lower(), (
                f"Category not lowercase: {data['category']!r}"
            )

    def test_restaurant_category_lowercase(self, live_mgr, restaurant_jpg):
        data = _staged_data(live_mgr, restaurant_jpg)
        if data.get("category"):
            assert data["category"] == data["category"].lower()

    def test_parking_category_lowercase(self, live_mgr, parking_pdf):
        data = _staged_data(live_mgr, parking_pdf)
        if data.get("category"):
            assert data["category"] == data["category"].lower()


# ── Date format ───────────────────────────────────────────────────────────────

class TestDateFormat:
    """Dates must be in YYYY-MM-DD ISO format (or absent)."""

    def test_grocery_date_format(self, live_mgr, grocery_heic):
        data = _staged_data(live_mgr, grocery_heic)
        _assert_date_format(data.get("date"))

    def test_restaurant_date_format(self, live_mgr, restaurant_jpg):
        data = _staged_data(live_mgr, restaurant_jpg)
        _assert_date_format(data.get("date"))

    def test_parking_date_format(self, live_mgr, parking_pdf):
        data = _staged_data(live_mgr, parking_pdf)
        _assert_date_format(data.get("date"))


def _assert_date_format(date_val):
    if date_val is None:
        return  # absent date is acceptable
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_val)), (
        f"Date not in YYYY-MM-DD format: {date_val!r}"
    )


# ── Invalid receipt not corrected ─────────────────────────────────────────────

class TestInvalidReceiptUnchanged:
    """Validation must not invent data for non-receipts.

    The validation node is skipped for is_valid_receipt=False, so the staged
    output should have null fields — not fabricated merchant/totals.
    """

    def test_no_merchant_for_invalid(self, live_mgr, not_a_receipt_jpg):
        data = _staged_data(live_mgr, not_a_receipt_jpg)
        assert data.get("is_valid_receipt") is False
        assert data.get("merchant_name") is None

    def test_no_total_for_invalid(self, live_mgr, not_a_receipt_jpg):
        data = _staged_data(live_mgr, not_a_receipt_jpg)
        assert data.get("is_valid_receipt") is False
        assert data.get("total") is None
