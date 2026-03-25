"""Live eval conftest: skip if no API key; load real receipt images."""
import os
from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip all live tests if ANTHROPIC_API_KEY is not set."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set — skipping live evals")
        for item in items:
            if "live" in str(item.fspath):
                item.add_marker(skip)


LIVE_RECEIPTS_DIR = Path(__file__).parent.parent / "fixtures" / "live_receipts"


@pytest.fixture(scope="session")
def live_receipt_images() -> list[Path]:
    """Return all real receipt images from fixtures/live_receipts/.

    Place real receipt images in evals/fixtures/live_receipts/ (gitignored).
    Supported formats: .png, .jpg, .jpeg, .heic, .heif, .pdf
    """
    supported = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".pdf"}
    images = [
        p for p in LIVE_RECEIPTS_DIR.iterdir()
        if p.suffix.lower() in supported and not p.name.startswith(".")
    ]
    if not images:
        pytest.skip("No images found in evals/fixtures/live_receipts/ — add real receipts to run live evals")
    return sorted(images)
