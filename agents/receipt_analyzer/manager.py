from agents.receipt_analyzer.agent import ReceiptAnalyzerAgent
from agents.receipt_analyzer.schemas import ReceiptRecord
from agents.receipt_analyzer.staging import (
    approve_staged,
    check_duplicate,
    get_staged,
    list_staged,
    reject_staged,
    update_staged,
)
from agents.receipt_analyzer.storage import (
    delete_receipt,
    get_summary_stats,
    init_receipt_tables,
    query_receipts,
)


class ReceiptManager:
    """Single entry point for all receipt operations.

    Orchestrates the AI agent, staging workflow, and DB storage.
    The UI should only interact with this class.
    """

    def __init__(self):
        self._agent = ReceiptAnalyzerAgent()

    def init(self):
        """Initialize storage (DB tables)."""
        init_receipt_tables()

    # ── AI operations (delegated to agent) ──

    def analyze(self, file_path: str) -> dict:
        """Run LLM extraction pipeline on a receipt. Returns staging result."""
        self.init()
        return self._agent.process_receipt(file_path)

    def reanalyze(self, staging_id: str) -> dict:
        """Re-run LLM extraction on a staged receipt's image."""
        return self._agent.reanalyze(staging_id)

    # ── Staging operations ──

    def get_pending(self) -> list[dict]:
        """List all staged receipts pending review."""
        return list_staged()

    def get_staged(self, staging_id: str) -> dict | None:
        """Get a single staged receipt by ID."""
        return get_staged(staging_id)

    def update_staged(self, staging_id: str, data: dict) -> None:
        """Update extracted data in a staged receipt (for user edits)."""
        update_staged(staging_id, data)

    def approve(self, staging_id: str) -> int:
        """Approve a staged receipt: validate, save to DB, archive image."""
        return approve_staged(staging_id)

    def reject(self, staging_id: str) -> None:
        """Reject a staged receipt: move to rejected folder."""
        reject_staged(staging_id)

    def check_duplicate(self, data: dict) -> ReceiptRecord | None:
        """Check if data matches an existing receipt (fuzzy match)."""
        return check_duplicate(data)

    # ── DB operations ──

    def query(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        category: str | None = None,
        merchant: str | None = None,
    ) -> list[ReceiptRecord]:
        """Query receipts with optional filters."""
        return query_receipts(
            start_date=start_date,
            end_date=end_date,
            category=category,
            merchant=merchant,
        )

    def get_summary(self, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Get aggregate stats for a date range."""
        return get_summary_stats(start_date=start_date, end_date=end_date)

    def delete(self, receipt_id: int) -> bool:
        """Delete a receipt from the DB."""
        return delete_receipt(receipt_id)
