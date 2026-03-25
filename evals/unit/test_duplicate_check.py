"""Unit tests for fuzzy duplicate detection in staging.py."""
import datetime

import pytest

from agents.receipt_analyzer.staging import check_duplicate
from agents.receipt_analyzer.storage import save_receipt
from agents.receipt_analyzer.schemas import ReceiptRecord


pytestmark = pytest.mark.unit


def _save(merchant: str, date: str, total: float, category: str = "groceries") -> int:
    return save_receipt(ReceiptRecord(
        merchant_name=merchant,
        date=datetime.date.fromisoformat(date),
        total=total,
        category=category,
        file_path="/data/archive/test.jpg",
    ))


def _candidate(merchant: str, date: str, total: float) -> dict:
    return {"merchant_name": merchant, "date": date, "total": total}


class TestExactMatch:
    def test_exact_match_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-15", 18.87))
        assert result is not None
        assert result.merchant_name == "Whole Foods"

    def test_no_match_empty_db(self):
        assert check_duplicate(_candidate("Whole Foods", "2026-03-15", 18.87)) is None


class TestDateTolerance:
    def test_one_day_before_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-14", 18.87))
        assert result is not None

    def test_one_day_after_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-16", 18.87))
        assert result is not None

    def test_two_days_apart_not_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-17", 18.87))
        assert result is None


class TestTotalTolerance:
    def test_within_50_cents_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-15", 18.50))
        assert result is not None

    def test_exactly_50_cents_off_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-15", 18.37))
        assert result is not None

    def test_more_than_50_cents_off_not_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-15", 17.00))
        assert result is None


class TestFuzzyMerchantMatch:
    def test_typo_detected(self):
        _save("Shashimati S Kale MD", "2026-03-15", 50.00)
        result = check_duplicate(_candidate("Shasihati S Kale MD", "2026-03-15", 50.00))
        assert result is not None

    def test_abbreviation_detected(self):
        _save("Whole Foods Market", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-15", 18.87))
        assert result is not None

    def test_completely_different_merchant_not_detected(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Target", "2026-03-15", 18.87))
        assert result is None

    def test_case_insensitive(self):
        _save("whole foods", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("WHOLE FOODS", "2026-03-15", 18.87))
        assert result is not None


class TestMissingFields:
    def test_missing_date_returns_none(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate({"merchant_name": "Whole Foods", "total": 18.87})
        assert result is None

    def test_missing_total_returns_none(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate({"merchant_name": "Whole Foods", "date": "2026-03-15"})
        assert result is None

    def test_missing_merchant_returns_none(self):
        _save("Whole Foods", "2026-03-15", 18.87)
        result = check_duplicate({"date": "2026-03-15", "total": 18.87})
        assert result is None

    def test_empty_dict_returns_none(self):
        assert check_duplicate({}) is None


class TestMultipleCandidates:
    def test_returns_correct_match_among_many(self):
        _save("Target", "2026-03-15", 18.87)
        _save("Whole Foods", "2026-03-15", 18.87)
        _save("Costco", "2026-03-15", 18.87)
        result = check_duplicate(_candidate("Whole Foods", "2026-03-15", 18.87))
        assert result is not None
        assert result.merchant_name == "Whole Foods"
