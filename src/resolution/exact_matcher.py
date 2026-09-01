import json
import difflib
from typing import List, Tuple, Dict, Set
from src.core.models import ShippingRecord, LLMMatchDecision
from src.resolution.normalizer import normalize_name
from src.core.config import config

def strip_trailing_suffixes(name: str) -> str:
    """
    Removes common corporate suffixes ONLY from the end of the brand name.
    Protects words if they are part of the core brand (e.g., 'INTERNATIONAL BREWERIES').
    Also strips trailing 'S' for singularization.
    """
    suffix_words = set(config['business_logic']['suffix_words'])
    if not name:
        return ""
        
    tokens = name.split()
    
    # Keep popping words off the end as long as they are in our suffix list.
    while len(tokens) > 1 and tokens[-1] in suffix_words:
        tokens.pop()
        
    core_name = " ".join(tokens)
    # Singularize: if length > 3 and ends with 'S', strip it
    if len(core_name) > 3 and core_name.endswith('S'):
        core_name = core_name[:-1]
        
    return core_name

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
            
    # 3. Fingerprint Lookup (Pass 3 prep)
    fingerprint_master_lookup: Dict[str, str] = {}
    ambiguous_fingerprints: Set[str] = set()
    for clean_acc, orig_acc in normalized_master_lookup.items():
        fg = clean_acc.replace(" ", "")
        if len(fg) > 7:
            if fg in fingerprint_master_lookup:
                ambiguous_fingerprints.add(fg)
            elif fg not in ambiguous_fingerprints:
                fingerprint_master_lookup[fg] = orig_acc
                
    for fg in ambiguous_fingerprints:
        if fg in fingerprint_master_lookup:
            del fingerprint_master_lookup[fg]
            
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
            # Let's try Pass 3, 4, 5
            matched = False
            messy_fg = clean_messy.replace(" ", "")
            
            # Pass 3: Whitespace Fingerprint Match
            if len(messy_fg) > 7 and messy_fg in fingerprint_master_lookup:
                exact_matches.append(LLMMatchDecision(
                    original_messy_name=record.messy_party_name,
                    matched=True,
                    resolved_master_name=fingerprint_master_lookup[messy_fg],
                    confidence_score=100,
                    reasoning="Pass 3: Exact match on whitespace-stripped fingerprint."
                ))
                matched = True
            
            if not matched:
                # Iterate for Pass 4 and 5
                messy_tokens = set(clean_messy.split())
                for clean_master, orig_master in normalized_master_lookup.items():
                    # Pass 4: Token Subset Match
                    master_tokens = set(clean_master.split())
                    shared = messy_tokens.intersection(master_tokens)
                    if len(shared) >= 2 and (messy_tokens.issubset(master_tokens) or master_tokens.issubset(messy_tokens)):
                        exact_matches.append(LLMMatchDecision(
                            original_messy_name=record.messy_party_name,
                            matched=True,
                            resolved_master_name=orig_master,
                            confidence_score=100,
                            reasoning="Pass 4: Token subset match (shared >= 2 words)."
                        ))
                        matched = True
                        break
                    
                    # Pass 5: Fuzzy Typo Match (0 vs O, transposed letters)
                    similarity = difflib.SequenceMatcher(None, clean_messy, clean_master).ratio()
                    if similarity >= 0.92:
                        exact_matches.append(LLMMatchDecision(
                            original_messy_name=record.messy_party_name,
                            matched=True,
                            resolved_master_name=orig_master,
                            confidence_score=98,
                            reasoning=f"Pass 5: High similarity fuzzy typo match ({similarity*100:.1f}%)."
                        ))
                        matched = True
                        break
            
            if not matched:
                unmatched_records.append(record)
            
    return exact_matches, unmatched_records