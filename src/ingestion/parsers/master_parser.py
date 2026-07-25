import os
import json
import pandas as pd
from typing import List

def ingest_master_list_excel(excel_path: str, output_json_path: str, name_col: str = None, id_col: str = None, alias_col: str = None, sheet_name: str | int = 0, header_row_index: int = 0) -> str:
    """
    Reads a Master List Excel file, extracts account names (and optionally aliases), 
    and saves them as a JSON array for the pipeline to use.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"❌ Master list Excel not found at {excel_path}")
        
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row_index)
    except Exception as e:
        raise ValueError(f"Failed to read Master List Excel. Error: {e}")
    
    # 1. Extract the data
    names = []
    
    if name_col and name_col in df.columns:
        names.extend(df[name_col].dropna().astype(str).str.strip().tolist())
        
    if alias_col and alias_col in df.columns:
        names.extend(df[alias_col].dropna().astype(str).str.strip().tolist())
        
    # If no custom columns were provided or found, fallback to intelligent search
    if not names:
        target_col = None
        for col in df.columns:
            col_name = str(col).lower()
            if "name" in col_name or "account" in col_name or "company" in col_name or "customer" in col_name:
                target_col = col
                break
                
        if not target_col:
            target_col = df.columns[0] 
            
        names = df[target_col].dropna().astype(str).str.strip().tolist()

    # 2. Get unique values
    names = list(set(names))
    
    # Remove any empty strings that might have snuck in
    names = [n for n in names if n]
    
    # 3. Save to JSON
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with open(output_json_path, 'w') as f:
        json.dump(names, f, indent=2)
        
    print(f"✅ Converted Master List Excel to JSON ({len(names)} accounts) -> {output_json_path}")
    return output_json_path