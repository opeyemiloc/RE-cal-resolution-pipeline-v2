from typing import List, Dict
from src.core.models import ShippingRecord

def reconcile_roles(
    raw_records: List[ShippingRecord], 
    name_to_master: Dict[str, str], 
    bank_keywords: List[str]
) -> None:
    """
    Applies the Dual-Field Role Hierarchy logic to assign the final master account and role.
    Modifies the ShippingRecord objects in-place.
    """
    for r in raw_records:
        c_match = name_to_master.get(r.messy_party_name)
        n_match = name_to_master.get(r.notify_party)
        
        is_bank_consignee = not r.messy_party_name or any(
            r.messy_party_name.upper().startswith(kw) for kw in bank_keywords
        )
        
        if c_match and (not n_match or c_match == n_match):
            r.party_role = "Consignee"
        elif n_match and not c_match:
            r.messy_party_name = r.notify_party 
            if is_bank_consignee:
                r.party_role = "Salvaged Consignee"
            else:
                r.party_role = "Third-Party Consignee"
        else:
            r.party_role = "Unknown/Conflict"

