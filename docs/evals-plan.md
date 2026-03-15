# Receipt Analyzer Evals Framework — Plan

## Context

The project has zero tests. We need a comprehensive evaluation framework ("Evals") covering:
- Receipt variants: different categories, valid/invalid, +ve and -ve expenses (discounts/trade-ins)
- Verify the analyze + validate LLM pipeline produces expected results
- Use a separate test DB (not production)
- Unified framework for pipeline, API, and watcher testing
- LLM-as-judge for automated quality evaluation of extraction results

## Directory Structure

```
evals/
    conftest.py                      # Root fixtures: temp DB/folders, mock LLM, API client
    fixtures/
        __init__.py
        receipt_data.py              # Predefined ExtractionResult objects for every variant
        sample_images/               # Small synthetic images for mock-mode evals
            grocery_receipt.png
            restaurant_receipt.jpg
            invalid_not_receipt.png
            text_receipt.pdf
        live_receipts/               # Real receipt images (gitignored) for live evals
            .gitkeep
    unit/
        __init__.py
        test_schemas.py              # Pydantic model validation
        test_detect_file_type.py     # detect_file_type node
        test_storage.py              # DB CRUD round-trips
        test_staging_helpers.py      # stage/approve/reject file operations
        test_duplicate_check.py      # Fuzzy matching logic
    integration/
        __init__.py
        test_pipeline_mock.py        # Full LangGraph pipeline with mocked LLM
        test_staging_workflow.py     # analyze -> approve -> query DB; analyze -> reject
        test_manager.py              # ReceiptManager facade
    e2e/
        __init__.py
        test_api_upload.py           # FastAPI TestClient: upload -> staged -> approve -> query
        test_api_expenses.py         # Query, summary, delete endpoints
        test_api_staging.py          # List/get/update/reject staged receipts
        test_watcher_e2e.py          # Drop file in watch folder -> verify staged
    live/
        __init__.py
        conftest.py                  # Skip if no API key; load real images
        test_llm_extraction.py       # Real LLM extraction on real receipts
        test_llm_validation.py       # Real LLM validation (arithmetic correction, category normalization)
    judges/
        __init__.py
        extraction_judge.py          # LLM-as-judge: evaluate extraction quality
        prompts.py                   # Judge prompt templates
```

## Test Isolation

Every eval gets a fresh temp DB + temp folders via an `autouse` fixture:

```python
@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "receipt_staging_folder", tmp_path / "staging")
    monkeypatch.setattr(settings, "receipt_archive_folder", tmp_path / "archive")
    monkeypatch.setattr(settings, "receipt_rejected_folder", tmp_path / "rejected")
    monkeypatch.setattr(settings, "receipt_watch_folder", tmp_path / "watch")
    # Create dirs + init DB tables
    ...
    yield
```

Key files: `shared/config/settings.py` (all paths configurable), `shared/storage/database.py` (`get_connection()` reads `settings.sqlite_db_path` on every call).

## LLM Mocking Strategy

Mock `get_llm()` at the call site: patch `agents.receipt_analyzer.graph.get_llm` (not the factory module — Python binding rule: patch where the name is used).

`MockLLMController` supports sequential responses for the two-call pipeline:
- Call 1 (extract_receipt): returns `ExtractionResult` from mock
- Call 2 (validate_receipt): returns corrected `ExtractionResult` from mock
- For invalid receipts: only 1 call (validation skipped), controller tracks `call_count`

## LLM-as-Judge

### Why

Hard-coded assertions are brittle for LLM outputs. A judge LLM can evaluate extraction quality semantically:
- "Is the merchant name reasonable for this receipt image?"
- "Are the line items consistent with what's visible in the image?"
- "Is the total mathematically consistent with subtotal + tax + tip?"

### Where it fits

Used in the **live** eval tier (real LLM extraction on real images). The judge evaluates the extraction output against the source image or known ground truth.

### Judge Architecture (`evals/judges/extraction_judge.py`)

```python
class ExtractionJudge:
    """Uses a separate LLM to evaluate extraction quality."""

    def __init__(self):
        self.llm = get_llm()  # Can use a different/cheaper model

    def evaluate(self, extraction: dict, ground_truth: dict | None = None) -> JudgeVerdict:
        """Evaluate extraction quality. Returns pass/fail + reasoning."""
        ...

    def evaluate_with_image(self, extraction: dict, image_path: str) -> JudgeVerdict:
        """Evaluate extraction against the source image (vision)."""
        ...
```

### Judge Evaluation Criteria

| Criterion | What it checks | Scoring |
|-----------|---------------|---------|
| **Validity** | `is_valid_receipt` correct? (receipt vs non-receipt) | pass/fail |
| **Merchant** | Merchant name present and reasonable | pass/fail |
| **Arithmetic** | subtotal + tax + tip ~ total; item totals ~ subtotal | pass/fail with tolerance |
| **Completeness** | All visible fields extracted (date, payment, items) | 0-5 score |
| **Category** | Category appropriate for merchant/items | pass/fail |
| **Item accuracy** | Line items match what's on receipt | 0-5 score |

### Judge Response Schema

```python
class CriterionResult(BaseModel):
    criterion: str
    passed: bool
    reason: str

class JudgeVerdict(BaseModel):
    criteria: list[CriterionResult]
    overall_score: int  # 1-10
    summary: str
    passed: bool  # overall_score >= 7
```

### Two Judge Modes

1. **With ground truth** — compare extraction against known expected values (partial match OK). Used when we have labeled test receipts.
2. **With image (vision)** — judge sees the original receipt image + extraction, evaluates if extraction matches the image. No ground truth needed. More flexible but costs an extra LLM call.

## Receipt Test Fixtures (`evals/fixtures/receipt_data.py`)

Predefined `ExtractionResult` objects covering all variants:

| Fixture | Category | Key characteristics |
|---------|----------|-------------------|
| `GROCERY_RECEIPT` | groceries | Multiple items, tax, no tip |
| `RESTAURANT_RECEIPT` | restaurant | Items + tip, Apple Pay |
| `ELECTRONICS_RECEIPT` | electronics | Single item |
| `TRADE_IN_RECEIPT` | electronics | Negative line item (-$350 trade-in credit) |
| `DISCOUNT_RECEIPT` | shopping | Negative line item (-$3 coupon) |
| `PET_CARE_RECEIPT` | pet-care | New/custom category |
| `NOT_A_RECEIPT` | — | `is_valid_receipt=False`, all fields null |
| `RECEIPT_NO_DATE` | restaurant | Missing date |
| `RECEIPT_FOREIGN_CURRENCY` | groceries | GBP currency |
| `GROCERY_BAD_MATH` | groceries | Wrong total (extraction error for validation testing) |
| `GROCERY_CORRECTED` | groceries | Corrected total (validation output) |

## Eval Tiers

### Tier 1: Unit (fast, no LLM, no graph)
- Schema validation, file type detection, DB CRUD, staging file ops, duplicate matching
- Marker: `@pytest.mark.unit`

### Tier 2: Integration (mocked LLM, real graph + DB)
- Full pipeline with mock: valid receipt -> 2 LLM calls; invalid -> 1 call; error handling
- Staging workflow: analyze -> approve -> query; analyze -> reject
- Marker: `@pytest.mark.integration`

### Tier 3: E2E (mocked LLM, FastAPI TestClient)
- Full API round-trips: upload -> staged -> approve -> query -> delete
- Watcher: drop file -> staged receipt appears
- Marker: `@pytest.mark.e2e`

### Tier 4: Live + Judge (real LLM calls, LLM-as-judge)
- Real extraction on real receipt images
- Judge evaluates quality automatically
- Skipped in CI (requires API key, costs money)
- Marker: `@pytest.mark.live`

## How to Run

```bash
# All evals except live (default)
pytest

# By tier
pytest -m unit
pytest -m integration
pytest -m e2e

# Live evals with judge (manual, needs ANTHROPIC_API_KEY)
pytest -m live --timeout=120

# Specific variant
pytest -k "trade_in" -v

# Everything
pytest -m ""
```

## pyproject.toml Changes

```toml
[tool.pytest.ini_options]
testpaths = ["evals"]
markers = [
    "unit: Fast unit tests (no LLM, no API)",
    "integration: Integration tests with mocked LLM",
    "e2e: End-to-end API tests with mocked LLM",
    "live: Live LLM tests with judge (requires API key, slow)",
    "watcher: File watcher tests",
]
addopts = "-m 'not live' -v"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-timeout>=2.3",
    "httpx>=0.27",
    "ruff>=0.8.0",
]
```

## Implementation Steps

### Step 1: Scaffold
- Create `evals/` directory structure
- `conftest.py` with `isolated_environment`, `mock_llm`, `sample_image`, `api_client` fixtures
- `fixtures/receipt_data.py` with all variant ExtractionResult objects
- Create synthetic sample images (minimal PNGs via Pillow)
- Update `pyproject.toml` with pytest config + deps

### Step 2: Unit evals
- `test_schemas.py`, `test_detect_file_type.py`, `test_storage.py`
- `test_staging_helpers.py`, `test_duplicate_check.py`

### Step 3: Integration evals
- `test_pipeline_mock.py` — pipeline with mocked LLM (valid/invalid/error/negative amounts)
- `test_staging_workflow.py` — full approve/reject flows
- `test_manager.py` — ReceiptManager methods

### Step 4: E2E / API evals
- `test_api_upload.py`, `test_api_staging.py`, `test_api_expenses.py`
- `test_watcher_e2e.py`

### Step 5: Judge + Live evals
- `judges/extraction_judge.py` — judge class with `evaluate()` and `evaluate_with_image()`
- `judges/prompts.py` — judge prompt templates
- `live/test_llm_extraction.py` — real extraction + judge evaluation
- `live/test_llm_validation.py` — validation correction checks

## Existing Code to Reuse (no changes needed)

| File | What |
|------|------|
| `agents/receipt_analyzer/graph.py` | Pipeline to test (mock `get_llm` at line 23) |
| `agents/receipt_analyzer/schemas.py` | ExtractionResult, LineItem — fixture shapes |
| `agents/receipt_analyzer/manager.py` | ReceiptManager — integration test target |
| `agents/receipt_analyzer/staging.py` | Staging ops — unit test target |
| `agents/receipt_analyzer/storage.py` | DB ops — unit test target |
| `shared/config/settings.py` | Settings singleton to monkeypatch |
| `shared/llm/factory.py` | `get_llm()` — mock injection point |
| `api/main.py` | FastAPI app — TestClient target |
