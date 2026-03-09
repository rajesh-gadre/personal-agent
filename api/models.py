from pydantic import BaseModel


class ReceiptEditData(BaseModel):
    """Request body for updating/approving a staged receipt."""

    merchant_name: str
    merchant_address: str | None = None
    date: str | None = None
    items: list[dict] = []
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float
    payment_method: str | None = None
    category: str = "other"
    currency: str = "USD"


class AnalyzeResponse(BaseModel):
    staging_id: str | None = None
    error: str | None = None
    original_size_bytes: int = 0
    sent_size_bytes: int = 0


class StagedReceiptResponse(BaseModel):
    staging_id: str
    image_url: str
    extracted_data: dict
    staged_at: str


class LineItemResponse(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float


class ReceiptResponse(BaseModel):
    id: int
    merchant_name: str
    merchant_address: str | None = None
    date: str | None = None
    items: list[LineItemResponse] = []
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float
    payment_method: str | None = None
    category: str
    currency: str
    image_url: str
    created_at: str | None = None


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    existing_receipt: ReceiptResponse | None = None


class SummaryResponse(BaseModel):
    total_spent: float
    total_tax: float
    receipt_count: int
    by_category: dict[str, float]
