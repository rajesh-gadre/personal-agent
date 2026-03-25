"""E2E tests for the upload endpoint (POST /api/receipts/upload)."""
import io

import pytest
from PIL import Image

from shared.config.settings import settings

pytestmark = pytest.mark.e2e


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, format="PNG")
    return buf.getvalue()


def _make_file(name: str, data: bytes = None, content_type: str = "image/png"):
    return (name, data or _png_bytes(), content_type)


class TestUploadQueuing:
    def test_single_file_queued(self, api_client):
        resp = api_client.post(
            "/api/receipts/upload",
            files=[("files", _make_file("receipt.png"))],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] == 1
        assert body["filenames"] == ["receipt.png"]
        assert body["errors"] == []

    def test_multiple_files_queued(self, api_client):
        resp = api_client.post(
            "/api/receipts/upload",
            files=[
                ("files", _make_file("r1.png")),
                ("files", _make_file("r2.jpg", content_type="image/jpeg")),
            ],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] == 2
        assert len(body["filenames"]) == 2

    def test_files_written_to_incoming_folder(self, api_client):
        api_client.post(
            "/api/receipts/upload",
            files=[("files", _make_file("receipt.png"))],
        )
        assert (settings.receipt_incoming_folder / "receipt.png").exists()

    def test_duplicate_filename_renamed(self, api_client):
        # Upload the same filename twice
        api_client.post("/api/receipts/upload", files=[("files", _make_file("receipt.png"))])
        resp = api_client.post("/api/receipts/upload", files=[("files", _make_file("receipt.png"))])
        body = resp.json()
        assert body["queued"] == 1
        # Second file gets a renamed copy — original still exists
        assert (settings.receipt_incoming_folder / "receipt.png").exists()

    def test_pdf_accepted(self, api_client):
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        resp = api_client.post(
            "/api/receipts/upload",
            files=[("files", ("scan.pdf", pdf_bytes, "application/pdf"))],
        )
        assert resp.status_code == 200
        assert resp.json()["queued"] == 1


class TestUploadValidation:
    def test_unsupported_type_not_queued(self, api_client):
        resp = api_client.post(
            "/api/receipts/upload",
            files=[("files", ("notes.txt", b"hello", "text/plain"))],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] == 0
        assert len(body["errors"]) == 1
        assert "notes.txt" in body["errors"][0]

    def test_mixed_valid_invalid(self, api_client):
        resp = api_client.post(
            "/api/receipts/upload",
            files=[
                ("files", _make_file("receipt.png")),
                ("files", ("notes.txt", b"hello", "text/plain")),
            ],
        )
        body = resp.json()
        assert body["queued"] == 1
        assert len(body["errors"]) == 1

    def test_no_files_returns_422(self, api_client):
        resp = api_client.post("/api/receipts/upload")
        assert resp.status_code == 422
