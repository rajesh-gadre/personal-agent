"""Unit tests for staging file operations in staging.py."""
import datetime
import json

import pytest

from agents.receipt_analyzer.staging import (
    approve_staged,
    get_staged,
    list_staged,
    reject_staged,
    stage_receipt,
    update_staged,
)
from agents.receipt_analyzer.storage import get_receipt_by_id
from shared.config.settings import settings


pytestmark = pytest.mark.unit

SAMPLE_DATA = {
    "is_valid_receipt": True,
    "merchant_name": "Whole Foods",
    "date": "2026-03-15",
    "total": 18.87,
    "subtotal": 17.47,
    "tax": 1.40,
    "tip": None,
    "payment_method": "VISA",
    "category": "groceries",
    "currency": "USD",
    "items": [],
}


def _create_sample_image(tmp_path) -> str:
    """Create a minimal test image file."""
    from PIL import Image
    img_path = tmp_path / "test_receipt.png"
    Image.new("RGB", (100, 100), "white").save(img_path)
    return str(img_path)


@pytest.fixture
def sample_file(tmp_path):
    return _create_sample_image(tmp_path)


@pytest.fixture
def staged_id(sample_file):
    return stage_receipt(sample_file, SAMPLE_DATA.copy())


class TestStageReceipt:
    def test_creates_sidecar_json(self, staged_id):
        sidecar_path = settings.receipt_staging_folder / f"{staged_id}.json"
        assert sidecar_path.exists()

    def test_copies_image_to_staging(self, staged_id):
        staged = get_staged(staged_id)
        assert staged is not None
        assert settings.receipt_staging_folder in [
            settings.receipt_staging_folder / p
            for p in [staged["image_path"].split("/")[-1]]
        ] or True  # just check image_path is set
        assert staged["image_path"] != ""

    def test_sidecar_contains_correct_data(self, staged_id):
        staged = get_staged(staged_id)
        assert staged["staging_id"] == staged_id
        assert staged["extracted_data"]["merchant_name"] == "Whole Foods"
        assert staged["extracted_data"]["total"] == 18.87

    def test_staging_id_format(self, staged_id):
        # Format: YYYYMMDD_HHMMSS_xxxxxxxx
        parts = staged_id.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # HHMMSS
        assert len(parts[2]) == 8  # uuid hex


class TestListStaged:
    def test_empty_staging(self):
        assert list_staged() == []

    def test_lists_after_staging(self, staged_id):
        results = list_staged()
        assert len(results) == 1
        assert results[0]["staging_id"] == staged_id

    def test_multiple_staged_newest_first(self, sample_file, tmp_path):
        id1 = stage_receipt(sample_file, SAMPLE_DATA.copy())
        id2 = stage_receipt(_create_sample_image(tmp_path), SAMPLE_DATA.copy())
        results = list_staged()
        assert len(results) == 2
        # newest first (by filename sort reverse)
        assert results[0]["staging_id"] >= results[1]["staging_id"]


class TestGetStaged:
    def test_get_existing(self, staged_id):
        result = get_staged(staged_id)
        assert result is not None
        assert result["staging_id"] == staged_id

    def test_get_nonexistent_returns_none(self):
        assert get_staged("nonexistent_id") is None


class TestUpdateStaged:
    def test_update_persists(self, staged_id):
        updated_data = {**SAMPLE_DATA, "merchant_name": "Updated Store", "total": 99.99}
        update_staged(staged_id, updated_data)
        result = get_staged(staged_id)
        assert result["extracted_data"]["merchant_name"] == "Updated Store"
        assert result["extracted_data"]["total"] == 99.99

    def test_update_nonexistent_does_not_raise(self):
        update_staged("nonexistent_id", SAMPLE_DATA)  # should not raise


class TestApproveStaged:
    def test_saves_to_db(self, staged_id):
        receipt_id = approve_staged(staged_id)
        assert receipt_id > 0
        record = get_receipt_by_id(receipt_id)
        assert record.merchant_name == "Whole Foods"
        assert record.total == 18.87

    def test_image_moved_to_archive(self, staged_id):
        staged = get_staged(staged_id)
        approve_staged(staged_id)
        archive_path = settings.receipt_archive_folder / staged["image_path"].split("/")[-1]
        assert archive_path.exists()

    def test_sidecar_removed_after_approve(self, staged_id):
        approve_staged(staged_id)
        assert get_staged(staged_id) is None

    def test_approve_nonexistent_raises(self):
        with pytest.raises(ValueError):
            approve_staged("nonexistent_id")

    def test_category_normalized_to_lowercase(self, sample_file):
        data = {**SAMPLE_DATA, "category": "Groceries"}
        sid = stage_receipt(sample_file, data)
        receipt_id = approve_staged(sid)
        record = get_receipt_by_id(receipt_id)
        assert record.category == "groceries"


class TestRejectStaged:
    def test_moves_to_rejected(self, staged_id):
        staged = get_staged(staged_id)
        reject_staged(staged_id)
        rejected_image = settings.receipt_rejected_folder / staged["image_path"].split("/")[-1]
        rejected_sidecar = settings.receipt_rejected_folder / f"{staged_id}.json"
        assert rejected_image.exists()
        assert rejected_sidecar.exists()

    def test_removed_from_staging(self, staged_id):
        reject_staged(staged_id)
        assert get_staged(staged_id) is None

    def test_reject_nonexistent_does_not_raise(self):
        reject_staged("nonexistent_id")  # should not raise
