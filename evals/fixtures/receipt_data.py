"""Predefined ExtractionResult fixtures covering all receipt variants.

Import these in tests to set up mock LLM responses or as expected values.
"""
import datetime

from agents.receipt_analyzer.schemas import ExtractionResult, LineItem

# ── Valid receipts ────────────────────────────────────────────────────────────

GROCERY_RECEIPT = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Whole Foods Market",
    merchant_address="123 Main St, San Francisco CA",
    date=datetime.date(2026, 3, 15),
    items=[
        LineItem(description="Organic Milk", quantity=1, unit_price=4.99, total=4.99),
        LineItem(description="Sourdough Bread", quantity=1, unit_price=6.49, total=6.49),
        LineItem(description="Free Range Eggs", quantity=1, unit_price=5.99, total=5.99),
    ],
    subtotal=17.47,
    tax=1.40,
    tip=None,
    total=18.87,
    payment_method="VISA ending 4242",
    category="groceries",
    currency="USD",
)

RESTAURANT_RECEIPT = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="The Italian Place",
    merchant_address="456 Market St, San Francisco CA",
    date=datetime.date(2026, 3, 10),
    items=[
        LineItem(description="Pasta Carbonara", quantity=1, unit_price=18.00, total=18.00),
        LineItem(description="House Wine", quantity=2, unit_price=9.00, total=18.00),
    ],
    subtotal=36.00,
    tax=2.97,
    tip=7.00,
    total=45.97,
    payment_method="Apple Pay",
    category="restaurant",
    currency="USD",
)

ELECTRONICS_RECEIPT = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Best Buy",
    merchant_address="789 Tech Blvd, San Jose CA",
    date=datetime.date(2026, 2, 20),
    items=[
        LineItem(description="USB-C Hub 7-in-1", quantity=1, unit_price=49.99, total=49.99),
    ],
    subtotal=49.99,
    tax=4.50,
    tip=None,
    total=54.49,
    payment_method="Mastercard",
    category="electronics",
    currency="USD",
)

TRADE_IN_RECEIPT = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Best Buy",
    merchant_address="789 Tech Blvd, San Jose CA",
    date=datetime.date(2026, 2, 22),
    items=[
        LineItem(description="MacBook Air M3", quantity=1, unit_price=1299.00, total=1299.00),
        LineItem(description="Trade-in credit (iPhone 13)", quantity=1, unit_price=-350.00, total=-350.00),
    ],
    subtotal=949.00,
    tax=76.00,
    tip=None,
    total=1025.00,
    payment_method="VISA",
    category="electronics",
    currency="USD",
)

DISCOUNT_RECEIPT = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Target",
    merchant_address="321 Retail Dr, Palo Alto CA",
    date=datetime.date(2026, 3, 1),
    items=[
        LineItem(description="Laundry Detergent", quantity=1, unit_price=12.99, total=12.99),
        LineItem(description="Paper Towels", quantity=1, unit_price=8.99, total=8.99),
        LineItem(description="Coupon discount", quantity=1, unit_price=-3.00, total=-3.00),
    ],
    subtotal=18.98,
    tax=1.52,
    tip=None,
    total=20.50,
    payment_method="Target RedCard",
    category="shopping",
    currency="USD",
)

PET_CARE_RECEIPT = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Pawsome Grooming Studio",
    merchant_address="55 Bark Ave, Oakland CA",
    date=datetime.date(2026, 3, 5),
    items=[
        LineItem(description="Full groom - medium dog", quantity=1, unit_price=75.00, total=75.00),
    ],
    subtotal=75.00,
    tax=0.00,
    tip=15.00,
    total=90.00,
    payment_method="Venmo",
    category="pet-care",  # new/custom category not in defaults
    currency="USD",
)

RECEIPT_NO_DATE = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Quick Eats Diner",
    merchant_address=None,
    date=None,  # date not visible on receipt
    items=[
        LineItem(description="Burger Combo", quantity=1, unit_price=12.50, total=12.50),
    ],
    subtotal=12.50,
    tax=1.00,
    tip=2.50,
    total=16.00,
    payment_method="Cash",
    category="restaurant",
    currency="USD",
)

RECEIPT_FOREIGN_CURRENCY = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Tesco Express",
    merchant_address="10 Oxford St, London UK",
    date=datetime.date(2026, 1, 15),
    items=[
        LineItem(description="Meal Deal", quantity=1, unit_price=3.99, total=3.99),
    ],
    subtotal=3.99,
    tax=0.00,
    tip=None,
    total=3.99,
    payment_method="Contactless",
    category="groceries",
    currency="GBP",
)

# ── Validation testing fixtures ───────────────────────────────────────────────

GROCERY_BAD_MATH = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Whole Foods Market",
    merchant_address="123 Main St, San Francisco CA",
    date=datetime.date(2026, 3, 15),
    items=[
        LineItem(description="Organic Milk", quantity=1, unit_price=4.99, total=4.99),
        LineItem(description="Sourdough Bread", quantity=1, unit_price=6.49, total=6.49),
    ],
    subtotal=11.48,
    tax=1.40,
    tip=None,
    total=99.99,  # wrong total — should be 12.88
    payment_method="VISA",
    category="groceries",
    currency="USD",
)

GROCERY_CORRECTED = ExtractionResult(
    is_valid_receipt=True,
    merchant_name="Whole Foods Market",
    merchant_address="123 Main St, San Francisco CA",
    date=datetime.date(2026, 3, 15),
    items=[
        LineItem(description="Organic Milk", quantity=1, unit_price=4.99, total=4.99),
        LineItem(description="Sourdough Bread", quantity=1, unit_price=6.49, total=6.49),
    ],
    subtotal=11.48,
    tax=1.40,
    tip=None,
    total=12.88,  # corrected by validation LLM
    payment_method="VISA",
    category="groceries",
    currency="USD",
)

# ── Invalid receipt ───────────────────────────────────────────────────────────

NOT_A_RECEIPT = ExtractionResult(
    is_valid_receipt=False,
    merchant_name=None,
    merchant_address=None,
    date=None,
    items=None,
    subtotal=None,
    tax=None,
    tip=None,
    total=None,
    payment_method=None,
    category=None,
    currency="USD",
)
