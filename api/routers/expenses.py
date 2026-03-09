from fastapi import APIRouter, HTTPException

from api import mgr
from api.image import path_to_image_url
from api.models import ReceiptResponse, SummaryResponse
from agents.receipt_analyzer.schemas import DEFAULT_CATEGORIES
from agents.receipt_analyzer.storage import get_categories

router = APIRouter(tags=["expenses"])


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


@router.get("/expenses", response_model=list[ReceiptResponse])
async def query_expenses(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
):
    receipts = mgr.query(
        start_date=start_date,
        end_date=end_date,
        category=category,
        merchant=merchant,
    )
    return [_receipt_record_to_response(r) for r in receipts]


@router.get("/expenses/summary", response_model=SummaryResponse)
async def get_summary(start_date: str | None = None, end_date: str | None = None):
    stats = mgr.get_summary(start_date=start_date, end_date=end_date)
    return SummaryResponse(**stats)


@router.get("/expenses/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(receipt_id: int):
    from agents.receipt_analyzer.storage import get_receipt_by_id

    r = get_receipt_by_id(receipt_id)
    if not r:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return _receipt_record_to_response(r)


@router.delete("/expenses/{receipt_id}")
async def delete_receipt(receipt_id: int):
    deleted = mgr.delete(receipt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"ok": True}


@router.get("/categories", response_model=list[str])
async def list_categories():
    db_cats = get_categories()
    return sorted(set(DEFAULT_CATEGORIES + db_cats))
