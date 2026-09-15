from typing import List, Dict, Any, Callable
from src.resolution.exact_matcher import process_exact_matches
from src.resolution.candidate_generator import find_top_candidates
from src.resolution.pre_processor import should_reject, create_rejection_decision
from src.resolution.llm_resolver import resolve_candidates
from src.core.models import ShippingRecord

def run_resolution_pipeline(
    records: List[ShippingRecord], 
    master_json_path: str, 
    custom_aliases: Dict[str, str] = None,
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
        
    exact_matches, unmatched_records = process_exact_matches(records, master_json_path, custom_aliases)

    from src.resolution.normalizer import normalize_name
    from src.core.models import LLMMatchDecision
    
    # 2. Pre-Processor (Junk Filter & Short Acronym Filter)
    to_vector_search = []
    auto_rejected = []
    short_acronym_names = set()
    
    for record in unmatched_records:
        if should_reject(record.messy_party_name):
            auto_rejected.append(create_rejection_decision(record.messy_party_name))
        else:
            clean_messy = normalize_name(record.messy_party_name)
            if len(clean_messy.split()) == 1:
                short_acronym_names.add(record.messy_party_name)
            to_vector_search.append(record)
                
    # 3. Vector Search (Candidate Generation)
    candidates, _ = find_top_candidates(to_vector_search, master_json_path)
    
    # 3.5 Intercept Short Acronyms
    llm_decisions = []
    candidates_for_llm = []
    for c in candidates:
        if c.messy_name in short_acronym_names:
            llm_decisions.append(LLMMatchDecision(
                original_messy_name=c.messy_name,
                matched=False,
                resolved_master_name=None,
                confidence_score=0,
                reasoning="Bypassed AI: Short acronyms require 100% exact match."
            ))
        else:
            candidates_for_llm.append(c)

    # UI Hook before expensive LLM call
    if ui_callback: 
        ui_callback("deterministic_complete", {
            "exact_matches": exact_matches, 
            "auto_rejected": auto_rejected,
            "candidates": candidates
        })

    # 4. LLM Resolution
    if candidates_for_llm:
        if ui_callback: 
            ui_callback("llm_start", {"count": len(candidates_for_llm)})
            
        llm_decisions.extend(resolve_candidates(candidates_for_llm))

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
