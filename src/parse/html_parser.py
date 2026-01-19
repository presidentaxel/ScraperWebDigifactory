"""Parse HTML and extract visible data fields."""
import logging
import re
import hashlib
from typing import Any
from datetime import datetime
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser, Node

from src.parse.jsinfos import parse_jsinfos

logger = logging.getLogger(__name__)


def extract_text_by_selector(parser: HTMLParser, selector: str, default: str = "") -> str:
    """Extract text from first matching element."""
    node = parser.css_first(selector)
    return node.text(strip=True) if node else default


def extract_all_text_by_selector(parser: HTMLParser, selector: str) -> list[str]:
    """Extract text from all matching elements."""
    return [node.text(strip=True) for node in parser.css(selector) if node.text(strip=True)]


def parse_date(date_str: str) -> str | None:
    """Try to parse a date string and return ISO format."""
    if not date_str:
        return None
    # Common date formats in French
    formats = [
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d.%m.%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.isoformat()
        except ValueError:
            continue
    return date_str  # Return as-is if can't parse


def extract_numeric(text: str) -> float | None:
    """Extract numeric value from text (handles French number format)."""
    if not text:
        return None
    # Remove spaces, replace comma with dot
    cleaned = text.replace(" ", "").replace(",", ".")
    # Extract number
    match = re.search(r"[\d.]+", cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def contains_location_vehicule(html_content: str) -> bool:
    """
    Check if HTML contains "Location de véhicule".
    Returns True if at least one condition is met:
    - Contains <h5>Location de véhicule</h5>
    - Contains regex "Location\s+de\s+véhicule" (case-insensitive)
    - Contains "Type de vente (code) = Location_Subscription"
    """
    if not html_content:
        return False

    html_lower = html_content.lower()

    # Check 1: <h5>Location de véhicule</h5>
    if "<h5>location de véhicule</h5>" in html_lower:
        return True

    # Check 2: Regex "Location\s+de\s+véhicule" (case-insensitive)
    if re.search(r"location\s+de\s+véhicule", html_content, re.IGNORECASE):
        return True

    # Check 3: "Type de vente (code) = Location_Subscription"
    if "location_subscription" in html_lower or "type de vente" in html_lower:
        # More specific check
        if re.search(r"type\s+de\s+vente.*location[_-]?subscription", html_lower):
            return True

    return False


def parse_html_pages(
    responses: dict[str, str | None],
    base_url: str,
    gate_passed: bool = True,
) -> dict[str, Any]:
    """
    Parse all HTML pages and extract data.
    Only does full extraction if gate_passed is True.
    """
    from src.parse.basket import extract_basket_lines
    from src.parse.explorer import extract_explorer_links

    data = {
        "pages": {},
        "jsinfos": {},
        "explorer_links": [],
    }

    # Parse each page
    for url, html_content in responses.items():
        if not html_content:
            continue

        page_type = _get_page_type(url)
        parser = HTMLParser(html_content)

        page_result = {
            "url": url,
            "status_code": 200,  # Will be set by caller if available
            "hash": _compute_hash(html_content),
        }

        # Only do full extraction if gate passed
        if gate_passed:
            # Extract JSinfos from this page
            page_jsinfos = parse_jsinfos(html_content)
            if page_jsinfos:
                data["jsinfos"][page_type] = page_jsinfos
                page_result["jsinfos"] = page_jsinfos

            # Extract basket lines (only on view page)
            if page_type == "view":
                basket_lines = extract_basket_lines(html_content)
                if basket_lines:
                    page_result["basket_lines"] = basket_lines
                    data["basket_lines"] = basket_lines

            # Extract explorer links
            explorer_links = extract_explorer_links(html_content, base_url)
            if explorer_links:
                page_result["explorer_links"] = explorer_links
                data["explorer_links"].extend(explorer_links)

            # Extract visible data
            page_data = _extract_page_data(parser, page_type)
            page_result.update(page_data)
        else:
            # Minimal extraction when gate not passed
            page_result["gate_passed"] = False

        data["pages"][page_type] = page_result

    # Deduplicate explorer links
    data["explorer_links"] = sorted(list(set(data["explorer_links"])))

    return data


def _compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _get_page_type(url: str) -> str:
    """Determine page type from URL."""
    if "viewLogistic" in url:
        return "logistic"
    elif "viewPayment" in url:
        return "payment"
    elif "viewInfos" in url:
        return "infos"
    elif "viewOrders" in url:
        return "orders"
    else:
        return "view"


def _extract_page_data(parser: HTMLParser, page_type: str) -> dict[str, Any]:
    """Extract data from a specific page type."""
    data = {}

    # Common extractions (adjust based on actual HTML)
    # Look for common patterns: refs, dates, amounts, client info, etc.

    # Example: Extract reference (BC-xxxx)
    ref = extract_text_by_selector(parser, "span.ref, .ref, [class*='ref']")
    if ref:
        data["ref"] = ref

    # Extract dates (commande, facturation, etc.)
    date_patterns = [
        ("commande", "date-commande, .date-commande"),
        ("facturation", "date-facturation, .date-facturation"),
        ("livraison", "date-livraison, .date-livraison"),
    ]
    for key, selector in date_patterns:
        date_text = extract_text_by_selector(parser, selector)
        if date_text:
            data[key] = parse_date(date_text)

    # Extract amounts (TTC, TVA, ports)
    amount_patterns = [
        ("ttc", "montant-ttc, .ttc, [class*='ttc']"),
        ("tva", "montant-tva, .tva, [class*='tva']"),
        ("ht", "montant-ht, .ht, [class*='ht']"),
        ("port", "port, .port, [class*='port']"),
    ]
    for key, selector in amount_patterns:
        amount_text = extract_text_by_selector(parser, selector)
        if amount_text:
            amount = extract_numeric(amount_text)
            if amount is not None:
                data[key] = amount

    # Extract client info
    client_name = extract_text_by_selector(parser, ".client-name, [class*='client']")
    if client_name:
        data["client_name"] = client_name

    # Extract entity/vehicule info
    entity = extract_text_by_selector(parser, ".entity, [class*='entity']")
    if entity:
        data["entity"] = entity

    vehicule = extract_text_by_selector(parser, ".vehicule, [class*='vehicule']")
    if vehicule:
        data["vehicule"] = vehicule

    # Extract Location de véhicule specific data (on view page)
    if page_type == "view":
        # Extract semaine (week)
        semaine = extract_text_by_selector(parser, ".semaine, [class*='semaine'], [class*='week']")
        if semaine:
            data["semaine"] = semaine

        # Extract véhicule link
        vehicule_link = None
        for link in parser.css("a[href*='vehicles/view']"):
            href = link.attributes.get("href", "")
            if href:
                data["vehicule_link"] = href
                break

        # Extract button links (Contrat initial & Caution, Dernière vente d'abonnement)
        button_links = []
        for link in parser.css("a[href*='nr=']"):
            href = link.attributes.get("href", "")
            text = link.text(strip=True)
            if href and ("contrat" in text.lower() or "caution" in text.lower() or "abonnement" in text.lower()):
                button_links.append({"text": text, "href": href})
        if button_links:
            data["button_links"] = button_links

    # Extract all text content for fallback (can be refined later)
    # This ensures we don't lose data if selectors don't match
    all_text = parser.body.text(separator="\n", strip=True)
    if all_text:
        data["_raw_text"] = all_text[:5000]  # Limit size

    return data

