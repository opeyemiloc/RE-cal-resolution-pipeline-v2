import json
import faiss
from typing import List, Tuple, Dict, Any
from sentence_transformers import SentenceTransformer
from src.core.models import ShippingRecord, ResolutionCandidate
from src.resolution.normalizer import normalize_name
from src.core.config import config

def find_top_candidates(records: List[ShippingRecord], master_accounts_path: str) -> Tuple[List[ResolutionCandidate], List[Dict[str, Any]]]:
    quality_threshold = config['thresholds']['vector_quality_threshold']
    vector_k_candidates = config['thresholds'].get('vector_k_candidates', 3)
    embedding_model_name = config['thresholds'].get('embedding_model', 'all-MiniLM-L6-v2')
    
    # Load model lazily
    model = SentenceTransformer(embedding_model_name)
    
    with open(master_accounts_path, 'r', encoding='utf-8') as f:
        master_accounts = json.load(f)
    
    # EMBED THE NORMALIZED MASTER NAMES
    clean_master_names = [normalize_name(acc) for acc in master_accounts]
    master_embeddings = model.encode(clean_master_names)
    
    dimension = master_embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(master_embeddings)
    
    candidates: List[ResolutionCandidate] = []
    math_debug_log: List[Dict[str, Any]] = []
    
    if not records:
        return candidates, math_debug_log
        
    # BATCH EMBED THE MESSY NAMES
    clean_messy_names = [normalize_name(record.messy_party_name) for record in records]
    messy_embeddings = model.encode(clean_messy_names)
    
    for idx, record in enumerate(records):
        clean_messy = clean_messy_names[idx]
        messy_vector = messy_embeddings[idx:idx+1]
        distances, indices = index.search(messy_vector, k=vector_k_candidates)
        
        best_distance = float(distances[0][0])
        # We still return the original master names to the AI
        top_names = [master_accounts[i] for i in indices[0]]
        all_distances = [float(d) for d in distances[0]]
        
        passed_threshold = best_distance <= quality_threshold
        
        math_debug_log.append({
            "original_messy_name": record.messy_party_name,
            "normalized_messy_name": clean_messy,
            "best_match_name": top_names[0],
            "best_match_distance": round(best_distance, 4),
            "threshold_limit": quality_threshold,
            "passed_gatekeeper": passed_threshold,
            "top_3_candidates": top_names,
            "top_3_distances": [round(d, 4) for d in all_distances]
        })
        
        if not passed_threshold:
            continue
            
        candidates.append(ResolutionCandidate(
            messy_name=record.messy_party_name, # keep original for output tracking
            candidate_master_names=top_names
        ))
        
    return candidates, math_debug_log