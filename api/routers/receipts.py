import io
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from api import mgr
from api.image import path_to_image_url
from api.models import (
    AnalyzeResponse,
    DuplicateCheckResponse,
    ReceiptEditData,
    ReceiptResponse,
    StagedReceiptResponse,
)
from shared.config.settings import settings

router = APIRouter(tags=["receipts"])

UPLOAD_DIR = Path("./data/uploads")


# ── Image serving ──


@router.get("/receipts/image/{source}/{filename}")
async def serve_image(source: str, filename: str):
    folder_map = {
        "staging": settings.receipt_staging_folder,
        "archive": settings.receipt_archive_folder,
        "rejected": settings.receipt_rejected_folder,
    }
    folder = folder_map.get(source)
    if not folder:
        raise HTTPException(status_code=404, detail="Unknown image source")
    file_path = folder / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    MAX_WEB_SIZE = 1200  # Max dimension for web display

    if file_path.suffix.lower() in (".heic", ".heif"):
        # Convert HEIC→JPEG and cache to disk
        cached = file_path.with_suffix(".web.jpg")
        if not cached.exists():
            from PIL import Image
            from pillow_heif import register_heif_opener

            register_heif_opener()
            img = Image.open(str(file_path))
            img.thumbnail((MAX_WEB_SIZE, MAX_WEB_SIZE), Image.LANCZOS)
            img.save(str(cached), format="JPEG", quality=85)
        return FileResponse(str(cached), media_type="image/jpeg", headers=_cache_headers())

    # For large non-HEIC images, resize and cache too
    if file_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        size = file_path.stat().st_size
        if size > 500_000:  # Only resize if >500KB
            cached = file_path.with_suffix(".web.jpg")
            if not cached.exists():
                from PIL import Image

                img = Image.open(str(file_path))
                if max(img.size) > MAX_WEB_SIZE:
                    img.thumbnail((MAX_WEB_SIZE, MAX_WEB_SIZE), Image.LANCZOS)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(str(cached), format="JPEG", quality=85)
            return FileResponse(str(cached), media_type="image/jpeg", headers=_cache_headers())

    return FileResponse(str(file_path), headers=_cache_headers())


def _cache_headers() -> dict:
    return {"Cache-Control": "public, max-age=86400"}


# ── Upload & analyze ──


@router.post("/receipts/upload", response_model=AnalyzeResponse)
def upload_and_analyze(file: UploadFile = File(...)):
    """Upload a receipt file and run LLM extraction. Blocking (runs in threadpool)."""
    allowed = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".pdf"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = UPLOAD_DIR / file.filename
    save_path.write_bytes(file.file.read())

    result = mgr.analyze(str(save_path))

    if result.get("error"):
        return AnalyzeResponse(error=result["error"])
    return AnalyzeResponse(
        staging_id=result.get("staging_id"),
        original_size_bytes=result.get("original_size_bytes", 0),
        sent_size_bytes=result.get("sent_size_bytes", 0),
    )


# ── Staging CRUD ──


def _staged_to_response(staged: dict) -> StagedReceiptResponse:
    return StagedReceiptResponse(
        staging_id=staged["staging_id"],
        image_url=path_to_image_url(staged.get("image_path")),
        extracted_data=staged["extracted_data"],
        staged_at=staged.get("staged_at", ""),
    )


@router.get("/receipts/staged", response_model=list[StagedReceiptResponse])
async def list_staged():
    pending = mgr.get_pending()
    return [_staged_to_response(s) for s in pending]


@router.get("/receipts/staged/{staging_id}", response_model=StagedReceiptResponse)
async def get_staged(staging_id: str):
    staged = mgr.get_staged(staging_id)
    if not staged:
        raise HTTPException(status_code=404, detail="Staged receipt not found")
    return _staged_to_response(staged)


@router.put("/receipts/staged/{staging_id}")
async def update_staged(staging_id: str, data: ReceiptEditData):
    staged = mgr.get_staged(staging_id)
    if not staged:
        raise HTTPException(status_code=404, detail="Staged receipt not found")
    mgr.update_staged(staging_id, data.model_dump())
    return {"ok": True}


@router.post("/receipts/staged/{staging_id}/approve")
def approve_staged(staging_id: str, data: ReceiptEditData):
    staged = mgr.get_staged(staging_id)
    if not staged:
        raise HTTPException(status_code=404, detail="Staged receipt not found")
    mgr.update_staged(staging_id, data.model_dump())
    receipt_id = mgr.approve(staging_id)
    return {"receipt_id": receipt_id}


@router.post("/receipts/staged/{staging_id}/reject")
async def reject_staged(staging_id: str):
    mgr.reject(staging_id)
    return {"ok": True}


@router.post("/receipts/staged/{staging_id}/reanalyze", response_model=AnalyzeResponse)
def reanalyze_staged(staging_id: str):
    """Re-run LLM extraction on a staged receipt. Blocking (runs in threadpool)."""
    result = mgr.reanalyze(staging_id)
    if result.get("error"):
        return AnalyzeResponse(error=result["error"])
    return AnalyzeResponse(
        staging_id=result.get("staging_id"),
        original_size_bytes=result.get("original_size_bytes", 0),
        sent_size_bytes=result.get("sent_size_bytes", 0),
    )


# ── Duplicate check ──


def _receipt_record_to_response(r) -> ReceiptResponse:
    return ReceiptResponse(
        id=r.id,
        merchant_name=r.merchant_name,
        merchant_address=r.merchant_address,
        date=str(r.date) if r.date else None,
        items=[item.model_dump() for item in (r.items or [])],
        subtotal=r.subtotal,
        tax=r.tax,
        tip=r.tip,
        total=r.total,
        payment_method=r.payment_method,
        category=r.category,
        currency=r.currency,
        image_url=path_to_image_url(r.file_path),
        created_at=r.created_at,
    )


@router.post("/receipts/check-duplicate", response_model=DuplicateCheckResponse)
async def check_duplicate(data: ReceiptEditData):
    dup = mgr.check_duplicate(data.model_dump())
    if dup:
        return DuplicateCheckResponse(
            is_duplicate=True,
            existing_receipt=_receipt_record_to_response(dup),
        )
    return DuplicateCheckResponse(is_duplicate=False)
