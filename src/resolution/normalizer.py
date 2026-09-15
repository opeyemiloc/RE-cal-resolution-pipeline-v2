import re

# Pre-compiled abbreviation expansions for performance
_ABBREVIATIONS = [
    (re.compile(r'\bLTD\b'), 'LIMITED'),
    (re.compile(r'\bIND\b'), 'INDUSTRIES'),
    (re.compile(r'\bNIG\b'), 'NIGERIA'),
    (re.compile(r'\bCO\b'), 'COMPANY'),
    (re.compile(r'\bINTL\b'), 'INTERNATIONAL'),
    (re.compile(r'\bCORP\b'), 'CORPORATION'),
    (re.compile(r'\bENT\b'), 'ENTERPRISES'),
    (re.compile(r'\bMFG\b'), 'MANUFACTURING'),
    (re.compile(r'\bDIST\b'), 'DISTRIBUTORS'),
    (re.compile(r'\bGRP\b'), 'GROUP'),
    (re.compile(r'\bTECH\b'), 'TECHNOLOGY'),
    (re.compile(r'\bBROS\b'), 'BROTHERS'),
]

def normalize_name(name: str) -> str:
    """
    Cleans a messy company name for highly accurate mathematical and exact matching.
    """
    if not isinstance(name, str):
        return ""
    if not name:
        return ""
        
    # 1. Uppercase everything
    n = name.upper()
    
    # 2. Standardize symbols and replace punctuation (commas, periods, hyphens, slashes) with space
    n = n.replace("&", " AND ")
    n = n.replace("'", "")
    n = n.replace(".", " ").replace(",", " ").replace("-", " ").replace("/", " ")
    
    # 3. Expand common abbreviations (using word boundaries \b so we don't ruin actual words)
    for pattern, replacement in _ABBREVIATIONS:
        n = pattern.sub(replacement, n)
    
    # 4. Remove extra/double spaces and strip ends
    n = " ".join(n.split())
    
    return n.strip()