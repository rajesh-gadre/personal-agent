"""Unit tests for the detect_file_type graph node."""
import pytest

from agents.receipt_analyzer.graph import detect_file_type


pytestmark = pytest.mark.unit


def _state(filename: str) -> dict:
    return {"file_path": f"/tmp/{filename}"}


class TestDetectFileType:
    def test_png(self):
        assert detect_file_type(_state("receipt.png")) == {"file_type": "image"}

    def test_jpg(self):
        assert detect_file_type(_state("receipt.jpg")) == {"file_type": "image"}

    def test_jpeg(self):
        assert detect_file_type(_state("receipt.jpeg")) == {"file_type": "image"}

    def test_heic(self):
        assert detect_file_type(_state("receipt.HEIC")) == {"file_type": "image"}

    def test_heif(self):
        assert detect_file_type(_state("receipt.heif")) == {"file_type": "image"}

    def test_webp(self):
        assert detect_file_type(_state("receipt.webp")) == {"file_type": "image"}

    def test_gif(self):
        assert detect_file_type(_state("receipt.gif")) == {"file_type": "image"}

    def test_pdf(self):
        assert detect_file_type(_state("receipt.pdf")) == {"file_type": "pdf"}

    def test_txt_unsupported(self):
        result = detect_file_type(_state("notes.txt"))
        assert "error" in result

    def test_doc_unsupported(self):
        result = detect_file_type(_state("scan.doc"))
        assert "error" in result

    def test_no_extension(self):
        result = detect_file_type(_state("receipt"))
        assert "error" in result

    def test_uppercase_pdf(self):
        assert detect_file_type(_state("RECEIPT.PDF")) == {"file_type": "pdf"}

    def test_mixed_case_jpg(self):
        assert detect_file_type(_state("Photo.JPG")) == {"file_type": "image"}
