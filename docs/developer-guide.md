# Personal Agent — Developer & Feature Guide

## Overview

A multi-agent personal assistant built with LangGraph, starting with a **Receipt Analyzer** agent. The system uses a monorepo structure with shared infrastructure (`shared/`) and individual agents (`agents/`), with a FastAPI backend serving a vanilla HTML/JS frontend.

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
│       └── watcher.py          # Background folder watcher (dual folder)
├── api/                        # FastAPI backend
│   ├── main.py                 # App factory, middleware, error handlers
│   ├── models.py               # Pydantic request/response models
│   ├── image.py                # Image URL helper
│   └── routers/
│       ├── receipts.py         # Upload, staging, image serving endpoints
│       └── expenses.py         # Query, summary, delete endpoints
├── ui/
│   └── static/
│       ├── index.html          # Single-page app shell + CSS
│       └── app.js              # Vanilla JS (no framework, no build step)
├── data/                       # Runtime data (not in git)
│   ├── personal_agent.db       # SQLite database
│   ├── incoming/               # Landing area for UI uploads (watcher picks up)
│   ├── staging/                # Pending review (image + JSON sidecar)
│   ├── archive/                # Approved receipt images
│   └── rejected/               # Rejected receipt images
└── pyproject.toml              # Dependencies & project config
```

---

## Receipt Processing Workflow

### High-Level Flow

```
  ~/Receipts/              data/incoming/
  (drop folder)            (UI uploads land here)
       │                        │
       │ watcher detects        │ watcher detects
       │ (event-based)          │ (event-based)
       └──────────┬─────────────┘
                  ▼
  ┌─────────────────────────────────────┐
  │  LangGraph Pipeline (4 nodes)       │
  │  detect → extract → validate →      │──► data/staging/
  │                            stage    │    (image COPY + JSON sidecar)
  └─────────────────────────────────────┘        │
       │                                         │
       │ watcher DELETES                         │
       │ original file                    UI: Review & Edit
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
| 0 | User drops file or UI uploads | `~/Receipts/receipt.HEIC` or `data/incoming/receipt.HEIC` |
| 1 | Watcher detects file (watchdog event), waits 2s | same |
| 2 | `detect_file_type` — checks extension | same |
| 3 | `extract_receipt` — reads file, base64, LLM call #1 | same |
| 4 | `validate_receipt` — LLM call #2 (JSON only, no image) | same |
| 5 | `stage_receipt` — **copies** image + writes JSON sidecar | original + `data/staging/{id}.HEIC` + `data/staging/{id}.json` |
| 6 | Watcher **deletes** original (pipeline succeeded) | `data/staging/{id}.HEIC` + `.json` only |
| 7a | **Approve**: validate → DB save → move image → delete JSON | `data/archive/{id}.HEIC` (DB points here) |
| 7b | **Reject**: move image + JSON to rejected/ | `data/rejected/{id}.HEIC` + `.json` |

**Key point:** The original is never lost — it's copied to staging at step 5, then moved to `archive/` or `rejected/` at step 7.

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

### Web Image Serving

Images are served via `/api/receipts/image/{source}/{filename}`. The server:
- Converts HEIC/HEIF → JPEG on first request, caches as `.web.jpg`
- Resizes images >500KB to max 1200px, caches as `.web.jpg`
- Sets `Cache-Control: public, max-age=86400` (1-day browser cache)

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

Uses `difflib.SequenceMatcher` (stdlib) — no external dependency.

### Dedup in the UI

- Runs on **user-edited data** (not raw LLM output) — so corrections are checked
- Triggers in real-time as user edits fields (debounced 500ms)
- Shows side-by-side comparison: new vs existing receipt data + images
- Duplicate approval requires confirmation via modal dialog

---

## Background Watcher

### How It Works

- **Event-based** (default): Uses `watchdog` library for instant file detection via OS-native events (FSEvents on macOS, inotify on Linux)
- **Poll fallback**: Set `RECEIPT_WATCHER_MODE=poll` for 30-second interval scanning
- Watches **two folders simultaneously**: `~/Receipts` (drop folder) and `data/incoming/` (UI uploads)
- On startup, scans for files already in both watch folders (catches files dropped while watcher was off)
- On success: deletes original from watch folder
- On error: logs error, leaves file for retry

### Running Modes

| Mode | How to run | When to use |
|------|-----------|-------------|
| **Standalone process** | `python -m agents.receipt_analyzer.watcher` | Recommended — runs independently of API |
| **Console script** | `receipt-watcher` (after `pip install -e .`) | Same as above, convenience alias |

### Supported File Types

`.png`, `.jpg`, `.jpeg`, `.heic`, `.heif`, `.pdf`, `.webp`, `.gif`

Skips hidden files (starting with `.`).

---

## API Layer

### Running

```bash
# Accessible on local network (e.g., from phone)
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API serves both the REST endpoints and the static HTML/JS frontend.

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/receipts/upload` | Queue 1+ files to `data/incoming/` |
| `GET` | `/api/receipts/staged` | List all staged receipts |
| `POST` | `/api/receipts/staged/{id}/approve` | Approve + save to DB |
| `POST` | `/api/receipts/staged/{id}/reject` | Reject + move to rejected/ |
| `POST` | `/api/receipts/staged/{id}/reanalyze` | Re-run LLM extraction |
| `GET` | `/api/receipts/image/{source}/{filename}` | Serve receipt image |
| `GET` | `/api/expenses` | Query approved receipts (filterable) |
| `GET` | `/api/expenses/summary` | Aggregate stats by category |
| `DELETE` | `/api/expenses/{id}` | Delete receipt + archived image |
| `GET` | `/api/categories` | List all known categories |

### Upload Flow

UI uploads do **not** trigger LLM analysis synchronously. Instead:
1. Files are written to `data/incoming/`
2. Response returns immediately with `QueueResponse` (count + filenames)
3. Background watcher picks up files and processes them asynchronously
4. UI polls `/api/receipts/staged` every 4s to update the pending badge

---

## UI (FastAPI + Vanilla JS)

### Tabs

1. **Upload Receipt** — Multi-file selector; queues files and shows confirmation
2. **Pending Review (N)** — Lists all staged receipts with count badge, expandable cards
3. **Expenses** — Filterable table (date range, category, merchant) with View button per row
4. **Summary** — Aggregate metrics + spending-by-category bar chart

### Review Form Features

- **Editable fields:** Merchant, Address, Date, Category, Payment, Currency, Subtotal, Tax, Tip, Total
- **Read-only:** Line items table
- **Action buttons:** Approve & Save, Reject, Re-analyze, Copy JSON
- **Lazy loading:** Only the first pending receipt form is rendered; others load on expand
- **Duplicate detection:** Debounced real-time check as user edits fields

### Static Asset Caching

The `app.js` script tag includes a version query string (`?v=N`) to bust browser cache when the JS changes. Bump this when making breaking changes to field names or request formats — especially important for mobile clients which cache aggressively.

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

- **WAL mode** enabled for concurrent read/write (watcher + API)
- Line items stored as JSON string in `items_json` column
- Dates stored as ISO strings (sort correctly, unambiguous)
- Displayed in US format (MM/DD/YYYY) in the UI

---

## Folder Structure & Data Flow

| Folder | Purpose | Files | Lifecycle |
|--------|---------|-------|-----------|
| `~/Receipts` | Watch folder (user drop) | Receipt images/PDFs | Deleted after successful staging |
| `data/incoming/` | UI upload landing area | Receipt images/PDFs | Deleted after successful staging |
| `data/staging/` | Pending review | Image + JSON sidecar pairs | Removed on approve/reject |
| `data/archive/` | Approved receipts | Receipt images | Permanent storage |
| `data/rejected/` | Rejected receipts | Image + JSON sidecar | For later review |

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
RECEIPT_INCOMING_FOLDER=./data/incoming
RECEIPT_STAGING_FOLDER=./data/staging
RECEIPT_ARCHIVE_FOLDER=./data/archive
RECEIPT_REJECTED_FOLDER=./data/rejected
RECEIPT_WATCH_INTERVAL_SECONDS=30
```

**Important:** `load_dotenv()` must run before any LangChain imports for LangSmith tracing to work.

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
uv sync

# Configure
cp .env.example .env
# Edit .env with your API keys

# Terminal 1: Start the watcher
uv run python -m agents.receipt_analyzer.watcher

# Terminal 2: Start the API + UI
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` in a browser. Accessible from other devices on the same network via `http://<your-ip>:8000`.

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
| Upload queues to `data/incoming/` (not processed inline) | Decouples UI from LLM latency; watcher handles all sources uniformly |
| Vanilla JS frontend (no framework) | No build step, easy to iterate, full control |
| `?v=N` cache buster on `app.js` | Mobile browsers cache JS aggressively; bump N when field names change |

---

## Future Improvements

| # | Item | Status | Priority |
|---|------|--------|----------|
| 1 | Improved Duplicate Detection | Done | High |
| 2 | UI Framework Migration (Streamlit → FastAPI + vanilla JS) | Done | Medium |
| 3 | Multi-file Upload + Landing Area | Done | Medium |
| 4 | E2E Evals Framework | Pending (plan in `docs/evals-plan.md`) | High |
| 5 | ReAct Agent Pattern with DeepAgents | Pending | Medium |
| 6 | Standalone Watcher as System Service (launchd) | Pending | Low |
| 7 | Audit & Recovery Utility | Pending | Low |
| 8 | Multi-Row Delete in Expenses | Pending | Low |

### 4. E2E Evals Framework

See `docs/evals-plan.md` for the full plan. Four tiers: unit, integration, e2e (FastAPI TestClient), and live (real LLM + LLM-as-judge). Not yet implemented.

### 5. ReAct Agent Pattern with DeepAgents

**Current state:** Linear 4-node LangGraph pipeline (detect → extract → validate → stage). Sufficient for the current single-task workflow.

**When to evolve:** When the receipt agent needs tools — merchant lookup, currency conversion, category classification using history, etc.

### 6. Standalone Watcher as System Service

**Future:** Package as a `launchd` plist (macOS) or `systemd` unit file (Linux) for always-on background processing without a terminal window.

### 7. Audit & Recovery Utility

CLI utility to detect and fix inconsistencies: orphaned sidecars, DB records pointing to missing images, images in wrong folders after partial approval failures.

### 8. Multi-Row Delete in Expenses

Currently single receipt delete via the detail modal. Bulk select + delete for cleaning up test data or batch errors.
