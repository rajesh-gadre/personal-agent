from pathlib import Path

from shared.config.settings import settings


def path_to_image_url(file_path: str | None) -> str:
    """Convert a filesystem path to an API image URL."""
    if not file_path:
        return ""
    p = Path(file_path)
    staging = str(settings.receipt_staging_folder.resolve())
    archive = str(settings.receipt_archive_folder.resolve())
    rejected = str(settings.receipt_rejected_folder.resolve())
    resolved = str(p.resolve())

    if resolved.startswith(staging):
        return f"/api/receipts/image/staging/{p.name}"
    elif resolved.startswith(archive):
        return f"/api/receipts/image/archive/{p.name}"
    elif resolved.startswith(rejected):
        return f"/api/receipts/image/rejected/{p.name}"
    # Fallback: try matching by parent folder name
    parent = p.parent.name
    if parent in ("staging", "archive", "rejected"):
        return f"/api/receipts/image/{parent}/{p.name}"
    return ""
