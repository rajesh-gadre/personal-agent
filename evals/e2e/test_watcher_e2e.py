"""E2E tests for the watcher: drop file → process → staged."""
import shutil

import pytest
from PIL import Image

from agents.receipt_analyzer.watcher import _process_file, _scan_existing
from agents.receipt_analyzer.staging import list_staged
from shared.config.settings import settings
from evals.fixtures.receipt_data import GROCERY_RECEIPT, NOT_A_RECEIPT

pytestmark = pytest.mark.e2e


def _drop_image(dest_dir, name="receipt.png") -> object:
    """Write a minimal PNG into dest_dir. Returns the Path."""
    path = dest_dir / name
    Image.new("RGB", (100, 100), "white").save(path)
    return path


class TestProcessFile:
    def test_valid_image_staged(self, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        # Copy sample image into incoming folder
        dest = settings.receipt_incoming_folder / "receipt.png"
        shutil.copy(str(sample_image_path), dest)

        _process_file(dest)

        staged = list_staged()
        assert len(staged) == 1
        assert staged[0]["extracted_data"]["merchant_name"] == "Whole Foods Market"

    def test_original_deleted_after_success(self, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        dest = settings.receipt_incoming_folder / "receipt.png"
        shutil.copy(str(sample_image_path), dest)

        _process_file(dest)

        assert not dest.exists()

    def test_invalid_receipt_still_staged(self, mock_llm, sample_invalid_image_path):
        mock_llm.add_response(NOT_A_RECEIPT)
        dest = settings.receipt_incoming_folder / "not_receipt.png"
        shutil.copy(str(sample_invalid_image_path), dest)

        _process_file(dest)

        staged = list_staged()
        assert len(staged) == 1
        assert staged[0]["extracted_data"]["is_valid_receipt"] is False

    def test_unsupported_file_not_staged(self, tmp_path):
        txt = settings.receipt_incoming_folder / "notes.txt"
        txt.write_text("not a receipt")

        _process_file(txt)

        # File remains (watcher only deletes on success) and nothing staged
        assert len(list_staged()) == 0


class TestScanExisting:
    def test_scan_processes_files_in_folder(self, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)

        shutil.copy(str(sample_image_path), settings.receipt_incoming_folder / "r1.png")
        shutil.copy(str(sample_image_path), settings.receipt_incoming_folder / "r2.png")

        _scan_existing(settings.receipt_incoming_folder)

        assert len(list_staged()) == 2

    def test_scan_clears_incoming_folder(self, mock_llm, sample_image_path):
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        shutil.copy(str(sample_image_path), settings.receipt_incoming_folder / "receipt.png")

        _scan_existing(settings.receipt_incoming_folder)

        remaining = list(settings.receipt_incoming_folder.iterdir())
        assert remaining == []

    def test_scan_empty_folder_no_error(self):
        # Should not raise even if folder is empty
        _scan_existing(settings.receipt_incoming_folder)
        assert list_staged() == []

    def test_scan_skips_hidden_files(self, mock_llm, sample_image_path):
        hidden = settings.receipt_incoming_folder / ".DS_Store"
        hidden.write_bytes(b"")

        _scan_existing(settings.receipt_incoming_folder)

        assert list_staged() == []
        assert hidden.exists()  # hidden file left untouched

    def test_scan_watch_folder(self, mock_llm, sample_image_path):
        """Watcher should also process files dropped in the watch folder."""
        mock_llm.add_response(GROCERY_RECEIPT).add_response(GROCERY_RECEIPT)
        shutil.copy(str(sample_image_path), settings.receipt_watch_folder / "receipt.png")

        _scan_existing(settings.receipt_watch_folder)

        assert len(list_staged()) == 1
