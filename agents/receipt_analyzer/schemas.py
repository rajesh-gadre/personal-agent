import datetime

from pydantic import BaseModel, Field

# Default seed categories (used when DB has no approved receipts yet).
# New categories are added dynamically when receipts with new categories are approved.
DEFAULT_CATEGORIES = [
    "electronics",
    "entertainment",
    "groceries",
    "health",
    "other",
    "restaurant",
    "shopping",
    "transport",
    "utilities",
]


class LineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    total: float


class ExtractionResult(BaseModel):
    """LLM extraction output — lenient, all fields optional except is_valid_receipt."""

    is_valid_receipt: bool
    merchant_name: str | None = None
    merchant_address: str | None = None
    date: datetime.date | None = None
    items: list[LineItem] | None = None
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float | None = None
    payment_method: str | None = None
    category: str | None = Field(
        default=None,
        description="Receipt category. Use an existing category if appropriate, but suggest a specific new one (e.g. 'pet-care', 'education', 'insurance') rather than defaulting to 'other'.",
    )
    currency: str = "USD"


class ReceiptData(BaseModel):
    """Structured data extracted from a receipt."""

    merchant_name: str
    merchant_address: str | None = None
    date: datetime.date | None = None
    items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float
    payment_method: str | None = None
    category: str = "other"
    currency: str = "USD"


class ReceiptRecord(ReceiptData):
    """ReceiptData + DB metadata."""

    id: int | None = None
    file_path: str = ""
    created_at: str | None = None
