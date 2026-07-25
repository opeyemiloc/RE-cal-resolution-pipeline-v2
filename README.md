# Container Arrival List (CAL) AI Resolution Pipeline (V2)

An automated data extraction and AI-powered entity resolution pipeline that processes unstructured shipping documents (Container Arrival Lists) and matches incoming freight consignees to a master accounts database.

## What It Does

Shipping lines (MSC, Hapag-Lloyd, ONE, COSCO) each send container arrival lists in different messy Excel formats. This pipeline:

1. **Ingests** any supported Excel file and extracts structured data using a dynamic, user-steered UI.
2. **Filters** junk records (e.g., "TO ORDER", "BANK") instantly.
3. **Matches** messy consignee names to your master accounts list deterministically using string normalization and **Portable Workspace Aliases**.
4. **Vector Searches** a database of candidates for any records that fail deterministic matching.
5. **AI Resolution (Batched)** sends ambiguous records to Gemini in optimized batches to make final matching decisions, completely bypassing rate limits.
6. **Active Learning (Human-in-the-Loop)** flags low-confidence AI matches for human review, allowing users to approve them into a portable Alias Dictionary for future runs.
7. **Reports** results via a dynamic Streamlit dashboard with Pivot-Table Drill-Downs and a Standalone `.xlsx` Export.

## Architecture

```text
Excel Upload ──► Streamlit UI Config ──► Universal Parser ──► Universal Schema
(Master & Manifest)                                                │
                                                                   ▼
┌──────────────────────────────────────────┐             Exact Matcher (Pass 0: Custom Aliases,
│ 📁 Portable Workspace (Active Learning)  │ ◄────────── Pass 1: Normalized, Pass 2: Core Brand)
└──────────────────────────────────────────┘                       │
                                                         ┌─────────┴─────────┐
                                                         ▼                   ▼
                                                   ✅ Matched          Unmatched
                                                                             │
                                                                       Junk Pre-Filter
                                                                             │             │
                                                                             ▼             ▼
                                                                      🔴 Rejected    Vector Search (FAISS + Sentence Transformers)
                                                                                           │
                                                                                     ┌─────┴─────┐
                                                                                     ▼           ▼
                                                                              Below Threshold  🟡 Top Candidates
                                                                              (Dropped)          │
                                                                                                 ▼
                                                                                           LLM Resolver (Gemini)
                                                                                        (Exponential Backoff + Batching)
                                                                                                 │
                                                                                     ┌───────────┴───────────┐
                                                                                     ▼                       ▼
                                                                              ⚠️ Needs Review (<95%)   ✅ High Confidence
                                                                               (Editable in UI)          (Editable in UI)
                                                                                     │                       │
                                                                                     ▼                       ▼
                                                                          💾 Saved to Portable Workspace & Exported as Excel
```

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/opeyemiloc/RE-cal-resolution-pipeline.git
cd RE-cal-resolution-pipeline

# 2. Create and activate a virtual environment
python -m venv re_env
source re_env/Scripts/activate  # Git Bash on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables (Gemini API Key)
# If running locally, set it in your terminal. If running on Streamlit Cloud, add it to Streamlit Secrets:
# GEMINI_API_KEY="your_api_key_here"

# 5. Launch the Streamlit app
streamlit run app.py
```

The app opens at `http://localhost:8501`. 

## V2 Major Features

### 1. User-Driven Ingestion Engine & Multi-Tenancy
Instead of relying on fragile, hardcoded parsers or database user authentication, this pipeline features a completely dynamic multi-tab Excel ingestion engine:
- **Zero-Overhead Multi-Tenancy (Master Accounts)**: Store different operators or client lists (e.g., OPE, MICHEAL, NNEOMA) as different tabs in a single Master Excel file. Select which sheet to use on the fly with live visual previews.
- **Multi-Carrier Manifest Support**: Switch between different shipping line tabs (e.g., MSC, Hapag-Lloyd, ONE) in a single workbook without reloading.
- **Target Sheet & Header Index**: Skip boilerplate formatting and identify exactly where table headers begin with real-time visual table previews.
- **Dynamic Column Mapping**: Map required (`BL`, `Container`, `Consignee`) and optional fields dynamically from dropdowns populated from the selected sheet.
- **Starter Templates**: Downloadable multi-tab starter templates directly in the UI to guide users on structuring multi-user master lists and multi-carrier manifests.

### 2. The Portable Workspace (Active Learning)
Because cloud environments (like Streamlit Community Cloud) reset frequently, V2 introduces a stateless **Portable Brain**.
- **Upload an Excel Workspace** to instantly inject your saved Settings and Custom Aliases.
- **Pass 0 Matching**: The pipeline bypasses expensive AI calls by checking your Workspace Aliases first.
- **Human-in-the-Loop Review**: At the end of the pipeline, AI results are split into a **Needs Review Queue (< 95% Confidence)** and a High Confidence Queue. Users can edit decisions, check "Approve for Learning", and instantly download an updated Workspace Excel for tomorrow.

### 3. Advanced Settings Control Center
A dedicated UI tab to override `config.yaml` parameters in real-time:
- **Entity Resolution**: Tune FAISS similarity score thresholds and Top-K lookups.
- **Dynamic Cleaning Rules**: Edit Junk filter phrases, Suffix lists, and Bank stripping logic.
- **LLM Switching**: Swap between Gemini Flash models on the fly.

### 4. Interactive Analytics & Excel Reporting
- **Pivot-Table Drill-Down**: Click on any row in the Deterministic, Ambiguous, or AI tables to instantly view the underlying raw manifest records (Bill of Lading, Container, Consignee) that share that name.
- **Standalone Excel Export**: Export a pristine, professional `.xlsx` report tagging every record by `Resolution Type` (Exact Match, Junk Filter, or AI Model).

## Tech Stack

- **Python 3.x** with Pydantic for strict LLM data validation
- **pandas** for messy Excel parsing and data manipulation
- **FAISS + Sentence Transformers** for vector similarity search
- **Google GenAI SDK** for batched LLM entity resolution
- **Tenacity** for bulletproof Exponential Backoff & rate limit handling
- **Streamlit** for the web GUI & Interactive Data Editors
