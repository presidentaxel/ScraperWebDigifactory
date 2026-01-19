"""Extract basket data from jBasketComposer JavaScript calls."""
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def extract_basket_lines(html_content: str) -> list[dict[str, Any]]:
    """
    Extract basket lines from jBasketComposer( JavaScript call.
    Looks for pattern: jBasketComposer([ {...}, {...} ])
    """
    if not html_content:
        return []

    # Pattern to find jBasketComposer calls
    # Matches: jBasketComposer([...]) or jBasketComposer({...})
    pattern = r"jBasketComposer\s*\(\s*(\[[^\]]+\]|\{[^\}]+\})\s*\)"
    
    matches = re.finditer(pattern, html_content, re.DOTALL | re.IGNORECASE)
    basket_lines = []

    for match in matches:
        try:
            # Extract the JSON-like content
            json_str = match.group(1)
            
            # Try to parse as JSON
            try:
                parsed = json.loads(json_str)
                
                # If it's a list, extract items
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            basket_lines.append(_normalize_basket_item(item))
                # If it's a dict, check for items/lines array
                elif isinstance(parsed, dict):
                    if "items" in parsed and isinstance(parsed["items"], list):
                        for item in parsed["items"]:
                            if isinstance(item, dict):
                                basket_lines.append(_normalize_basket_item(item))
                    elif "lines" in parsed and isinstance(parsed["lines"], list):
                        for item in parsed["lines"]:
                            if isinstance(item, dict):
                                basket_lines.append(_normalize_basket_item(item))
                    else:
                        # Single item
                        basket_lines.append(_normalize_basket_item(parsed))
                        
            except json.JSONDecodeError:
                # Try to extract array items manually
                logger.debug(f"Could not parse JSON from jBasketComposer: {json_str[:100]}")
                continue
                
        except Exception as e:
            logger.debug(f"Error extracting basket line: {e}")
            continue

    return basket_lines


def _normalize_basket_item(item: dict) -> dict[str, Any]:
    """Normalize basket item to standard format."""
    normalized = {}
    
    # Common fields
    field_mapping = {
        "name": ["name", "nom", "label", "libelle"],
        "ref": ["ref", "reference", "code", "sku"],
        "price": ["price", "prix", "amount", "montant"],
        "qtty": ["qtty", "quantity", "qty", "quantite"],
        "tax": ["tax", "tva", "vat"],
        "rate": ["rate", "taux", "tax_rate"],
        "subscription": ["subscription", "abonnement"],
        "sub_start": ["sub_start", "subscription_start", "debut_abonnement"],
        "total": ["total", "total_ht", "total_ttc"],
    }
    
    for standard_key, possible_keys in field_mapping.items():
        for key in possible_keys:
            if key in item:
                normalized[standard_key] = item[key]
                break
    
    # Include all other fields
    for key, value in item.items():
        if key not in normalized:
            normalized[key] = value
    
    return normalized

