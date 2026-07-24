# Container Arrival List (CAL) AI Resolution Pipeline

An automated data extraction and AI-powered entity resolution pipeline that processes unstructured shipping documents (Container Arrival Lists) and matches incoming freight consignees to a master accounts database.

## What It Does

Shipping lines (MSC, Hapag-Lloyd, ONE, COSCO) each send container arrival lists in different messy Excel formats. This pipeline:

1. **Ingests** any supported Excel file and extracts structured data.
2. **Filters** junk records (e.g., "TO ORDER", "BANK") instantly.
3. **Matches** messy consignee names to your master accounts list deterministically using string normalization.
4. **Vector Searches** a database of candidates for any records that fail deterministic matching.
5. **AI Resolution (Batched)** sends ambiguous records to Gemini 3.6 Flash in optimized batches to make final matching decisions, completely bypassing rate limits.
6. **Reports** results via a dynamic Streamlit dashboard with full CSV download support.

## Architecture

```text
Excel Upload ──► Streamlit UI Config ──► Universal Parser ──► Universal Schema
                                                                  │
                            ┌─────────────────────────────┘
                            ▼
                     Exact Matcher (Pass 1: Normalized, Pass 2: Core Brand)
                            │
                     ┌──────┴──────┐
                     ▼             ▼
               ✅ Matched    Unmatched
                                   │
                            Junk Pre-Filter
                            │             │
                            ▼             ▼
                     🔴 Rejected    Vector Search (FAISS + Sentence Transformers)
                                          │
                                   ┌──────┴──────┐
                                   ▼             ▼
                            Below Threshold   🟡 Top Candidates
                            (Dropped)             │
                                                  ▼
                                           LLM Resolver (Gemini)
                                        (Exponential Backoff + Batching)
                                                  │
                                            Final Decisions
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

The app opens at `http://localhost:8501`. Upload a **Master Accounts Excel** and a **Manifest Excel** from the sidebar, then click **Run Pipeline**.

## User-Driven Ingestion Engine

Instead of relying on fragile, hardcoded parsers for each shipping line, this pipeline features a completely dynamic ingestion engine. Through the Streamlit UI, users explicitly define how to parse their manifests:

1. **Target Sheet & Header Index**: Skip boilerplate formatting and identify exactly where data starts.
2. **Live Data Preview**: Immediately see how the parser views the target header row.
3. **Dynamic Column Mapping**: Map required (`BL`, `Container`, `Consignee`) and optional fields dynamically from dropdowns.
4. **Business Logic Overrides**: Toggle automatic "Notify Party" fallback and bank prefix stripping on the fly.

## Configuration

All tunable settings live in [`config.yaml`](config.yaml):

- **`paths`** — Input/output/reference directories
- **`thresholds`** — Vector search quality gate (e.g., `0.3`), minimum name length
- **`llm`** — Model name (`gemini-3.6-flash`), batch inference size (`batch_size: 5`), and temperature
- **`business_logic`** — Suffix words, junk patterns, bank keywords

## Future Roadmap & Admin Dashboard

To see the planned transition of this tool into a full SaaS product (including Database Integration, Admin Dashboards, and Continuous AI Learning), please refer to the [ROADMAP.md](ROADMAP.md) file.

## Tech Stack

- **Python 3.x** with Pydantic for strict LLM data validation
- **pandas** for messy Excel parsing
- **FAISS + Sentence Transformers** for vector similarity search
- **Google GenAI SDK (Gemini 3.6 Flash)** for batched LLM entity resolution
- **Tenacity** for bulletproof Exponential Backoff & rate limit handling
- **Streamlit** for the web GUI
