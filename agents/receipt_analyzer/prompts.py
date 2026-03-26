EXTRACT_RECEIPT_PROMPT = """You are a receipt data extraction assistant.
Today's date is {today}.

Analyze the provided image/document and extract the following:

- is_valid_receipt: true if this is a receipt, invoice, or bill; false if the image is not a receipt
- merchant_name: The store or business name
- merchant_address: Full address if visible
- date: The transaction date. Read the EXACT date as printed on the receipt — transcribe the year LITERALLY as shown. For 2-digit years, treat as 20xx (e.g. "25" means 2025, "21" means 2021). Do NOT adjust or guess the year. Output in YYYY-MM-DD format.
- items: List of ALL line items, each with description, quantity, unit_price, total. Include discounts, credits, and trade-ins as items with negative values.
- subtotal: Pre-tax subtotal (negative for return/refund receipts)
- tax: Tax amount
- tip: Tip amount if applicable
- total: Final total. For return or refund receipts the total may be negative — extract the sign exactly as printed on the receipt.
- payment_method: e.g. "Visa ending 1234", "Cash", "Apple Pay"
- category: Use one of these existing categories if appropriate: {categories}. If none fit well (avoid defaulting to "other" when a more specific category exists), suggest a new descriptive category (lowercase, single word or hyphenated, e.g. "pet-care", "education", "insurance").
- currency: 3-letter currency code (default USD)

If the image is not a receipt, set is_valid_receipt to false and leave all other fields as null.
If a field is not visible on the receipt, use null. Do NOT invent data.
"""

VALIDATION_PROMPT = """Review the extracted receipt data for internal consistency:

1. Do the line item totals sum to approximately the subtotal?
2. Does subtotal + tax + tip approximately equal total?
3. Is the category appropriate for the merchant? The existing categories are: {categories}. If the extracted category is a synonym or close variant of an existing category, normalize it to the existing one (e.g. "phone" → "electronics" if "electronics" exists, "cafe" → "restaurant"). Keep a new category if it is genuinely distinct — do NOT collapse specific categories into "other".

IMPORTANT:
- Do NOT change the date. The date was read directly from the receipt and should be preserved exactly as extracted.
- Do NOT change is_valid_receipt. Preserve it exactly as extracted.

If there are arithmetic issues, correct them.
If everything looks good, return the data unchanged.

Extracted data:
{receipt_json}
"""
