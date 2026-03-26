"""Root conftest: fixtures shared across all eval tiers."""
import pytest
from PIL import Image, ImageDraw

from agents.receipt_analyzer.storage import init_receipt_tables
from shared.config.settings import settings


# ── Mock LLM ──────────────────────────────────────────────────────────────────

class MockLLMController:
    """Controls sequential mock responses for the two-LLM-call pipeline.

    Usage:
        ctrl = MockLLMController()
        ctrl.add_response(GROCERY_RECEIPT)       # call 1: extract
        ctrl.add_response(GROCERY_RECEIPT)       # call 2: validate
        monkeypatch.setattr("agents.receipt_analyzer.graph.get_llm", ctrl.as_get_llm())
    """

    def __init__(self):
        self.responses: list = []
        self.call_count: int = 0

    def add_response(self, result) -> "MockLLMController":
        self.responses.append(result)
        return self  # allow chaining

    def as_get_llm(self):
        """Return a callable that replaces get_llm() in the graph module."""
        ctrl = self

        class _StructuredLLM:
            def invoke(self, messages):
                idx = ctrl.call_count
                ctrl.call_count += 1
                if idx >= len(ctrl.responses):
                    raise IndexError(
                        f"MockLLMController has no response for call #{idx}. "
                        f"Add more responses via add_response()."
                    )
                return ctrl.responses[idx]

        class _MockLLM:
            def with_structured_output(self, schema):
                return _StructuredLLM()

        def _get_llm():
            return _MockLLM()

        return _get_llm


# ── Environment isolation ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Isolate every test with a fresh temp DB and temp folders.

    Patches all path settings on the shared settings singleton so no test
    touches the real DB or data folders.
    """
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "receipt_staging_folder", tmp_path / "staging")
    monkeypatch.setattr(settings, "receipt_archive_folder", tmp_path / "archive")
    monkeypatch.setattr(settings, "receipt_rejected_folder", tmp_path / "rejected")
    monkeypatch.setattr(settings, "receipt_watch_folder", tmp_path / "watch")
    monkeypatch.setattr(settings, "receipt_incoming_folder", tmp_path / "incoming")

    for folder in ("staging", "archive", "rejected", "watch", "incoming"):
        (tmp_path / folder).mkdir()

    init_receipt_tables()
    yield


# ── Mock LLM fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_controller():
    """Return a fresh MockLLMController for the test to configure."""
    return MockLLMController()


@pytest.fixture
def mock_llm(monkeypatch, mock_llm_controller):
    """Patch get_llm in the graph module. Returns the controller for response setup."""
    monkeypatch.setattr(
        "agents.receipt_analyzer.graph.get_llm",
        mock_llm_controller.as_get_llm(),
    )
    return mock_llm_controller


# ── Sample images ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_image_path(tmp_path_factory):
    """A minimal synthetic grocery receipt PNG (session-scoped, created once)."""
    img_dir = tmp_path_factory.mktemp("sample_images")
    img_path = img_dir / "grocery_receipt.png"
    img = Image.new("RGB", (400, 650), "white")
    draw = ImageDraw.Draw(img)
    lines = [
        (20, 20,  "WHOLE FOODS MARKET"),
        (20, 40,  "123 Main St, San Francisco CA"),
        (20, 80,  "Date: 2026-03-15"),
        (20, 120, "Organic Milk         $4.99"),
        (20, 140, "Sourdough Bread      $6.49"),
        (20, 160, "Free Range Eggs      $5.99"),
        (20, 200, "Subtotal:           $17.47"),
        (20, 220, "Tax:                 $1.40"),
        (20, 240, "Total:              $18.87"),
        (20, 280, "VISA ending 4242"),
    ]
    for x, y, text in lines:
        draw.text((x, y), text, fill="black")
    img.save(img_path)
    return img_path


@pytest.fixture(scope="session")
def sample_invalid_image_path(tmp_path_factory):
    """A non-receipt image (solid color, no text) for invalid-receipt tests."""
    img_dir = tmp_path_factory.mktemp("sample_images_invalid")
    img_path = img_dir / "not_a_receipt.png"
    img = Image.new("RGB", (400, 300), color=(100, 149, 237))  # cornflower blue
    img.save(img_path)
    return img_path


# ── API client ────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client(isolated_environment):
    """FastAPI TestClient with isolated DB and folders.

    `isolated_environment` is listed explicitly to ensure ordering (DB tables
    must exist before the app lifespan runs init_receipt_tables again).
    """
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        yield client
