from typing import List, Dict, Any, Callable
from src.resolution.exact_matcher import process_exact_matches
from src.resolution.candidate_generator import find_top_candidates
from src.resolution.pre_processor import should_reject, create_rejection_decision
from src.resolution.llm_resolver import resolve_candidates
from src.core.models import ShippingRecord

def run_resolution_pipeline(
    records: List[ShippingRecord], 
    master_json_path: str, 
    ui_callback: Callable[[str, dict], None] = None
) -> Dict[str, Any]:
    """
    Executes the full resolution funnel: Exact Match -> Junk Filter -> Vector Search -> LLM.
    
    Args:
        records: List of parsed ShippingRecords
        master_json_path: Path to the JSON master accounts list
        ui_callback: Optional callback function to emit progress to a UI (e.g., Streamlit).
                     Signature: callback(status_string, data_dictionary)
                     
    Returns:
        Dictionary containing exact_matches, auto_rejected, candidates, llm_decisions, and final_decisions.
    """
    
    # 1. Exact Matching
    if ui_callback: 
        ui_callback("deterministic_start", {})
        
    exact_matches, unmatched_records = process_exact_matches(records, master_json_path)

    # 2. Pre-Processor (Junk Filter)
    to_vector_search = []
    auto_rejected = []
    for record in unmatched_records:
        if should_reject(record.messy_party_name):
            auto_rejected.append(create_rejection_decision(record.messy_party_name))
        else:
            to_vector_search.append(record)

    # 3. Vector Search (Candidate Generation)
    candidates, _ = find_top_candidates(to_vector_search, master_json_path)

    # UI Hook before expensive LLM call
    if ui_callback: 
        ui_callback("deterministic_complete", {
            "exact_matches": exact_matches, 
            "auto_rejected": auto_rejected,
            "candidates": candidates
        })

    # 4. LLM Resolution
    llm_decisions = []
    if candidates:
        if ui_callback: 
            ui_callback("llm_start", {"count": len(candidates)})
            
        llm_decisions = resolve_candidates(candidates)

    # 5. Combine Results
    final_decisions = exact_matches + auto_rejected + llm_decisions
    
    if ui_callback: 
        ui_callback("pipeline_complete", {})
    
    return {
        "exact_matches": exact_matches,
        "auto_rejected": auto_rejected,
        "candidates": candidates,
        "llm_decisions": llm_decisions,
        "final_decisions": final_decisions
    }
