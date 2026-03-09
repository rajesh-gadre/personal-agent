import json

from agents.receipt_analyzer.schemas import LineItem, ReceiptRecord
from shared.storage.database import get_connection


def init_receipt_tables():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant_name TEXT NOT NULL,
                merchant_address TEXT,
                date TEXT,
                items_json TEXT,
                subtotal REAL,
                tax REAL,
                tip REAL,
                total REAL NOT NULL,
                payment_method TEXT,
                category TEXT NOT NULL DEFAULT 'other',
                currency TEXT NOT NULL DEFAULT 'USD',
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_receipt(receipt: ReceiptRecord) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO receipts
               (merchant_name, merchant_address, date, items_json,
                subtotal, tax, tip, total, payment_method, category,
                currency, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.merchant_name,
                receipt.merchant_address,
                str(receipt.date) if receipt.date else None,
                json.dumps([item.model_dump() for item in receipt.items]),
                receipt.subtotal,
                receipt.tax,
                receipt.tip,
                receipt.total,
                receipt.payment_method,
                receipt.category,
                receipt.currency,
                receipt.file_path,
            ),
        )
        return cursor.lastrowid


def get_receipt_by_id(receipt_id: int) -> ReceiptRecord | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    if not row:
        return None
    items = json.loads(row["items_json"]) if row["items_json"] else []
    return ReceiptRecord(
        id=row["id"],
        merchant_name=row["merchant_name"],
        merchant_address=row["merchant_address"],
        date=row["date"],
        items=[LineItem(**i) for i in items],
        subtotal=row["subtotal"],
        tax=row["tax"],
        tip=row["tip"],
        total=row["total"],
        payment_method=row["payment_method"],
        category=row["category"],
        currency=row["currency"],
        file_path=row["file_path"],
        created_at=row["created_at"],
    )


def delete_receipt(receipt_id: int) -> bool:
    """Delete a receipt by ID: removes DB record and archived image. Returns True if deleted."""
    from pathlib import Path

    with get_connection() as conn:
        row = conn.execute("SELECT file_path FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if not row:
            return False
        cursor = conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        if cursor.rowcount > 0 and row["file_path"]:
            image_path = Path(row["file_path"])
            if image_path.exists():
                image_path.unlink()
            return True
        return False


def get_categories() -> list[str]:
    """Return all distinct categories from the DB, sorted alphabetically."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM receipts ORDER BY category"
        ).fetchall()
    return [row["category"] for row in rows]


def query_receipts(
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> list[ReceiptRecord]:
    clauses = []
    params = []
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if merchant:
        clauses.append("merchant_name LIKE ?")
        params.append(f"%{merchant}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM receipts {where} ORDER BY date DESC", params
        ).fetchall()

    results = []
    for row in rows:
        items = json.loads(row["items_json"]) if row["items_json"] else []
        results.append(
            ReceiptRecord(
                id=row["id"],
                merchant_name=row["merchant_name"],
                merchant_address=row["merchant_address"],
                date=row["date"],
                items=[LineItem(**i) for i in items],
                subtotal=row["subtotal"],
                tax=row["tax"],
                tip=row["tip"],
                total=row["total"],
                payment_method=row["payment_method"],
                category=row["category"],
                currency=row["currency"],
                file_path=row["file_path"],
                created_at=row["created_at"],
            )
        )
    return results


def get_summary_stats(
    start_date: str | None = None, end_date: str | None = None
) -> dict:
    """Return aggregate stats: total spent, by category, total tax."""
    receipts = query_receipts(start_date=start_date, end_date=end_date)
    by_category: dict[str, float] = {}
    total_spent = 0.0
    total_tax = 0.0
    for r in receipts:
        total_spent += r.total
        total_tax += r.tax or 0.0
        cat = r.category
        by_category[cat] = by_category.get(cat, 0.0) + r.total
    return {
        "total_spent": total_spent,
        "total_tax": total_tax,
        "by_category": by_category,
        "receipt_count": len(receipts),
    }
