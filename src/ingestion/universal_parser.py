import pandas as pd
import math
from typing import List, Union, Optional
from src.core.models import ShippingRecord

def clean_name(name: str, strip_bank: bool) -> str:
    if not isinstance(name, str):
        return ""
    name = name.strip()
    if not name:
        return ""
    
    if strip_bank:
        name_upper = name.upper()
        # Common bank prefixes
        prefixes_to_strip = [
            "TO THE ORDER OF BANK OF ",
            "TO THE ORDER OF ",
            "TO ORDER OF ",
            "ORDER OF "
        ]
        for prefix in prefixes_to_strip:
            if name_upper.startswith(prefix):
                # Remove prefix but keep original casing for the rest
                name = name[len(prefix):].strip()
                break
    return name

def parse_user_driven_excel(
    file_source,
    sheet_name: Union[str, int] = 0,
    header_row_index: int = 0,
    skip_sub_header: bool = False,
    column_mapping: Optional[dict] = None,
    salvage_notify: bool = True,
    strip_bank_prefixes: bool = True
) -> List[ShippingRecord]:
    """
    Universally parse shipping manifests based on user-driven configuration.
    """
    if column_mapping is None:
        raise ValueError("column_mapping is required.")

    # 1. Load Sheet
    df = pd.read_excel(file_source, sheet_name=sheet_name, header=header_row_index)
    
    # 2. Handle Sub-headers
    if skip_sub_header and len(df) > 0:
        df = df.iloc[1:].reset_index(drop=True)
    
    records = []
    
    bl_col = column_mapping.get("bl_number")
    container_col = column_mapping.get("container_number")
    consignee_col = column_mapping.get("consignee_name")
    notify_col = column_mapping.get("notify_party")
    # product_col = column_mapping.get("product_description") # Ignored for now as not in ShippingRecord model
    
    for _, row in df.iterrows():
        # Extract Required Fields
        bl = str(row[bl_col]).strip() if bl_col and bl_col in row and pd.notna(row[bl_col]) else None
        container = str(row[container_col]).strip() if container_col and container_col in row and pd.notna(row[container_col]) else None
        consignee_raw = str(row[consignee_col]).strip() if consignee_col and consignee_col in row and pd.notna(row[consignee_col]) else ""
        
        # Extract Optional Fields
        notify_raw = str(row[notify_col]).strip() if notify_col and notify_col in row and pd.notna(row[notify_col]) else ""
        
        consignee_clean = clean_name(consignee_raw, strip_bank_prefixes)
        notify_clean = clean_name(notify_raw, strip_bank_prefixes)
        
        final_party_name = consignee_clean
        final_party_role = "Consignee"
        
        # 4. Apply Salvage Logic
        if salvage_notify:
            # Check if consignee is missing or just junk like "SAME AS NOTIFY"
            is_empty_or_junk = not final_party_name or final_party_name.upper() in ["SAME AS NOTIFY", "SAME AS NOTIFY PARTY", "TO ORDER"]
            if is_empty_or_junk and notify_clean:
                final_party_name = notify_clean
                final_party_role = "Salvaged Consignee"
        
        if not final_party_name:
            final_party_role = "Unknown"
            
        record = ShippingRecord(
            shipping_line="User_Defined", # We can leave this generic or add it to mapping
            vessel_name=None,
            container_number=container,
            bill_of_lading=bl,
            messy_party_name=final_party_name,
            party_role=final_party_role,
            port_of_discharge=None,
            eta=None
        )
        records.append(record)
        
    return records
