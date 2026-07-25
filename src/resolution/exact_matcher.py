import json
from typing import List, Tuple, Dict, Set
from src.core.models import ShippingRecord, LLMMatchDecision
from src.resolution.normalizer import normalize_name
from src.core.config import config

def strip_trailing_suffixes(name: str) -> str:
    """
    Removes common corporate suffixes ONLY from the end of the brand name.
    Protects words if they are part of the core brand (e.g., 'INTERNATIONAL BREWERIES').
    """
    suffix_words = set(config['business_logic']['suffix_words'])
    if not name:
        return ""
        
    tokens = name.split()
    
    # Keep popping words off the end as long as they are in our suffix list.
    # We require len(tokens) > 1 so we don't accidentally strip a company 
    # whose entire name is literally just a suffix word.
    while len(tokens) > 1 and tokens[-1] in suffix_words:
        tokens.pop()
        
    return " ".join(tokens)

def process_exact_matches(records: List[ShippingRecord], master_accounts_path: str, custom_aliases: Dict[str, str] = None) -> Tuple[List[LLMMatchDecision], List[ShippingRecord]]:
    """
    Pass 1: Direct exact match on normalized names.
    Pass 2: Core brand exact match (ignoring trailing suffixes).
    """
    if not records:
        return [], []
        
    # Load master accounts
    with open(master_accounts_path, 'r', encoding='utf-8') as f:
        master_accounts = json.load(f)
        
    # 1. Direct Normalized Lookup
    normalized_master_lookup: Dict[str, str] = {
        normalize_name(acc): acc for acc in master_accounts
    }
    
    # 2. Core Brand Lookup (stripping trailing suffixes)
    core_master_lookup: Dict[str, str] = {}
    ambiguous_cores: Set[str] = set()
    
    for acc in master_accounts:
        clean_acc = normalize_name(acc)
        core_acc = strip_trailing_suffixes(clean_acc)
        
        if not core_acc:
            continue
            
        if core_acc in core_master_lookup:
            # We found a duplicate core! (e.g. ABC LTD and ABC PLC)
            # Add it to the ambiguous list so we don't accidentally guess the wrong one.
            ambiguous_cores.add(core_acc)
        elif core_acc not in ambiguous_cores:
            core_master_lookup[core_acc] = acc
            
    # Remove all ambiguous cores from the lookup dictionary entirely
    for core in ambiguous_cores:
        if core in core_master_lookup:
            del core_master_lookup[core]
            
    master_accounts_set: Set[str] = set(master_accounts)
    exact_matches: List[LLMMatchDecision] = []
    unmatched_records: List[ShippingRecord] = []
    
    for record in records:
        clean_messy = normalize_name(record.messy_party_name)
        core_messy = strip_trailing_suffixes(clean_messy)
        
        # Pass 0: Custom Workspace Aliases (User-approved overrides)
        if custom_aliases and record.messy_party_name in custom_aliases and custom_aliases[record.messy_party_name] in master_accounts_set:
            exact_matches.append(LLMMatchDecision(
                original_messy_name=record.messy_party_name,
                matched=True,
                resolved_master_name=custom_aliases[record.messy_party_name],
                confidence_score=100,
                reasoning="Pass 0: Exact match found in custom Workspace Aliases."
            ))
        # Pass 1: Direct Match
        elif clean_messy in normalized_master_lookup:
            exact_matches.append(LLMMatchDecision(
                original_messy_name=record.messy_party_name,
                matched=True,
                resolved_master_name=normalized_master_lookup[clean_messy],
                confidence_score=100,
                reasoning="Pass 1: Perfect exact match on normalized string."
            ))
        # Pass 2: Core Brand Match
        elif core_messy in core_master_lookup:
            exact_matches.append(LLMMatchDecision(
                original_messy_name=record.messy_party_name,
                matched=True,
                resolved_master_name=core_master_lookup[core_messy],
                confidence_score=100,
                reasoning="Pass 2: Exact match on core brand (trailing suffixes ignored)."
            ))
        else:
            unmatched_records.append(record)
            
    return exact_matches, unmatched_records