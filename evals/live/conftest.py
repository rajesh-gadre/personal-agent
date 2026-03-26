"""Live eval conftest: skip if API keys missing; fixtures for receipts and judge."""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()  # ensure .env is loaded before API key checks

from agents.receipt_analyzer.manager import ReceiptManager
from evals.judges.extraction_judge import ExtractionJudge


LIVE_RECEIPTS_DIR = Path(__file__).parent.parent / "fixtures" / "live_receipts"


def pytest_collection_modifyitems(config, items):
    """Skip all live tests if either API key is missing."""
    missing = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    if missing:
        reason = f"Missing env vars: {', '.join(missing)} — skipping live evals"
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if "live" in str(item.fspath):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def live_receipt_images() -> list[Path]:
    """All real receipt images from fixtures/live_receipts/ (sorted)."""
    supported = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".pdf"}
    images = [
        p for p in LIVE_RECEIPTS_DIR.iterdir()
        if p.suffix.lower() in supported and not p.name.startswith(".")
    ]
    if not images:
        pytest.skip("No images found in evals/fixtures/live_receipts/")
    return sorted(images)


def _live_receipt(name: str) -> Path:
    """Return path to a named receipt, skipping the test if the file doesn't exist."""
    path = LIVE_RECEIPTS_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not found in live_receipts/ — skipping")
    return path


# ── Per-receipt path fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def grocery_heic() -> Path:
    return _live_receipt("grocery_TraderJoes.HEIC")


@pytest.fixture(scope="session")
def restaurant_jpg() -> Path:
    return _live_receipt("restaurant_italian.jpg")


@pytest.fixture(scope="session")
def parking_pdf() -> Path:
    return _live_receipt("parking_receipt_pdf.pdf")


@pytest.fixture(scope="session")
def not_a_receipt_jpg() -> Path:
    return _live_receipt("not_a_receipt.jpg")


@pytest.fixture(scope="session")
def return_receipt_jpg() -> Path:
    return _live_receipt("return_receipt.jpg")


@pytest.fixture(scope="session")
def negative_item_png() -> Path:
    return _live_receipt("services_receipt_with_negative_item.png")


# ── Manager and judge fixtures ────────────────────────────────────────────────

@pytest.fixture
def live_mgr():
    """ReceiptManager backed by the isolated temp DB (via autouse isolated_environment)."""
    return ReceiptManager()


@pytest.fixture(scope="session")
def extraction_judge() -> ExtractionJudge:
    """ExtractionJudge using OpenAI GPT-4o (session-scoped — one instance per run)."""
    return ExtractionJudge()
