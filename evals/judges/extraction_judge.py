"""LLM-as-judge for evaluating receipt extraction quality."""
import base64
import json
from pathlib import Path

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from evals.judges.prompts import (
    EXTRACTION_JUDGE_PROMPT,
    EXTRACTION_JUDGE_WITH_GROUND_TRUTH_PROMPT,
    EXTRACTION_JUDGE_WITH_IMAGE_PROMPT,
)
from shared.llm.factory import get_llm


class CriterionResult(BaseModel):
    criterion: str
    passed: bool
    reason: str


class JudgeVerdict(BaseModel):
    criteria: list[CriterionResult]
    overall_score: int  # 1-10
    summary: str
    passed: bool  # True if overall_score >= 7


class ExtractionJudge:
    """Uses a separate LLM call to evaluate receipt extraction quality.

    Two modes:
    - evaluate(extraction)                          → prompt-only (arithmetic + structure)
    - evaluate_with_ground_truth(extraction, truth) → compare against known expected values
    - evaluate_with_image(extraction, image_path)   → vision: judge sees receipt image
    """

    def __init__(self):
        self._llm = get_llm().with_structured_output(JudgeVerdict)

    def evaluate(self, extraction: dict) -> JudgeVerdict:
        """Evaluate extraction quality using prompt-only (no image, no ground truth)."""
        prompt = EXTRACTION_JUDGE_PROMPT.format(
            extraction_json=json.dumps(extraction, indent=2, default=str)
        )
        return self._llm.invoke([HumanMessage(content=prompt)])

    def evaluate_with_ground_truth(
        self, extraction: dict, ground_truth: dict
    ) -> JudgeVerdict:
        """Compare extraction against known expected values."""
        prompt = EXTRACTION_JUDGE_WITH_GROUND_TRUTH_PROMPT.format(
            extraction_json=json.dumps(extraction, indent=2, default=str),
            ground_truth_json=json.dumps(ground_truth, indent=2, default=str),
        )
        return self._llm.invoke([HumanMessage(content=prompt)])

    def evaluate_with_image(self, extraction: dict, image_path: str | Path) -> JudgeVerdict:
        """Evaluate extraction against the source receipt image (vision mode)."""
        image_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(image_bytes).decode()
        suffix = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")

        prompt = EXTRACTION_JUDGE_WITH_IMAGE_PROMPT.format(
            extraction_json=json.dumps(extraction, indent=2, default=str)
        )
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]
        )
        return self._llm.invoke([message])
