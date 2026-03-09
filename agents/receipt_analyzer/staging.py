import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from agents.receipt_analyzer.schemas import ReceiptRecord
from agents.receipt_analyzer.storage import get_receipt_by_id, save_receipt
from shared.config.settings import settings
from shared.storage.database import get_connection


def _staging_dir() -> Path:
    d = settings.receipt_staging_folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _archive_dir() -> Path:
    d = settings.receipt_archive_folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rejected_dir() -> Path:
    d = settings.receipt_rejected_folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def stage_receipt(file_path: str, extracted_data: dict) -> str:
    """Copy image to staging and write a JSON sidecar. Returns staging ID."""
    staging_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    src = Path(file_path)
    dest_image = _staging_dir() / f"{staging_id}{src.suffix}"
    shutil.copy2(str(src), str(dest_image))

    sidecar = {
        "staging_id": staging_id,
        "image_path": str(dest_image),
        "original_path": file_path,
        "extracted_data": extracted_data,
        "staged_at": datetime.now().isoformat(),
    }
    sidecar_path = _staging_dir() / f"{staging_id}.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2))
    return staging_id


def list_staged() -> list[dict]:
    """List all staged receipts, newest first."""
    results = []
    for f in sorted(_staging_dir().glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            results.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def get_staged(staging_id: str) -> dict | None:
    """Read a single staged receipt by ID."""
    sidecar_path = _staging_dir() / f"{staging_id}.json"
    if not sidecar_path.exists():
        return None
    return json.loads(sidecar_path.read_text())


def update_staged(staging_id: str, extracted_data: dict) -> None:
    """Update the extracted data in a sidecar JSON (for edits)."""
    sidecar_path = _staging_dir() / f"{staging_id}.json"
    if not sidecar_path.exists():
        return
    sidecar = json.loads(sidecar_path.read_text())
    sidecar["extracted_data"] = extracted_data
    sidecar_path.write_text(json.dumps(sidecar, indent=2))


def check_duplicate(data: dict) -> ReceiptRecord | None:
    """Fuzzy duplicate check. Returns the matching ReceiptRecord if likely duplicate found.

    Matching strategy:
    - Date: within +/- 1 day (handles LLM off-by-one errors)
    - Total: within +/- $0.50 (handles rounding differences)
    - Merchant: fuzzy string similarity >= 0.6 (handles OCR/LLM variations, typos)

    Uses difflib.SequenceMatcher for merchant comparison — no external dependencies.
    """
    from difflib import SequenceMatcher

    receipt_date = data.get("date")
    merchant = data.get("merchant_name")
    total = data.get("total")
    if not (receipt_date and merchant and total):
        return None

    total = float(total)

    # Step 1: SQL narrows candidates by date and total (cheap)
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, merchant_name FROM receipts
               WHERE date BETWEEN date(?, '-1 day') AND date(?, '+1 day')
               AND total BETWEEN ? AND ?""",
            (
                str(receipt_date),
                str(receipt_date),
                total - 0.50,
                total + 0.50,
            ),
        ).fetchall()

    if not rows:
        return None

    # Step 2: Fuzzy match merchant name in Python
    merchant_lower = merchant.strip().lower()
    for row in rows:
        candidate = (row["merchant_name"] or "").strip().lower()
        ratio = SequenceMatcher(None, merchant_lower, candidate).ratio()
        if ratio >= 0.6:
            return get_receipt_by_id(row["id"])

    return None


def approve_staged(staging_id: str) -> int:
    """Save staged receipt to DB, move image to archive, clean up staging files."""
    sidecar = get_staged(staging_id)
    if not sidecar:
        raise ValueError(f"Staging ID not found: {staging_id}")

    data = sidecar["extracted_data"]
    if data.get("items") is None:
        data["items"] = []
    image_path = Path(sidecar["image_path"])
    archive_path = _archive_dir() / image_path.name

    # Step 1: Validate data (fail fast, no side effects)
    # Strip extraction-only fields before passing to ReceiptRecord
    db_data = {k: v for k, v in data.items() if k != "is_valid_receipt"}
    # Normalize category to lowercase, fallback to "other"
    db_data["category"] = (db_data.get("category") or "other").lower()
    receipt = ReceiptRecord(file_path=str(archive_path), **db_data)

    # Step 2: Save to DB first (data is safe even if file move fails later)
    receipt_id = save_receipt(receipt)

    # Step 3: Move image to archive (if this fails, DB record exists with wrong path but data is safe)
    if image_path.exists():
        shutil.move(str(image_path), str(archive_path))

    # Step 4: Clean up sidecar (last step — everything else succeeded)
    sidecar_path = _staging_dir() / f"{staging_id}.json"
    sidecar_path.unlink(missing_ok=True)

    return receipt_id


def reject_staged(staging_id: str) -> None:
    """Move staged receipt image + sidecar to rejected folder."""
    sidecar = get_staged(staging_id)
    if not sidecar:
        return

    image_path = Path(sidecar["image_path"])
    sidecar_path = _staging_dir() / f"{staging_id}.json"

    if image_path.exists():
        shutil.move(str(image_path), str(_rejected_dir() / image_path.name))
    if sidecar_path.exists():
        shutil.move(str(sidecar_path), str(_rejected_dir() / sidecar_path.name))
