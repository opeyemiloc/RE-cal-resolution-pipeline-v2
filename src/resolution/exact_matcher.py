import json
from typing import List, Tuple, Dict, Set
from src.core.models import ShippingRecord, LLMMatchDecision
from src.resolution.normalizer import normalize_name

def check_token_containment(messy_name: str, master_name: str) -> bool:
    """
    Checks if the tokens of the shorter string are contained
    within the longer string, supporting truncation/prefix matching.
    """
    messy_tokens = messy_name.split()
    master_tokens = master_name.split()
    
    if not messy_tokens or not master_tokens:
        return False
        
    # Determine which is shorter in terms of token count
    if len(messy_tokens) <= len(master_tokens):
        shorter = messy_tokens
        longer = master_tokens
    else:
        shorter = master_tokens
        longer = messy_tokens
        
    # All tokens in shorter must be found in longer (or as a valid prefix)
    for s_tok in shorter:
        match_found = False
        for l_tok in longer:
            # Exact match OR truncation/prefix match for long tokens
            if s_tok == l_tok:
                match_found = True
                break
            elif len(s_tok) >= 5 and l_tok.startswith(s_tok):
                match_found = True
                break
            elif len(l_tok) >= 5 and s_tok.startswith(l_tok):
                match_found = True
                break
                
        if not match_found:
            return False
            
    return True

def process_exact_matches(records: List[ShippingRecord], master_accounts_path: str, custom_aliases: Dict[str, str] = None) -> Tuple[List[LLMMatchDecision], List[ShippingRecord]]:
    """
    Tier 1 (Auto-Resolve): 100% exact matches or 100% core-token (Token-Set Containment) matches.
    Everything else falls through to Tier 2 (Review Queue).
    """
    if not records:
        return [], []
        
    # Load master accounts
    with open(master_accounts_path, 'r', encoding='utf-8') as f:
        master_accounts = json.load(f)
        
    # 1. Direct Normalized Lookup for fast O(1) matching
    normalized_master_lookup: Dict[str, str] = {
        normalize_name(acc): acc for acc in master_accounts
    }
    
    master_accounts_set: Set[str] = set(master_accounts)
    exact_matches: List[LLMMatchDecision] = []
    unmatched_records: List[ShippingRecord] = []
    
    for record in records:
        clean_messy = normalize_name(record.messy_party_name)
        
        # Pass 0: Custom Workspace Aliases (User-approved overrides)
        if custom_aliases and record.messy_party_name in custom_aliases and custom_aliases[record.messy_party_name] in master_accounts_set:
            exact_matches.append(LLMMatchDecision(
                original_messy_name=record.messy_party_name,
                matched=True,
                resolved_master_name=custom_aliases[record.messy_party_name],
                confidence_score=100,
                reasoning="Tier 1: Exact match found in custom Workspace Aliases."
            ))
            continue
            
        # Pass 1: Direct Match
        if clean_messy in normalized_master_lookup:
            exact_matches.append(LLMMatchDecision(
                original_messy_name=record.messy_party_name,
                matched=True,
                resolved_master_name=normalized_master_lookup[clean_messy],
                confidence_score=100,
                reasoning="Tier 1: Perfect exact match on normalized string."
            ))
            continue
            
        # Pass 2: Token-Set Containment Match (No-Drop Funnel philosophy)
        matched = False
        possible_matches = []
        for clean_master, orig_master in normalized_master_lookup.items():
            if check_token_containment(clean_messy, clean_master):
                possible_matches.append(orig_master)
                
        # Only auto-resolve if it unambiguously matches exactly one master account
        if len(possible_matches) == 1:
            exact_matches.append(LLMMatchDecision(
                original_messy_name=record.messy_party_name,
                matched=True,
                resolved_master_name=possible_matches[0],
                confidence_score=100,
                reasoning="Tier 1: Token-Set Containment Match (truncation & noise ignored)."
            ))
            matched = True
            
        if not matched:
            unmatched_records.append(record)
            
    return exact_matches, unmatched_records