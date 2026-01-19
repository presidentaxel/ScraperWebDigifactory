"""Extractors for the main view page."""
import logging
import re
from typing import Any, Dict, Optional
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)


def extract_basket_data(html_content: str, dev_mode: bool = False) -> Dict[str, Any]:
    """
    Extract basket lines and totals from view page.
    Returns: {basket_lines: [], basket_totals: {}, debug: {...} if empty}
    """
    from src.parse.basket import extract_basket_lines
    import re
    
    result = {
        "basket_lines": [],
        "basket_totals": {},
    }
    
    # Debug info when basket is empty
    debug = {}
    
    # Check if jBasketComposer script exists
    basket_script_pattern = r"jBasketComposer\s*\("
    found_script = bool(re.search(basket_script_pattern, html_content, re.IGNORECASE))
    debug["found_basket_script"] = found_script
    
    if found_script:
        # Extract script excerpt for debugging
        matches = list(re.finditer(basket_script_pattern, html_content, re.IGNORECASE))
        if matches:
            match = matches[0]
            start = max(0, match.start() - 100)
            end = min(len(html_content), match.end() + 1000)
            script_excerpt = html_content[start:end]
            debug["basket_script_len"] = len(script_excerpt)
            
            if dev_mode:
                # Store raw excerpt (max 500 chars) in DEV mode only
                debug["basket_raw_excerpt"] = script_excerpt[:500] if len(script_excerpt) > 500 else script_excerpt
    else:
        debug["basket_script_len"] = 0
    
    try:
        basket_lines = extract_basket_lines(html_content)
        result["basket_lines"] = basket_lines
        
        # If empty, add debug info
        if not basket_lines:
            result["debug"] = debug
        
        # Try to extract totals from basket lines or HTML
        totals = _extract_basket_totals(html_content, basket_lines)
        if totals:
            result["basket_totals"] = totals
            
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Basket extraction error: {error_msg}")
        result["basket_parse_error"] = error_msg
        debug["basket_parse_error"] = error_msg
        result["debug"] = debug
    
    return result


def _extract_basket_totals(html_content: str, basket_lines: list) -> Dict[str, Any]:
    """Extract basket totals from HTML or calculate from lines."""
    totals = {}
    parser = HTMLParser(html_content)
    
    # Try to find totals in HTML
    total_ht = extract_numeric_from_text(extract_text_by_selector(parser, ".total-ht, [class*='total-ht'], [class*='total_ht']"))
    total_ttc = extract_numeric_from_text(extract_text_by_selector(parser, ".total-ttc, [class*='total-ttc'], [class*='total_ttc']"))
    total_tax = extract_numeric_from_text(extract_text_by_selector(parser, ".total-tva, [class*='total-tva'], [class*='total_tva']"))
    
    # If not found, try to calculate from basket lines
    if not total_ht and basket_lines:
        total_ht = sum(line.get("price", 0) * line.get("qtty", 0) for line in basket_lines)
    
    if total_ht is not None:
        totals["total_ht"] = total_ht
    if total_ttc is not None:
        totals["total_ttc"] = total_ttc
    if total_tax is not None:
        totals["total_tax"] = total_tax
    
    # Try to find currency
    currency_text = extract_text_by_selector(parser, ".currency, [class*='currency'], [class*='devise']")
    if currency_text:
        totals["currency"] = currency_text.strip()
    else:
        totals["currency"] = "EUR"  # Default
    
    return totals


def extract_location_vehicule(html_content: str) -> Dict[str, Any]:
    """
    Extract Location de véhicule data from view page.
    Returns: {vehicle_label, vehicle_nr, plate, semaine, contract_cto_nr, last_subscription_cto_nr}
    """
    parser = HTMLParser(html_content)
    location = {}
    
    # Extract vehicle label (look for text near "Location de véhicule" heading)
    # Try to find vehicle info after <h5>Location de véhicule</h5>
    h5_location = parser.css_first("h5")
    if h5_location and "location" in h5_location.text(strip=True).lower() and "véhicule" in h5_location.text(strip=True).lower():
        # Look for vehicle info in the next elements
        parent = h5_location.parent
        if parent:
            # Search for vehicle label in nearby text
            vehicle_text = parent.text(separator=" ", strip=True)
            # Try to extract vehicle label pattern (e.g., "TOYOTA PRIUS (GK-345-BT)")
            vehicle_match = re.search(r"([A-Z\s]+\([A-Z0-9\-]+\))", vehicle_text)
            if vehicle_match:
                location["vehicle_label"] = vehicle_match.group(1).strip()
    
    # Extract vehicle link and nr
    for link in parser.css("a[href*='vehicles/view']"):
        href = link.attributes.get("href", "")
        if href:
            # Extract nr from URL: vehicles/view?nr=28953
            nr_match = re.search(r"nr=(\d+)", href)
            if nr_match:
                location["vehicle_nr"] = int(nr_match.group(1))
            
            # Extract vehicle label from link text
            link_text = link.text(strip=True)
            if link_text and not location.get("vehicle_label"):
                location["vehicle_label"] = link_text
            break
    
    # Extract plate from vehicle_label if present
    if location.get("vehicle_label"):
        plate_match = re.search(r"\(([A-Z0-9\-]+)\)", location["vehicle_label"])
        if plate_match:
            location["plate"] = plate_match.group(1)
    
    # Extract semaine (week)
    semaine = extract_text_by_selector(parser, ".semaine, [class*='semaine'], [class*='week'], [data-semaine]")
    if not semaine:
        # Try to find in text near "semaine" or "week"
        body_text = parser.body.text()
        semaine_match = re.search(r"(?:semaine|week)[\s:]+([0-9]{4}-[0-9]{1,2})", body_text, re.IGNORECASE)
        if semaine_match:
            semaine = semaine_match.group(1)
    if semaine:
        location["semaine"] = semaine.strip()
    
    # Extract contract_cto_nr from "Contrat initial & Caution" button
    for link in parser.css("a[href*='nr=']"):
        href = link.attributes.get("href", "")
        text = link.text(strip=True)
        if href and ("contrat" in text.lower() and "caution" in text.lower()):
            nr_match = re.search(r"nr=(\d+)", href)
            if nr_match:
                location["contract_cto_nr"] = int(nr_match.group(1))
            break
    
    # Extract last_subscription_cto_nr from "Dernière vente d'abonnement" button
    for link in parser.css("a[href*='nr=']"):
        href = link.attributes.get("href", "")
        text = link.text(strip=True)
        if href and ("dernière" in text.lower() or "derniere" in text.lower()) and "abonnement" in text.lower():
            nr_match = re.search(r"nr=(\d+)", href)
            if nr_match:
                location["last_subscription_cto_nr"] = int(nr_match.group(1))
            break
    
    return location


def extract_sale_header(html_content: str) -> Dict[str, Any]:
    """
    Extract sale header information (type_code, status, created_at, contact_nr, biz_nr).
    Returns minimal dict with what can be found.
    """
    parser = HTMLParser(html_content)
    header = {}
    
    # Extract type_code (Type de vente)
    type_code = extract_text_by_selector(parser, "[data-type-code], .type-code, [class*='type-code']")
    if not type_code:
        # Try to find in text
        body_text = parser.body.text()
        type_match = re.search(r"type\s+de\s+vente[:\s]+([A-Z_]+)", body_text, re.IGNORECASE)
        if type_match:
            type_code = type_match.group(1)
    if type_code:
        header["type_code"] = type_code.strip()
    
    # Extract status
    status = extract_text_by_selector(parser, "[data-status], .status, [class*='status']")
    if status:
        header["status"] = status.strip()
    
    # Extract created_at (date de création)
    created_at = extract_text_by_selector(parser, "[data-created-at], .created-at, [class*='created-at'], [class*='date-creation']")
    if created_at:
        from src.parse.html_parser import parse_date
        header["created_at"] = parse_date(created_at)
    
    # Extract contact_nr from links
    for link in parser.css("a[href*='ct/view'], a[href*='crm/ct']"):
        href = link.attributes.get("href", "")
        nr_match = re.search(r"nr=(\d+)", href)
        if nr_match:
            header["contact_nr"] = int(nr_match.group(1))
            break
    
    # Extract biz_nr from links
    for link in parser.css("a[href*='biz/view'], a[href*='com/biz']"):
        href = link.attributes.get("href", "")
        nr_match = re.search(r"nr=(\d+)", href)
        if nr_match:
            header["biz_nr"] = int(nr_match.group(1))
            break
    
    return header


def extract_text_by_selector(parser: HTMLParser, selector: str, default: str = "") -> str:
    """Extract text from first matching element."""
    node = parser.css_first(selector)
    return node.text(strip=True) if node else default


def extract_numeric_from_text(text: str) -> Optional[float]:
    """Extract numeric value from text."""
    if not text:
        return None
    cleaned = text.replace(" ", "").replace(",", ".")
    match = re.search(r"[\d.]+", cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None

