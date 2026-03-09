# Personal Agent — Developer & Feature Guide

## Overview

A multi-agent personal assistant built with LangGraph, starting with a **Receipt Analyzer** agent. The system uses a monorepo structure with shared infrastructure (`shared/`) and individual agents (`agents/`), orchestrated through a Streamlit web UI.

---

## Architecture

```
personal-agent/
├── shared/                     # Shared infrastructure
│   ├── config/settings.py      # Centralized settings (Pydantic)
│   ├── llm/factory.py          # LLM provider factory
│   ├── storage/database.py     # SQLite connection manager
│   └── graph/base_agent.py     # Abstract base agent
├── agents/
│   └── receipt_analyzer/       # Receipt processing agent
│       ├── agent.py            # Agent class (orchestration)
│       ├── graph.py            # LangGraph pipeline (4 nodes)
│       ├── prompts.py          # LLM prompts (extraction + validation)
│       ├── schemas.py          # Pydantic data models
│       ├── staging.py          # Staging workflow + dedup
│       ├── storage.py          # SQLite CRUD
│       └── watcher.py          # Background folder watcher
├── ui/
│   └── app.py                  # Streamlit web UI
├── data/                       # Runtime data (not in git)
│   ├── personal_agent.db       # SQLite database
│   ├── uploads/                # Direct UI uploads
│   ├── staging/                # Pending review (image + JSON sidecar)
│   ├── archive/                # Approved receipt images
│   └── rejected/               # Rejected receipt images
└── pyproject.toml              # Dependencies & project config
```

---

## Receipt Processing Workflow

### High-Level Flow

```
  ~/Receipts/              data/uploads/
  (watch folder)           (UI uploads)
       │                        │
       │ watcher detects        │ user clicks "Analyze"
       │ (event-based)          │ (file stays in uploads/)
       ▼                        ▼
  ┌─────────────────────────────────────┐
  │  LangGraph Pipeline (4 nodes)       │
  │  detect → extract → validate →      │──► data/staging/
  │                            stage    │    (image COPY + JSON sidecar)
  └─────────────────────────────────────┘        |
       │                                         │
       │ watcher DELETES                         │
       │ ~/Receipts original              UI: Review & Edit
       │                                  (editable fields)
       ▼                                         │
  original gone,                       ┌─────────┴─────────┐
  copy safe in staging/             Approve              Reject
                                       │                   │
                                       ▼                   ▼
                                 1. Validate          data/rejected/
                                 2. Save to DB        (image + JSON)
                                 3. Move → archive/
                                 4. Delete sidecar
```

### Watcher Flow — File Location at Each Step

| Step | Action | File location |
|------|--------|---------------|
| 0 | User drops file | `~/Receipts/receipt.HEIC` |
| 1 | Watcher detects file (watchdog event), waits 2s | `~/Receipts/receipt.HEIC` |
| 2 | `detect_file_type` — checks extension | `~/Receipts/receipt.HEIC` |
| 3 | `extract_receipt` — reads file, base64, LLM call #1 | `~/Receipts/receipt.HEIC` |
| 4 | `validate_receipt` — LLM call #2 (JSON only, no image) | `~/Receipts/receipt.HEIC` |
| 5 | `stage_receipt` — **copies** image + writes JSON sidecar | `~/Receipts/receipt.HEIC` + `data/staging/{id}.HEIC` + `data/staging/{id}.json` |
| 6 | Watcher **deletes** original (pipeline succeeded) | `data/staging/{id}.HEIC` + `.json` only |
| 7a | **Approve**: validate → DB save → move image → delete JSON | `data/archive/{id}.HEIC` (DB points here) |
| 7b | **Reject**: move image + JSON to rejected/ | `data/rejected/{id}.HEIC` + `.json` |

**Key point:** The original is never lost — it's copied to staging at step 5, then moved to `archive/` or `rejected/` at step 7. To reprocess, copy from any of those locations back to `~/Receipts`.

---

## LLM Calls

The pipeline makes **two LLM calls** per receipt:

### Call 1: Extraction (`extract_receipt`)

| Detail | Value |
|--------|-------|
| **Purpose** | Extract structured data from receipt image/PDF |
| **Input** | Receipt image (base64) or PDF text + extraction prompt |
| **Output** | JSON with: merchant, address, date, items, totals, payment, category, currency |
| **Model** | Configurable (default: `claude-sonnet-4-20250514`) |
| **Prompt** | `EXTRACT_RECEIPT_PROMPT` — includes today's date for context |

Key prompt instructions:
- Date: Read EXACT date as printed; for 2-digit years treat as 20xx (e.g., "25" = 2025)
- Do NOT invent data — only extract what's visible
- Output YYYY-MM-DD format for dates

### Call 2: Validation (`validate_receipt`)

| Detail | Value |
|--------|-------|
| **Purpose** | Validate arithmetic consistency of extracted data |
| **Input** | Extracted JSON only (no image) |
| **Output** | Corrected or unchanged JSON |
| **Model** | Same as extraction |
| **Prompt** | `VALIDATION_PROMPT` |

What it checks:
- Line item totals sum to approximately subtotal
- Subtotal + tax + tip approximately equals total
- Category is appropriate for merchant

What it does NOT do:
- Does NOT change the date (explicitly preserved)
- Does NOT see the receipt image (cannot verify visual data)

**Design Decision:** The validation prompt explicitly says "Do NOT change the date" because the validator cannot see the receipt and was previously incorrectly "correcting" years based on training data bias.

---

## Image Processing

### Size Limits

Anthropic's API has a **5MB limit on base64-encoded images**. Since base64 adds ~33% overhead:

```
Max raw bytes = 5MB / 1.33 ≈ 3,750,000 bytes
```

### Resizing Algorithm

When an image exceeds `MAX_IMAGE_BYTES` (3.75MB) or is HEIC/HEIF format:

1. Load image, convert to RGB if needed
2. Progressively try smaller dimensions: `[original, 2048, 1600, 1200]`
3. At each dimension, save as JPEG with quality=90
4. Stop when under the size limit

### Supported Formats

| Format | Handling |
|--------|----------|
| JPEG, PNG, WebP, GIF | Native (resize if needed) |
| HEIC/HEIF | Convert to JPEG via `pillow-heif` |
| PDF | Text extraction via `pypdf` (no image processing) |

---

## Staging System

Receipts are **not saved directly to the database**. Instead, they go through a staging workflow using JSON sidecar files.

### Sidecar JSON Structure

Each staged receipt = image file + `.json` sidecar in `data/staging/`:

```json
{
  "staging_id": "20260214_171208_524ea50c",
  "image_path": "data/staging/20260214_171208_524ea50c.HEIC",
  "original_path": "/Users/name/Receipts/receipt.HEIC",
  "extracted_data": { ... },
  "staged_at": "2026-02-14T17:12:08.123456"
}
```

Staging ID format: `{YYYYMMDD_HHMMSS}_{8-char-uuid}`

### Approval Flow (Fail-Fast Order)

```
1. Validate    → Construct ReceiptRecord (Pydantic validation)
                 If invalid, STOP — nothing touched
2. Save to DB  → INSERT INTO receipts
                 Data is persisted — never lost after this step
3. Move image  → staging/ → archive/
                 If fails, DB has record (fixable path mismatch)
4. Delete JSON → Remove sidecar from staging/
                 Only after everything else succeeded
```

**Why this order matters:** Earlier versions moved the image before validation. If validation failed (e.g., `items=None`), the image was orphaned in archive with no DB record and no sidecar — data loss.

---

## Duplicate Detection

Two-phase matching with tolerance for LLM extraction errors:

**Phase 1 — SQL candidate selection (cheap):**

| Field | Match Criteria | Rationale |
|-------|---------------|-----------|
| Date | Within ±1 day | LLM off-by-one errors |
| Total | Within ±$0.50 | Rounding differences |

```sql
SELECT id, merchant_name FROM receipts
WHERE date BETWEEN date(?, '-1 day') AND date(?, '+1 day')
AND total BETWEEN ? AND ?      -- ±$0.50
```

**Phase 2 — Python fuzzy merchant matching:**

| Field | Match Criteria | Rationale |
|-------|---------------|-----------|
| Merchant | `SequenceMatcher` ratio ≥ 0.6 | Handles OCR/LLM typos, abbreviations, variant spellings |

Uses `difflib.SequenceMatcher` (stdlib) — no external dependency. Example: `"SHASIHATI S KALE MD"` vs `"SHASHIMATI S KALE MD"` scores 0.92, well above the 0.6 threshold.

### Dedup in the UI

- Runs on **user-edited data** (not raw LLM output) — so corrections are checked
- Triggers in real-time as user edits fields (Streamlit rerun model)
- Shows side-by-side comparison: new vs existing receipt data + images
- Duplicate approval requires confirmation via modal dialog

---

## Background Watcher

### How It Works

- **Event-based** (default): Uses `watchdog` library for instant file detection via OS-native events (FSEvents on macOS, inotify on Linux)
- **Poll fallback**: Set `RECEIPT_WATCHER_MODE=poll` for 30-second interval scanning
- On startup, scans for files already in the watch folder (catches files dropped while watcher was off)
- On success: deletes original from watch folder
- On error: logs error, leaves file for retry

### Running Modes

| Mode | How to run | When to use |
|------|-----------|-------------|
| **Standalone process** | `python -m agents.receipt_analyzer.watcher` | Recommended — runs independently of UI |
| **Console script** | `receipt-watcher` (after `pip install -e .`) | Same as above, convenience alias |
| **Embedded in Streamlit** | Set `START_WATCHER_IN_UI=true` in `.env` | Only if not running standalone |

**Important:** Run only one watcher at a time. If running standalone, set `START_WATCHER_IN_UI=false` in `.env` to disable the embedded watcher.

### Supported File Types

`.png`, `.jpg`, `.jpeg`, `.heic`, `.heif`, `.pdf`, `.webp`, `.gif`

Skips hidden files (starting with `.`).

---

## Database Schema

```sql
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_name TEXT NOT NULL,
    merchant_address TEXT,
    date TEXT,                              -- ISO format: YYYY-MM-DD
    items_json TEXT,                        -- JSON array of line items
    subtotal REAL,
    tax REAL,
    tip REAL,
    total REAL NOT NULL,
    payment_method TEXT,
    category TEXT NOT NULL DEFAULT 'other',
    currency TEXT NOT NULL DEFAULT 'USD',
    file_path TEXT NOT NULL,                -- Path to archived image
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **WAL mode** enabled for concurrent read/write (watcher + UI)
- Line items stored as JSON string in `items_json` column
- Dates stored as ISO strings (sort correctly, unambiguous)
- Displayed in US format (MM/DD/YYYY) in the UI

---

## Folder Structure & Data Flow

| Folder | Purpose | Files | Lifecycle |
|--------|---------|-------|-----------|
| `~/Receipts` | Watch folder (user input) | Receipt images/PDFs | Deleted after successful staging |
| `data/uploads/` | Direct UI uploads | Receipt images/PDFs | Persists |
| `data/staging/` | Pending review | Image + JSON sidecar pairs | Removed on approve/reject |
| `data/archive/` | Approved receipts | Receipt images | Permanent storage |
| `data/rejected/` | Rejected receipts | Image + JSON sidecar | For later review |

---

## UI (Streamlit)

### Tabs

1. **Upload Receipt** — File uploader + review form for just-uploaded receipt
2. **Pending Review (N)** — Lists all staged receipts with count badge, Refresh button
3. **Expenses** — Filterable table (date range, category, merchant) with Search button
4. **Summary** — Aggregate metrics + spending-by-category bar chart

### Review Form Features

- **Editable fields:** Merchant, Address, Date, Category, Payment, Currency, Subtotal, Tax, Tip, Total
- **Read-only:** Line items table
- **Action buttons:** Approve & Save, Reject, Re-analyze, Copy JSON
- **Re-analyze:** Re-runs LLM extraction on the same image (useful when extraction is wrong)
- **Copy JSON:** Clipboard copy via base64-encoded JavaScript (no page reload)

### Date Display

- **Storage:** ISO format `YYYY-MM-DD` (unambiguous, sorts correctly)
- **UI display:** US format `MM/DD/YYYY` via date_input format parameter

---

## Configuration

### Environment Variables (`.env`)

```bash
# Required — LLM API keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEFAULT_LLM_PROVIDER=anthropic
DEFAULT_LLM_MODEL=claude-sonnet-4-20250514

# Database
SQLITE_DB_PATH=./data/personal_agent.db

# LangSmith observability (optional)
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=personal-agent

# Receipt folders (optional — defaults shown)
RECEIPT_WATCH_FOLDER=~/Receipts
RECEIPT_STAGING_FOLDER=./data/staging
RECEIPT_ARCHIVE_FOLDER=./data/archive
RECEIPT_REJECTED_FOLDER=./data/rejected
RECEIPT_WATCH_INTERVAL_SECONDS=30
```

**Important:** `load_dotenv()` must run before any LangChain imports for LangSmith tracing to work.

**Important:** Settings uses `"extra": "ignore"` so LangSmith env vars (not in the Settings model) don't cause validation errors.

---

## LLM Provider Configuration

The system supports both Anthropic and OpenAI via a factory pattern:

```python
from shared.llm.factory import get_llm

llm = get_llm()                          # Uses defaults from settings
llm = get_llm(provider="openai")         # Override provider
llm = get_llm(model="gpt-4o")           # Override model
llm = get_llm(temperature=0.5)          # Pass kwargs to underlying model
```

---

## Running the Application

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
streamlit run ui/app.py
```

The app will:
1. Initialize the SQLite database
2. Start the background watcher thread
3. Open the web UI at `http://localhost:8501`

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON sidecar files (not DB) for staging | Simpler, editable before commit, no schema migration |
| Validation doesn't modify dates | Validator can't see the receipt image; was incorrectly adjusting years |
| DB save before file move in approval | Prioritizes data integrity over file housekeeping |
| Base64 size limit at 3.75MB (not 5MB) | Accounts for 33% base64 encoding overhead |
| Fuzzy dedup (not exact match) | Handles LLM extraction variance across runs |
| ISO dates in storage, US dates in UI | Unambiguous sorting + user-friendly display |
| `load_dotenv()` before LangChain imports | Required for LangSmith env var detection |
| Streamlit for UI (for now) | Quick to build; may switch to NiceGUI or FastAPI+HTMX later |
| Linear pipeline (not ReAct) | Sufficient for current use case; ReAct planned when tools are added |

---

## Future Improvements

| # | Item | Status | Priority |
|---|------|--------|----------|
| 1 | Improved Duplicate Detection | Done (fuzzy merchant matching via SequenceMatcher) | High |
| 2 | UI Framework Migration | Pending | Medium |
| 3 | ReAct Agent Pattern with DeepAgents | Pending | Medium |
| 4 | Standalone Watcher as System Service | Partial (standalone done, service pending) | Low |
| 5 | Audit & Recovery Utility | Pending | Low |
| 6 | Multi-Row Delete in Expenses | Pending | Low |

### 1. Improved Duplicate Detection — DONE

**Implemented:** Two-phase fuzzy matching — SQL narrows by date ±1 day and total ±$0.50, then Python `difflib.SequenceMatcher` compares merchant names with 0.6 similarity threshold. Handles OCR/LLM typos, abbreviations, and variant spellings.

**Remaining sub-item:** Also check staged receipts (not just the DB). Currently, if two copies of the same receipt are staged but neither is approved, no duplicate warning is shown.

### 2. UI Framework Migration

**Current state:** Streamlit. Quick to build and iterate, but has inherent limitations:
- Full page rerun on every interaction (no partial updates)
- Tab state not preserved reliably across reruns
- No true modal/popup without rerun
- Background updates (e.g., watcher results) require manual refresh

**Candidates for migration:**
- **NiceGUI** — Python-native, event-driven, real-time updates via WebSocket, similar simplicity to Streamlit
- **FastAPI + HTMX** — Lightweight, server-rendered, partial page updates without full reloads
- **FastAPI + React/Next.js** — Full SPA, most flexible but highest complexity

**Migration impact:** The agent/storage layer has zero UI dependencies. Migration means rewriting `ui/app.py` only. All business logic (`agent.py`, `staging.py`, `storage.py`, `graph.py`) is portable as-is.

### 3. ReAct Agent Pattern with DeepAgents

**Current state:** Linear 4-node LangGraph pipeline (detect → extract → validate → stage). Sufficient for the current single-task workflow.

**When to evolve:** When the receipt agent needs to make decisions or use external tools:
- Merchant lookup API (enrich merchant data, normalize names)
- Currency conversion API (for international receipts)
- Category classification using purchase history
- Multi-receipt batch processing with decision logic

**Approach:** Refactor to a ReAct (Reason + Act) pattern using DeepAgents (already installed). The agent would reason about each receipt, decide which tools to invoke, and iterate until satisfied with the extraction quality. The linear pipeline nodes become tools the ReAct agent can call.

### 4. Standalone Watcher as System Service

**Current state:** Watcher runs as a standalone process (`python -m agents.receipt_analyzer.watcher`) or as a background thread inside Streamlit. User must manually start it.

**Future:** Package as a system service for always-on monitoring:
- **macOS:** `launchd` plist (auto-start on login)
- **Linux:** `systemd` unit file (auto-start on boot)
- **Docker:** Dedicated watcher container alongside the UI container

### 5. Audit & Recovery Utility

**Need:** When the approval flow partially fails (e.g., DB saved but image move fails), data can become inconsistent — image in wrong folder, DB path mismatch, orphaned sidecars.

**Approach:** A CLI utility that scans for inconsistencies and fixes them:
- Image in staging but receipt in DB → move image to archive, fix DB path
- Orphaned sidecar JSON with no image → clean up or flag for re-upload
- DB record pointing to non-existent image → scan all folders to locate it

### 6. Multi-Row Delete in Expenses

**Current state:** Single receipt delete via the detail popup (click row → view detail → delete).

**Future:** Allow selecting multiple rows in the Expenses table and deleting them in bulk. Useful for cleaning up test data or removing a batch of incorrectly processed receipts. Requires Streamlit's `selection_mode="multi-row"` and a bulk delete confirmation dialog.
