import base64
import io
import json
from datetime import date
from pathlib import Path
from typing import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()  # Enables Image.open() to handle HEIC/HEIF files

# Anthropic's 5MB limit is on the base64-encoded string.
# base64 adds ~33% overhead, so raw bytes must be under ~3.75MB.
MAX_IMAGE_BYTES = 3_750_000

from agents.receipt_analyzer.prompts import EXTRACT_RECEIPT_PROMPT, VALIDATION_PROMPT
from agents.receipt_analyzer.schemas import DEFAULT_CATEGORIES, ExtractionResult
from agents.receipt_analyzer.staging import stage_receipt
from agents.receipt_analyzer.storage import get_categories
from shared.llm.factory import get_llm


class ReceiptState(TypedDict):
    file_path: str
    file_type: str
    original_size_bytes: int
    sent_size_bytes: int
    raw_extraction: dict
    validated_data: dict
    staging_id: str | None
    error: str | None


def _get_category_list() -> str:
    """Get merged category list (DB + defaults) as a comma-separated string."""
    db_categories = get_categories()
    all_categories = sorted(set(DEFAULT_CATEGORIES + db_categories))
    return ", ".join(all_categories)


def detect_file_type(state: ReceiptState) -> dict:
    """Determine if the file is an image or PDF."""
    path = Path(state["file_path"])
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return {"file_type": "pdf"}
    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif"):
        return {"file_type": "image"}
    else:
        return {"error": f"Unsupported file type: {suffix}"}


def extract_receipt(state: ReceiptState) -> dict:
    """Use vision LLM to extract structured data from the receipt."""
    if state.get("error"):
        return {}

    file_path = Path(state["file_path"])
    structured_llm = get_llm().with_structured_output(ExtractionResult)

    if state["file_type"] == "image":
        image_bytes = file_path.read_bytes()
        original_size = len(image_bytes)
        suffix = file_path.suffix.lower()
        needs_conversion = suffix in (".heic", ".heif") or len(image_bytes) > MAX_IMAGE_BYTES
        if needs_conversion:
            img = Image.open(file_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            # Progressively shrink dimensions until under limit, preserving quality
            max_side = max(img.size)
            quality = 90
            for target in [max_side, 2048, 1600, 1200]:
                resized = img.copy()
                if target < max_side:
                    resized.thumbnail((target, target), Image.LANCZOS)
                buf = io.BytesIO()
                resized.save(buf, format="JPEG", quality=quality)
                image_bytes = buf.getvalue()
                if len(image_bytes) <= MAX_IMAGE_BYTES:
                    break
            mime = "image/jpeg"
        else:
            mime_map = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
            mime = mime_map.get(suffix, "image/jpeg")
        sent_size = len(image_bytes)
        b64 = base64.b64encode(image_bytes).decode()
        prompt = EXTRACT_RECEIPT_PROMPT.format(today=date.today().isoformat(), categories=_get_category_list())
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]
        )
    elif state["file_type"] == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            prompt = EXTRACT_RECEIPT_PROMPT.format(today=date.today().isoformat(), categories=_get_category_list())
            message = HumanMessage(
                content=f"{prompt}\n\nReceipt text:\n{text}"
            )
        else:
            return {
                "error": "PDF has no extractable text. Please upload an image instead."
            }
    else:
        return {"error": "Unknown file type"}

    extraction: ExtractionResult = structured_llm.invoke([message])
    result = {"raw_extraction": extraction.model_dump(mode="json")}
    if state["file_type"] == "image":
        result["original_size_bytes"] = original_size
        result["sent_size_bytes"] = sent_size

    return result


def _should_validate(state: ReceiptState) -> str:
    """Route: skip validation if not a valid receipt or if there's an error."""
    if state.get("error"):
        return "stage_receipt"
    if not state.get("raw_extraction", {}).get("is_valid_receipt"):
        return "stage_receipt"
    return "validate_receipt"


def validate_receipt(state: ReceiptState) -> dict:
    """Validate and correct extracted data."""
    structured_llm = get_llm().with_structured_output(ExtractionResult)
    receipt_json = json.dumps(state["raw_extraction"], indent=2)
    prompt = VALIDATION_PROMPT.format(receipt_json=receipt_json, categories=_get_category_list())
    validation: ExtractionResult = structured_llm.invoke([HumanMessage(content=prompt)])

    return {"validated_data": validation.model_dump(mode="json")}


def stage_receipt_node(state: ReceiptState) -> dict:
    """Stage validated data for review (not saved to DB yet)."""
    if state.get("error"):
        return {}

    try:
        # Use validated_data if available (validation ran), otherwise raw_extraction
        data = state["validated_data"] if state.get("validated_data") else state["raw_extraction"]

        # Early validation: if LLM says valid but required fields are missing, override
        if data.get("is_valid_receipt") and (not data.get("merchant_name") or data.get("total") is None):
            data["is_valid_receipt"] = False

        staging_id = stage_receipt(state["file_path"], data)
        return {"staging_id": staging_id}
    except Exception as e:
        return {"error": f"Failed to stage receipt: {e}"}


def build_receipt_graph():
    graph = StateGraph(ReceiptState)

    graph.add_node("detect_file_type", detect_file_type)
    graph.add_node("extract_receipt", extract_receipt)
    graph.add_node("validate_receipt", validate_receipt)
    graph.add_node("stage_receipt", stage_receipt_node)

    graph.add_edge(START, "detect_file_type")
    graph.add_edge("detect_file_type", "extract_receipt")
    graph.add_conditional_edges("extract_receipt", _should_validate)
    graph.add_edge("validate_receipt", "stage_receipt")
    graph.add_edge("stage_receipt", END)

    return graph.compile()
