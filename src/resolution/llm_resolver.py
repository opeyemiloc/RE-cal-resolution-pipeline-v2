import os
import json
import time
from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt
from src.core.models import ResolutionCandidate, LLMMatchDecision
from src.resolution.normalizer import normalize_name
from src.core.config import config

@retry(wait=wait_exponential(multiplier=2, min=5, max=60), stop=stop_after_attempt(5))
def _call_gemini_with_retry(client, model_name, prompt):
    # Automatically retries if an exception (like 429 Quota Exceeded) is raised
    return client.models.generate_content(
        model=model_name,
        contents=prompt
    )

def _resolve_with_gemini(candidates: List[ResolutionCandidate]) -> List[LLMMatchDecision]:
    from google import genai
    decisions: List[LLMMatchDecision] = []
    model_name = config['llm'].get('gemini', {}).get('model_name', 'gemini-3.6-flash')
    batch_size = config['llm'].get('gemini', {}).get('batch_size', 5)
    
    # Initialize Gemini Client (automatically picks up GEMINI_API_KEY from environment)
    client = genai.Client()
    
    print(f"\n🧠 Starting LLM Resolution Phase for {len(candidates)} candidates using Gemini ({model_name}) with batch size {batch_size}...")
    
    # Process candidates in batches
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        print(f"   -> Sending batch of {len(batch)} records to Gemini...")
        
        system_prompt = f"""You are a master data analyst processing a batch of ambiguous shipping names. 
For each 'Cleaned Input Name' in the batch, match it to the correct 'Master Account' from its respective candidate list.

RULES:
1. If the input name contains the Master Account name plus extra words (like 'LIMITED', 'PLC', 'NIGERIA'), IT IS A MATCH.
2. If the core entity brand is the same, IT IS A MATCH.
3. If they are different companies, return matched: false.

Output strictly valid JSON matching this exact schema for EACH input, and return the results as a JSON ARRAY of objects:
[
  {json.dumps(LLMMatchDecision.model_json_schema(), indent=4)}
]

Ensure you return EXACTLY ONE decision object for every input provided, in the exact same order they were given. Do NOT include markdown code blocks like ```json."""

        prompt_lines = [system_prompt, "\n\nBATCH INPUT:"]
        for idx, candidate in enumerate(batch):
            clean_messy = normalize_name(candidate.messy_name)
            prompt_lines.append(f"--- Record {idx+1} ---")
            prompt_lines.append(f"Cleaned Input Name: \"{clean_messy}\"")
            prompt_lines.append(f"Master Candidates: {candidate.candidate_master_names}\n")
            
        prompt = "\n".join(prompt_lines)
        
        try:
            response = _call_gemini_with_retry(client, model_name, prompt)
            
            output_text = (response.text or "").strip()
            if output_text.startswith("```json"):
                output_text = output_text[7:]
            if output_text.startswith("```"):
                output_text = output_text[3:]
            if output_text.endswith("```"):
                output_text = output_text[:-3]
                
            data_array = json.loads(output_text.strip())
            
            # Ensure it is a list
            if not isinstance(data_array, list):
                data_array = [data_array]
                
            for idx, item in enumerate(data_array):
                # Map back to the original candidate in the batch
                if idx < len(batch):
                    item['original_messy_name'] = batch[idx].messy_name
                    
                    if 'confidence_score' in item:
                        try:
                            score = float(item['confidence_score'])
                            if 0 < score <= 1.0:
                                item['confidence_score'] = int(score * 100)
                            else:
                                item['confidence_score'] = int(score)
                        except ValueError:
                            item['confidence_score'] = 0
                    else:
                        item['confidence_score'] = 0
                        
                    decision = LLMMatchDecision(**item)
                    decisions.append(decision)
                    
        except Exception as e:
            # If the batch completely fails to parse, fail all records in the batch
            for candidate in batch:
                decisions.append(LLMMatchDecision(
                    original_messy_name=candidate.messy_name, 
                    matched=False, 
                    resolved_master_name=None, 
                    confidence_score=0, 
                    reasoning=f"LLM Batch Error: {str(e)}"
                ))
            
        # Polite baseline delay between batches
        if i + batch_size < len(candidates):
            time.sleep(2)
            
    return decisions

def resolve_candidates(candidates: List[ResolutionCandidate]) -> List[LLMMatchDecision]:
    return _resolve_with_gemini(candidates)