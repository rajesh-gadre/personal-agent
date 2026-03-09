from agents.receipt_analyzer.graph import ReceiptState, build_receipt_graph
from agents.receipt_analyzer.staging import get_staged
from agents.receipt_analyzer.storage import init_receipt_tables
from shared.graph.base_agent import BaseAgent


class ReceiptAnalyzerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Receipt Analyzer"

    def build_graph(self):
        return build_receipt_graph()

    def init_storage(self):
        init_receipt_tables()

    def process_receipt(self, file_path: str) -> dict:
        """Run the LLM extraction pipeline. Returns staging result."""
        self.init_storage()
        graph = self.build_graph()
        initial_state: ReceiptState = {
            "file_path": file_path,
            "file_type": "",
            "original_size_bytes": 0,
            "sent_size_bytes": 0,
            "raw_extraction": {},
            "validated_data": {},
            "staging_id": None,
            "error": None,
        }
        return graph.invoke(initial_state)

    def reanalyze(self, staging_id: str) -> dict:
        """Re-run LLM extraction on a staged receipt's image."""
        staged = get_staged(staging_id)
        if not staged:
            return {"error": f"Staging ID not found: {staging_id}"}
        image_path = staged["image_path"]
        result = self.process_receipt(image_path)
        if result.get("error"):
            return result
        # Remove the old sidecar (new one was created by process_receipt)
        from pathlib import Path
        old_sidecar = Path(staged["image_path"]).parent / f"{staging_id}.json"
        old_sidecar.unlink(missing_ok=True)
        # Also remove the old image copy since staging created a new one
        old_image = Path(staged["image_path"])
        if old_image.exists() and str(old_image) != result.get("file_path", ""):
            old_image.unlink(missing_ok=True)
        return result
