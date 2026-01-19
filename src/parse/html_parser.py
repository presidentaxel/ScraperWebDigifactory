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


def contains_location_vehicule(html_content: str) -> tuple[bool, dict[str, Any]]:
    """
    Check if HTML contains "Location de véhicule".
    Returns (bool, reason_dict) where reason_dict contains:
    - gate_reason: reason code
    - gate_matched_text: matched text (for dev)
    - gate_match_count: number of matches
    """
    if not html_content:
        return False, {"gate_reason": "empty_html"}

    html_lower = html_content.lower()
    matches = []
    matched_texts = []

    # Check 1: <h5>Location de véhicule</h5>
    if "<h5>location de véhicule</h5>" in html_lower:
        matches.append("h5_tag")
        matched_texts.append("<h5>Location de véhicule</h5>")

    # Check 2: Regex "Location\s+de\s+véhicule" (case-insensitive)
    regex_match = re.search(r"location\s+de\s+véhicule", html_content, re.IGNORECASE)
    if regex_match:
        matches.append("regex")
        matched_texts.append(regex_match.group(0))

    # Check 3: "Type de vente (code) = Location_Subscription"
    if "location_subscription" in html_lower or "type de vente" in html_lower:
        type_match = re.search(r"type\s+de\s+vente.*location[_-]?subscription", html_lower)
        if type_match:
            matches.append("type_code")
            matched_texts.append(type_match.group(0))

    if matches:
        reason = {
            "gate_reason": "location_de_vehicule_found",
            "gate_match_count": len(matches),
            "gate_matched_text": matched_texts[0] if matched_texts else None,  # First match for dev
        }
        return True, reason
    else:
        return False, {
            "gate_reason": "missing_location_de_vehicule",
            "gate_match_count": 0,
        }


def parse_html_pages(
    responses: dict[str, str | None],
    base_url: str,
    gate_passed: bool = True,
    store_debug_snippets: bool = False,
) -> dict[str, Any]:
    """
    Parse all HTML pages and extract data.
    Only does full extraction if gate_passed is True.
    """
    from src.parse.explorer_enhanced import filter_and_tag_explorer_links
    from src.parse.extractors.view_extractor import (
        extract_basket_data,
        extract_location_vehicule,
        extract_sale_header,
    )
    from src.parse.extractors.tabs_extractors import (
        extract_payment_data,
        extract_logistic_data,
        extract_infos_data,
        extract_orders_data,
    )

    data = {
        "pages": {},
        "explorer_links_all": [],
    }

    # Parse each page
    for url, html_content in responses.items():
        if not html_content:
            continue

        page_type = _get_page_type(url)
        parser = HTMLParser(html_content)
        content_length = len(html_content.encode("utf-8"))

        page_result = {
            "url": url,
            "status_code": 200,  # Will be set by caller if available
            "final_url": url,  # Will be updated by caller
            "hash": _compute_hash(html_content),
            "content_length": content_length,
            "extracted": {},
        }

        # Only do full extraction if gate passed
        if gate_passed:
            # Extract JSinfos from this page (stored in extracted, not at root)
            page_jsinfos = parse_jsinfos(html_content)
            if page_jsinfos:
                page_result["extracted"]["jsinfos"] = page_jsinfos

            # Extract data based on page type
            if page_type == "view":
                # Extract basket data (with dev_mode for debug)
                basket_data = extract_basket_data(html_content, dev_mode=store_debug_snippets)
                # Always include basket data, even if empty (for debug info)
                page_result["extracted"]["basket"] = basket_data

                # Extract location véhicule
                location = extract_location_vehicule(html_content)
                if location:
                    page_result["extracted"]["location"] = location

                # Extract sale header
                sale_header = extract_sale_header(html_content)
                if sale_header:
                    page_result["extracted"]["sale_header"] = sale_header

            elif page_type == "payment":
                payment_data = extract_payment_data(html_content, base_url)
                page_result["extracted"] = payment_data

            elif page_type == "logistic":
                logistic_data = extract_logistic_data(html_content)
                page_result["extracted"] = logistic_data

            elif page_type == "infos":
                infos_data = extract_infos_data(html_content)
                page_result["extracted"] = infos_data

            elif page_type == "orders":
                orders_data = extract_orders_data(html_content)
                page_result["extracted"] = orders_data

            # Extract explorer links (filtered and tagged)
            explorer_links = filter_and_tag_explorer_links(html_content, base_url, max_links=200)
            if explorer_links:
                page_result["explorer_links"] = explorer_links
                # Collect URLs for global deduplication
                for link in explorer_links:
                    if isinstance(link, dict) and "url" in link:
                        data["explorer_links_all"].append(link["url"])
                    elif isinstance(link, str):
                        data["explorer_links_all"].append(link)

            # Extract debug snippets if requested (small, controlled)
            if store_debug_snippets:
                snippet = _extract_debug_snippet(html_content)
                if snippet:
                    page_result["extract_debug_snippet"] = snippet
        else:
            # Minimal extraction when gate not passed
            page_result["extracted"] = {"gate_passed": False}

        data["pages"][page_type] = page_result

    # Deduplicate global explorer links
    data["explorer_links_all"] = sorted(list(set(data["explorer_links_all"])))

    return data


def _extract_debug_snippet(html_content: str, max_bytes: int = 3000) -> str | None:
    """Extract a small debug snippet (max 3KB) for debugging."""
    if not html_content:
        return None
    
    # Extract first meaningful content (skip head, scripts, styles)
    parser = HTMLParser(html_content)
    body = parser.body
    if not body:
        return None
    
    # Get text content, limit size
    snippet = body.text(separator=" ", strip=True)
    if len(snippet.encode("utf-8")) > max_bytes:
        snippet = snippet[:max_bytes] + "..."
    
    return snippet


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

    # NO _raw_text by default (too large and mostly menu)
    # Use extract_debug_snippet if needed for debugging

    return data

