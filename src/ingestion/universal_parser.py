import pandas as pd
import math
from typing import List, Union, Optional
from src.core.models import ShippingRecord
from src.core.config import config
from src.resolution.pre_processor import should_reject

def clean_name(name: str, strip_bank: bool) -> str:
    if not isinstance(name, str):
        return ""
    name = name.strip()
    if not name:
        return ""
    
    if strip_bank:
        name_upper = name.upper()
        # Common bank prefixes
        prefixes_to_strip = config["business_logic"]["bank_keywords"]
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
    size_col = column_mapping.get("size")
    teu_col = column_mapping.get("teu")
    # product_col = column_mapping.get("product_description") # Ignored for now as not in ShippingRecord model
    
    for _, row in df.iterrows():
        # Extract Required Fields
        bl = str(row[bl_col]).strip() if bl_col and bl_col in row and pd.notna(row[bl_col]) else None
        container = str(row[container_col]).strip() if container_col and container_col in row and pd.notna(row[container_col]) else None
        consignee_raw = str(row[consignee_col]).strip() if consignee_col and consignee_col in row and pd.notna(row[consignee_col]) else ""
        
        # Extract Optional Fields
        notify_raw = str(row[notify_col]).strip() if notify_col and notify_col in row and pd.notna(row[notify_col]) else ""
        size_raw = str(row[size_col]).strip() if size_col and size_col in row and pd.notna(row[size_col]) else None
        teu_raw = str(row[teu_col]).strip() if teu_col and teu_col in row and pd.notna(row[teu_col]) else None
        
        consignee_clean = clean_name(consignee_raw, strip_bank_prefixes)
        notify_clean = clean_name(notify_raw, strip_bank_prefixes)
        
        # We store the raw/clean values directly. Phase 2 Role Hierarchy will resolve this later.
        record = ShippingRecord(
            shipping_line="User_Defined", 
            vessel_name=None,
            container_number=container,
            bill_of_lading=bl,
            messy_party_name=consignee_clean, # Base mapping for Consignee
            notify_party=notify_clean,        # Base mapping for Notify Party
            party_role="Unknown",             # Will be assigned during Phase 2
            port_of_discharge=None,
            eta=None,
            size=size_raw,
            teu=teu_raw
        )
        records.append(record)
        
    return records
