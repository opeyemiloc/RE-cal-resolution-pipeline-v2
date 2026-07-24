# `src/ingestion/` — User-Driven Universal Parsing

This module is responsible for taking raw, messy Excel files from any shipping line and converting them into a clean, universal format (`ShippingRecord`) based on explicit user configuration.

## How It Works

Instead of relying on fragile, hardcoded parsers for each carrier (e.g., MSC, Hapag-Lloyd), the system utilizes a **User-Driven Ingestion Engine**. 

```text
Streamlit UI (User Settings) ──► universal_parser.py ──► List[ShippingRecord]
```

### `universal_parser.py`

This script contains a single universal function: `parse_user_driven_excel`. It dynamically processes Excel files by accepting a configuration payload from the UI:

1. **Target Sheet & Header Row:** Skips boilerplate metadata and finds the exact row where headers begin.
2. **Sub-header skip:** Optionally drops the row immediately following the header (common in ONE and ZIM manifests).
3. **Dynamic Column Mapping:** Extracts columns based on user dropdown selections, mapping raw columns to:
   - `Bill of Lading Number`
   - `Container Number`
   - `Consignee Name`
   - `Notify Party`
   - `Product / Cargo`

### Salvage Logic & Cleaning

The parser applies business rules during extraction:
- **Notify Party Fallback:** If the `Consignee` is empty or contains known "junk" strings (e.g., "SAME AS NOTIFY"), it will automatically substitute the `Notify Party` value.
- **Bank Prefix Stripping:** Cleans banking boilerplate text (e.g., "TO THE ORDER OF BANK OF...") before records hit the resolution pipeline.

### `parsers/master_parser.py` — Master Accounts Converter

Converts the Master Accounts Excel file into a flat JSON array of company names. It auto-detects the name column by looking for keywords like `name`, `account`, `company`, or `customer` in the header.
