"""Extract payment details: GoCardless debit requests and transaction modals from JSinfos spans."""
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)


def extract_payment_data_from_jsinfos(html_content: str, base_url: str) -> Dict[str, Any]:
    """
    Extract payment requests and transactions from JSinfos spans in viewPayment page.
    Only extracts JSinfos that represent tables (have "data": [...]).
    Ignores menu/navigation JSinfos.
    Returns: {
        "payment_requests": [{nr, ordernr, bref, amount, state, paymentid, transactionnr, ...}],
        "transactions": [{nr, ordernr, billnr, date, amount, num, paymentmethodnr, ...}],
        "debug": {
            "source": "JSinfos spans",
            "jsinfos_spans_total": int,
            "parsed_ok": int,
            "parsed_fail": int,
            "tables_found": int,
            "payment_requests_found": int,
            "transactions_found": int,
            "sample_payment_request_keys": [...],
            "sample_transaction_keys": [...]
        }
    }
    """
    parser = HTMLParser(html_content)
    result = {
        "payment_requests": [],
        "transactions": [],
        "debug": {
            "source": "JSinfos spans",
            "jsinfos_spans_total": 0,
            "parsed_ok": 0,
            "parsed_fail": 0,
            "tables_found": 0,
            "payment_requests_found": 0,
            "transactions_found": 0,
            "sample_payment_request_keys": [],
            "sample_transaction_keys": [],
        }
    }
    
    # Find all JSinfos spans (not just base64 ones)
    jsinfos_spans = parser.css("span.JSinfos, span[class*='JSinfos']")
    result["debug"]["jsinfos_spans_total"] = len(jsinfos_spans)
    
    logger.debug(f"[PAYMENT] Found {len(jsinfos_spans)} JSinfos spans total")
    
    # Parse each span's content as JSON
    parsed_data_objects = []
    for span in jsinfos_spans:
        text = span.text(strip=True)
        if not text:
            continue
        
        try:
            # Try to parse as JSON
            data = json.loads(text)
            if isinstance(data, dict):
                parsed_data_objects.append(data)
                result["debug"]["parsed_ok"] += 1
            else:
                result["debug"]["parsed_fail"] += 1
        except (json.JSONDecodeError, ValueError) as e:
            result["debug"]["parsed_fail"] += 1
            logger.debug(f"[PAYMENT] Failed to parse JSinfos span: {str(e)[:100]}")
            continue
    
    logger.info(f"[PAYMENT] jsinfos_spans_total={result['debug']['jsinfos_spans_total']} parsed_ok={result['debug']['parsed_ok']} parsed_fail={result['debug']['parsed_fail']}")
    
    # Filter: only keep JSinfos that represent tables (have "data": [...])
    # Ignore menu/navigation JSinfos (huge arrays like "Sections principales...")
    table_objects = []
    for data_obj in parsed_data_objects:
        # Must have "data" key with list
        if not isinstance(data_obj.get("data"), list):
            continue
        
        data_list = data_obj["data"]
        if not data_list or len(data_list) == 0:
            continue
        
        # Check first item to see if it's a table row (dict with fields)
        first_item = data_list[0] if data_list else None
        if not isinstance(first_item, dict):
            continue
        
        # Skip menu/navigation JSinfos (they often have huge arrays without useful keys)
        # Tables have specific keys we're looking for
        # Menu items typically have different structure (like "sections", "items", etc.)
        # We'll identify by the presence of our target keys
        has_table_keys = any(key in first_item for key in [
            "nr", "ordernr", "mandatnr", "paymentid", "transactionnr", 
            "tocollect", "requestsent", "bref", "state",
            "paymentmethodnr", "date", "amount", "num", "billnr"
        ])
        
        if has_table_keys:
            table_objects.append(data_obj)
            result["debug"]["tables_found"] += 1
    
    # Identify payment requests and transactions from table objects
    for data_obj in table_objects:
        data_list = data_obj.get("data", [])
        if not data_list:
            continue
        
        # Check first item to determine type
        first_item = data_list[0] if data_list else {}
        if not isinstance(first_item, dict):
            continue
        
        # Payment request indicators (check for specific keys)
        has_payment_request_keys = any(key in first_item for key in [
            "mandatnr", "paymentid", "transactionnr", "tocollect", "requestsent", "bref", "state"
        ])
        
        # Transaction indicators (must have all these keys)
        has_transaction_keys = all(key in first_item for key in [
            "paymentmethodnr", "date", "amount", "num"
        ])
        
        # Process payment requests
        if has_payment_request_keys and not has_transaction_keys:
            for item in data_list:
                if isinstance(item, dict) and "nr" in item:
                    # Store item with all its fields
                    payment_request = {
                        "nr": item.get("nr"),
                        "ordernr": item.get("ordernr"),
                        "bref": item.get("bref"),
                        "amount": item.get("amount"),
                        "state": item.get("state"),
                        "paymentid": item.get("paymentid"),
                        "transactionnr": item.get("transactionnr"),
                    }
                    # Keep all other fields as well
                    for key, value in item.items():
                        if key not in payment_request:
                            payment_request[key] = value
                    
                    result["payment_requests"].append(payment_request)
                    
                    # Store sample keys (only once)
                    if not result["debug"]["sample_payment_request_keys"]:
                        result["debug"]["sample_payment_request_keys"] = list(first_item.keys())
        
        # Process transactions
        elif has_transaction_keys:
            for item in data_list:
                if isinstance(item, dict) and "nr" in item:
                    # Store item with all its fields
                    transaction = {
                        "nr": item.get("nr"),
                        "ordernr": item.get("ordernr"),
                        "billnr": item.get("billnr"),
                        "amount": item.get("amount"),
                        "date": item.get("date"),
                        "num": item.get("num"),
                        "paymentmethodnr": item.get("paymentmethodnr"),
                    }
                    # Keep all other fields as well
                    for key, value in item.items():
                        if key not in transaction:
                            transaction[key] = value
                    
                    result["transactions"].append(transaction)
                    
                    # Store sample keys (only once)
                    if not result["debug"]["sample_transaction_keys"]:
                        result["debug"]["sample_transaction_keys"] = list(first_item.keys())
    
    result["debug"]["payment_requests_found"] = len(result["payment_requests"])
    result["debug"]["transactions_found"] = len(result["transactions"])
    
    # Log required information
    first_request_nr = result["payment_requests"][0].get("nr") if result["payment_requests"] else None
    first_transaction_nr = result["transactions"][0].get("nr") if result["transactions"] else None
    
    logger.info(
        f"[PAYMENT] found_requests={result['debug']['payment_requests_found']} "
        f"first_request_nr={first_request_nr}"
    )
    logger.info(
        f"[PAYMENT] found_transactions={result['debug']['transactions_found']} "
        f"first_transaction_nr={first_transaction_nr}"
    )
    
    logger.info(
        f"[PAYMENT] payment_requests_found={result['debug']['payment_requests_found']} "
        f"sample_keys={result['debug']['sample_payment_request_keys']}"
    )
    logger.info(
        f"[PAYMENT] transactions_found={result['debug']['transactions_found']} "
        f"sample_keys={result['debug']['sample_transaction_keys']}"
    )
    
    return result


def parse_gocardless_modal(html_content: str, request_nr: int, details_url: str) -> Dict[str, Any]:
    """
    Parse GoCardless payment request modal HTML.
    Structure: section > fieldset > article > label + div
    Returns: {
        "details": {...},  # structured fields
        "raw_fields": {...}  # label -> value mapping
    }
    """
    parser = HTMLParser(html_content)
    result = {
        "details": {},
        "raw_fields": {},
    }
    
    # Parse section > fieldset > article > label + div structure
    for section in parser.css("section"):
        for fieldset in section.css("fieldset"):
            for article in fieldset.css("article"):
                label = article.css_first("label")
                div = article.css_first("div")
                if label and div:
                    label_text = label.text(strip=True)
                    value = div.text(strip=True)
                    result["raw_fields"][label_text] = value
                    
                    # Also check for links in div
                    link = div.css_first("a[href]")
                    if link:
                        link_url = link.attributes.get("href", "")
                        link_text = link.text(strip=True)
                        if link_url:
                            result["raw_fields"][f"{label_text}_url"] = link_url
                            result["raw_fields"][f"{label_text}_link"] = link_text
    
    # Also check direct fieldset > article (without section)
    for fieldset in parser.css("fieldset"):
        for article in fieldset.css("article"):
            label = article.css_first("label")
            div = article.css_first("div")
            if label and div:
                label_text = label.text(strip=True)
                value = div.text(strip=True)
                if label_text not in result["raw_fields"]:
                    result["raw_fields"][label_text] = value
    
    # Map common fields to structured schema
    mapping = {
        "proprietaire": ["proprietaire", "propriétaire", "owner"],
        "reference_vente": ["reference vente", "référence vente", "ref vente", "cto_nr"],
        "reference_facture": ["reference facture", "référence facture", "ref facture", "invoice"],
        "description": ["description", "desc"],
        "montant_demande": ["montant demande", "montant", "amount", "demande"],
        "montant_rembourse": ["montant remboursé", "remboursé", "refund"],
        "date_creation": ["date création", "date creation", "créé", "created"],
        "date_envoi": ["date envoi", "envoyé", "sent"],
        "date_prevue": ["date prévue", "date prevue", "prévu", "scheduled"],
        "date_realisation": ["date réalisation", "date realisation", "réalisé", "executed"],
        "etat_mandat_prelevement": ["état mandat", "état prélèvement", "mandat", "state"],
        "date_creation_mandat": ["date création mandat", "mandat créé"],
        "reference_mandat": ["référence mandat", "ref mandat", "mandate"],
        "etat_demande_prelevement": ["état demande", "état", "status"],
        "reference_prelevement": ["référence prélèvement", "ref prélèvement", "debit"],
    }
    
    details = {}
    for schema_key, possible_keys in mapping.items():
        for key in possible_keys:
            # Search in raw_fields (case-insensitive)
            for raw_key, raw_value in result["raw_fields"].items():
                if key.lower() in raw_key.lower():
                    # Extract numeric values for amounts
                    if "montant" in schema_key:
                        numeric = _extract_numeric_from_text(str(raw_value))
                        if numeric is not None:
                            details[schema_key] = numeric
                        else:
                            details[schema_key] = raw_value
                    else:
                        details[schema_key] = raw_value
                    break
            if schema_key in details:
                break
    
    result["details"] = details
    return result


def parse_transaction_modal(html_content: str, transaction_nr: int, details_url: str) -> Dict[str, Any]:
    """
    Parse transaction modal HTML (viewTransaction).
    Structure: section > fieldset > article > label + div
    Returns: {
        "type": str,
        "method": str,
        "date": "YYYY-MM-DD",
        "amount": float,
        "currency": "EUR",
        "bank_account_label": str,
        "bank_account_href": str,
        "transaction_id": str,
        "invoice_ref": str,
        "raw_fields": {...}
    }
    """
    parser = HTMLParser(html_content)
    result = {
        "raw_fields": {},
    }
    
    # Parse section > fieldset > article > label + div structure
    for section in parser.css("section"):
        for fieldset in section.css("fieldset"):
            for article in fieldset.css("article"):
                label = article.css_first("label")
                div = article.css_first("div")
                if label and div:
                    label_text = label.text(strip=True)
                    value = div.text(strip=True)
                    result["raw_fields"][label_text] = value
                    
                    # Also check for links in div
                    link = div.css_first("a[href]")
                    if link:
                        link_url = link.attributes.get("href", "")
                        link_text = link.text(strip=True)
                        if link_url:
                            result["raw_fields"][f"{label_text}_url"] = link_url
                            result["raw_fields"][f"{label_text}_link"] = link_text
    
    # Also check direct fieldset > article (without section)
    for fieldset in parser.css("fieldset"):
        for article in fieldset.css("article"):
            label = article.css_first("label")
            div = article.css_first("div")
            if label and div:
                label_text = label.text(strip=True)
                value = div.text(strip=True)
                if label_text not in result["raw_fields"]:
                    result["raw_fields"][label_text] = value
    
    # Map to structured schema
    mapping = {
        "type": ["type de paiement", "type paiement", "type"],
        "method": ["méthode de paiement", "methode paiement", "méthode", "methode"],
        "date": ["date"],
        "amount": ["montant", "amount"],
        "bank_account": ["compte bancaire", "compte", "bank"],
        "transaction_id": ["numéro transaction", "numero transaction", "transaction id", "id transaction", "identifiant", "référence transaction", "ref transaction"],
        "invoice_ref": ["facture liée", "facture liee", "facture", "invoice", "référence facture", "ref facture"],
    }
    
    # Extract structured fields (case-insensitive search)
    for schema_key, possible_keys in mapping.items():
        for key in possible_keys:
            for raw_key, raw_value in result["raw_fields"].items():
                if key.lower() in raw_key.lower():
                    value = raw_value
                    # Special handling for invoice_ref: extract from link text or value
                    if schema_key == "invoice_ref" and isinstance(value, str):
                        # Try to extract invoice reference like "FA-00029069"
                        invoice_match = re.search(r"(FA|INV|FACT)[\s\-]?(\d+)", value, re.IGNORECASE)
                        if invoice_match:
                            result[schema_key] = f"{invoice_match.group(1)}-{invoice_match.group(2)}"
                        else:
                            result[schema_key] = value
                    else:
                        result[schema_key] = value
                    break
            if schema_key in result:
                break
    
    # Normalize amount: convert "210,00 €" -> 210.00, currency="EUR"
    if "amount" in result:
        amount_str = str(result["amount"])
        # Extract currency
        currency_match = re.search(r"([€$£]|EUR|USD|GBP)", amount_str)
        result["currency"] = currency_match.group(1) if currency_match else "EUR"
        if result["currency"] == "€":
            result["currency"] = "EUR"
        
        # Extract numeric value
        numeric = _extract_numeric_from_text(amount_str)
        if numeric is not None:
            result["amount"] = numeric
    else:
        result["currency"] = "EUR"
    
    # Normalize bank_account: extract label and href separately
    bank_account_label = None
    bank_account_href = None
    
    for key in result["raw_fields"]:
        if "compte" in key.lower() and "bancaire" in key.lower():
            bank_account_label = result["raw_fields"][key]
            if f"{key}_url" in result["raw_fields"]:
                bank_account_href = result["raw_fields"][f"{key}_url"]
            break
    
    if bank_account_label:
        result["bank_account_label"] = bank_account_label
    if bank_account_href:
        result["bank_account_href"] = bank_account_href
    
    # Normalize date: try to parse YYYY-MM-DD
    if "date" in result:
        date_str = result["date"]
        parsed_date = _parse_date_to_iso(date_str)
        if parsed_date:
            result["date"] = parsed_date
    
    return result


def _extract_numeric_from_text(text: str) -> Optional[float]:
    """Extract numeric value from text."""
    if not text:
        return None
    cleaned = text.replace(" ", "").replace(",", ".").replace("€", "").replace("$", "").replace("£", "").strip()
    match = re.search(r"[\d.]+", cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def _parse_date_to_iso(date_str: str) -> Optional[str]:
    """Try to parse date string to YYYY-MM-DD format."""
    if not date_str:
        return None
    
    # Common patterns: DD/MM/YYYY, YYYY-MM-DD, etc.
    patterns = [
        (r"(\d{4})-(\d{2})-(\d{2})", lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
        (r"(\d{2})/(\d{2})/(\d{4})", lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
        (r"(\d{2})\.(\d{2})\.(\d{4})", lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
    ]
    
    for pattern, formatter in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                return formatter(match)
            except (ValueError, IndexError):
                continue
    
    return None
