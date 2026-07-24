import pandas as pd
import io
import datetime
from typing import Dict, Any, Tuple

def create_empty_workspace_template() -> bytes:
    """Generates an empty Workspace Excel file with the required tabs and columns."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        pd.DataFrame(columns=["Original Messy Name", "Master Name"]).to_excel(writer, sheet_name="Aliases", index=False)
        pd.DataFrame(columns=["Setting Key", "Setting Value"]).to_excel(writer, sheet_name="Settings", index=False)
        pd.DataFrame(columns=["Date", "Total Records", "Exact Matches", "Auto Rejected", "AI Matches"]).to_excel(writer, sheet_name="Run_History", index=False)
    return buffer.getvalue()

def load_workspace(file_bytes: bytes) -> Tuple[Dict[str, str], Dict[str, Any], pd.DataFrame]:
    """Loads the Workspace Excel file and extracts its data."""
    buffer = io.BytesIO(file_bytes)
    
    # Load Aliases
    try:
        df_aliases = pd.read_excel(buffer, sheet_name="Aliases")
        aliases = dict(zip(df_aliases["Original Messy Name"].astype(str), df_aliases["Master Name"].astype(str)))
    except Exception:
        aliases = {}
        
    # Load Settings
    try:
        buffer.seek(0)
        df_settings = pd.read_excel(buffer, sheet_name="Settings")
        settings = dict(zip(df_settings["Setting Key"].astype(str), df_settings["Setting Value"]))
    except Exception:
        settings = {}
        
    # Load History
    try:
        buffer.seek(0)
        df_history = pd.read_excel(buffer, sheet_name="Run_History")
    except Exception:
        df_history = pd.DataFrame(columns=["Date", "Total Records", "Exact Matches", "Auto Rejected", "AI Matches"])
        
    return aliases, settings, df_history

def update_workspace(file_bytes: bytes, new_aliases: Dict[str, str], current_settings: Dict[str, Any], run_stats: Dict[str, Any]) -> bytes:
    """Merges new aliases, current settings, and the latest run stats into a new Excel file."""
    # Load existing to append to
    if file_bytes:
        aliases, _, df_history = load_workspace(file_bytes)
    else:
        aliases = {}
        df_history = pd.DataFrame(columns=["Date", "Total Records", "Exact Matches", "Auto Rejected", "AI Matches"])
        
    # 1. Merge Aliases
    aliases.update(new_aliases)
    df_new_aliases = pd.DataFrame(list(aliases.items()), columns=["Original Messy Name", "Master Name"])
    
    # 2. Update Settings
    df_new_settings = pd.DataFrame(list(current_settings.items()), columns=["Setting Key", "Setting Value"])
    
    # 3. Append History
    new_run = pd.DataFrame([{
        "Date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Total Records": run_stats.get("Total Records", 0),
        "Exact Matches": run_stats.get("Exact Matches", 0),
        "Auto Rejected": run_stats.get("Auto Rejected", 0),
        "AI Matches": run_stats.get("AI Matches", 0)
    }])
    df_new_history = pd.concat([df_history, new_run], ignore_index=True)
    
    # Write to new buffer
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_new_aliases.to_excel(writer, sheet_name="Aliases", index=False)
        df_new_settings.to_excel(writer, sheet_name="Settings", index=False)
        df_new_history.to_excel(writer, sheet_name="Run_History", index=False)
        
    return buffer.getvalue()
