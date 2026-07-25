import pandas as pd
import io
import datetime
from typing import Dict, Any, Tuple

def create_empty_workspace_template() -> bytes:
    """Generates an empty Workspace Excel file with the required tabs and columns."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        pd.DataFrame(columns=["USER", "Original Messy Name", "Master Name"]).to_excel(writer, sheet_name="Aliases", index=False)
        pd.DataFrame(columns=["Setting Key", "Setting Value"]).to_excel(writer, sheet_name="Settings", index=False)
        pd.DataFrame(columns=["Date", "Total Records", "Exact Matches", "Auto Rejected", "AI Matches"]).to_excel(writer, sheet_name="Run_History", index=False)
    return buffer.getvalue()

def create_master_template() -> bytes:
    """Generates a sample multi-tenant Master Accounts Excel file with tabs for different operators."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_sample = pd.DataFrame([
            {"Account Name": "Flourish Global Appliances Ltd", "Alias / ID": "FLOURISH_001"},
            {"Account Name": "Dangote Cement Plc", "Alias / ID": "DANGOTE_CEM"},
            {"Account Name": "Nestle Nigeria Plc", "Alias / ID": "NESTLE_NG"}
        ])
        df_sample.to_excel(writer, sheet_name="OPE", index=False)
        df_sample.to_excel(writer, sheet_name="MICHEAL", index=False)
        df_sample.to_excel(writer, sheet_name="NNEOMA", index=False)
    return buffer.getvalue()

def create_manifest_template() -> bytes:
    """Generates a sample multi-carrier Shipping Manifest Excel file with tabs for different shipping lines."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_msc = pd.DataFrame([
            {"B/L NO": "MEDU12345678", "Cont. Prefix": "MSCU9876543", "Receiver": "FLOURISH GLOBAL APPLIANCES LTD", "Notify Name": "SAME AS RECEIVER", "Cargo Desc": "ELECTRONICS"},
            {"B/L NO": "MEDU87654321", "Cont. Prefix": "MSCU3456789", "Receiver": "TO THE ORDER OF BANK OF AFRICA", "Notify Name": "DANGOTE CEMENT PLC", "Cargo Desc": "RAW MATERIALS"}
        ])
        df_hapag = pd.DataFrame([
            {"BL_NUMBER": "HLCU11223344", "CONTAINER_ID": "HLBU5566778", "CONSIGNEE": "NESTLE NIGERIA PLC", "NOTIFY_PARTY": "NESTLE NIGERIA PLC", "DESCRIPTION": "FOOD PRODUCTS"}
        ])
        df_msc.to_excel(writer, sheet_name="MSC", index=False)
        df_hapag.to_excel(writer, sheet_name="Hapag-Lloyd", index=False)
        df_msc.to_excel(writer, sheet_name="ONE", index=False)
    return buffer.getvalue()

def load_workspace(file_bytes: bytes, target_user: str = None) -> Tuple[Dict[str, str], Dict[str, Any], pd.DataFrame]:
    """Loads the Workspace Excel file and extracts its data."""
    buffer = io.BytesIO(file_bytes)
    
    # Load Aliases
    try:
        df_aliases = pd.read_excel(buffer, sheet_name="Aliases")
        if "USER" in df_aliases.columns and target_user is not None and str(target_user).strip() != "" and str(target_user) != "None" and str(target_user) != "0":
            df_aliases = df_aliases[df_aliases["USER"].astype(str) == str(target_user)]
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

def update_workspace(file_bytes: bytes, new_aliases: Dict[str, str], current_settings: Dict[str, Any], run_stats: Dict[str, Any], active_user: str = "Default") -> bytes:
    """Merges new aliases, current settings, and the latest run stats into a new Excel file."""
    # Load existing to append to
    if file_bytes:
        _, _, df_history = load_workspace(file_bytes)
        buffer = io.BytesIO(file_bytes)
        try:
            df_existing_aliases = pd.read_excel(buffer, sheet_name="Aliases")
            if "USER" not in df_existing_aliases.columns:
                df_existing_aliases["USER"] = "Default"
        except Exception:
            df_existing_aliases = pd.DataFrame(columns=["USER", "Original Messy Name", "Master Name"])
    else:
        df_existing_aliases = pd.DataFrame(columns=["USER", "Original Messy Name", "Master Name"])
        df_history = pd.DataFrame(columns=["Date", "Total Records", "Exact Matches", "Auto Rejected", "AI Matches"])
        
    # 1. Merge Aliases for active_user
    new_rows = []
    for messy, master in new_aliases.items():
        df_existing_aliases = df_existing_aliases[
            ~((df_existing_aliases["USER"].astype(str) == str(active_user)) & (df_existing_aliases["Original Messy Name"].astype(str) == str(messy)))
        ]
        new_rows.append({"USER": str(active_user), "Original Messy Name": str(messy), "Master Name": str(master)})
        
    if new_rows:
        df_new_aliases = pd.concat([df_existing_aliases, pd.DataFrame(new_rows)], ignore_index=True)
    else:
        df_new_aliases = df_existing_aliases
    
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
