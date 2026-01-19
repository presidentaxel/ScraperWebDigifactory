"""Extractors for payment, logistic, infos, and orders tabs."""
import logging
import re
from typing import Any, Dict
from selectolax.parser import HTMLParser

from src.parse.jsinfos import parse_jsinfos

logger = logging.getLogger(__name__)


def extract_payment_data(html_content: str, base_url: str = "") -> Dict[str, Any]:
    """Extract payment tab data from JSinfos spans (NEW METHOD - JSON-based)."""
    extracted = {}
    
    # Extract payment requests and transactions from JSinfos spans (NEW METHOD)
    if base_url:
        from src.parse.payment_details import extract_payment_data_from_jsinfos
        payment_data = extract_payment_data_from_jsinfos(html_content, base_url)
        
        # Store payment requests and transactions (raw data from JSinfos)
        if payment_data.get("payment_requests"):
            extracted["payment_requests"] = payment_data["payment_requests"]
        if payment_data.get("transactions"):
            extracted["transactions"] = payment_data["transactions"]
        if payment_data.get("debug"):
            extracted["debug"] = payment_data["debug"]
        
        # Also extract traditional JSinfos base64 for other uses
        jsinfos = parse_jsinfos(html_content)
        if jsinfos:
            extracted["jsinfos"] = jsinfos
    
    # Extract invoices (still from HTML)
    parser = HTMLParser(html_content)
    invoices = _extract_list_items(parser, "invoice", ["invoice", "facture"])
    if invoices:
        extracted["invoices"] = invoices
    
    # Payment summary (optional, from HTML)
    payment_summary = {}
    status = _extract_text_by_patterns(parser, [".payment-status", "[class*='payment-status']", "[data-status]"])
    if status:
        payment_summary["status"] = status
    
    total_due = _extract_numeric(parser, [".total-due", "[class*='total-due']", "[data-total-due]"])
    total_paid = _extract_numeric(parser, [".total-paid", "[class*='total-paid']", "[data-total-paid]"])
    balance = _extract_numeric(parser, [".balance", "[class*='balance']", "[data-balance]"])
    
    if total_due is not None:
        payment_summary["total_due"] = total_due
    if total_paid is not None:
        payment_summary["total_paid"] = total_paid
    if balance is not None:
        payment_summary["balance"] = balance
    
    if payment_summary:
        extracted["payment_summary"] = payment_summary
    
    return extracted


def extract_logistic_data(html_content: str) -> Dict[str, Any]:
    """Extract logistic tab data - must return at least minimal structure."""
    parser = HTMLParser(html_content)
    extracted = {}
    
    # Logistic summary (always present, even if empty)
    logistic_summary = {}
    
    # Extract delivery method
    delivery_method = _extract_text_by_patterns(parser, [
        ".delivery-method", "[class*='delivery-method']", "[data-delivery]",
        ".methode-livraison", "[class*='livraison']"
    ])
    if delivery_method:
        logistic_summary["delivery_method"] = delivery_method
    
    # Extract shipping status
    shipping_status = _extract_text_by_patterns(parser, [
        ".shipping-status", "[class*='shipping-status']", "[data-shipping-status]",
        ".statut-livraison", "[class*='statut']"
    ])
    if shipping_status:
        logistic_summary["shipping_status"] = shipping_status
    
    # Extract tracking number if available
    tracking = _extract_text_by_patterns(parser, [
        ".tracking", "[class*='tracking']", "[data-tracking]",
        ".numero-suivi"
    ])
    if tracking:
        logistic_summary["tracking_number"] = tracking
    
    extracted["logistic_summary"] = logistic_summary
    
    # Extract documents (BL, tracking links, etc.)
    documents = []
    for link in parser.css("a[href]"):
        href = link.attributes.get("href", "")
        text = link.text(strip=True) or ""
        href_lower = href.lower()
        text_lower = text.lower()
        
        # Look for document links (PDF, BL, tracking, etc.)
        if any(keyword in href_lower or keyword in text_lower for keyword in [
            ".pdf", "document", "bl", "bon-livraison", "tracking", "suivi", "expedition"
        ]):
            documents.append({
                "url": href,
                "label": text or href,
                "type": _classify_document_link(href, text)
            })
    
    if documents:
        extracted["documents"] = documents
    
    # Extract JSinfos if present
    jsinfos = parse_jsinfos(html_content)
    if jsinfos:
        extracted["jsinfos"] = jsinfos
    
    return extracted


def _classify_document_link(url: str, text: str) -> str:
    """Classify document link type."""
    combined = (url + " " + text).lower()
    if "bl" in combined or "bon-livraison" in combined:
        return "bl"
    elif "tracking" in combined or "suivi" in combined:
        return "tracking"
    elif ".pdf" in combined:
        return "pdf"
    else:
        return "document"


def extract_infos_data(html_content: str) -> Dict[str, Any]:
    """Extract infos tab data, resolving template variables to real values."""
    parser = HTMLParser(html_content)
    extracted = {}
    
    # First, try to extract numeric values from JS/JSON/variables
    resolved_values = _extract_numeric_values_from_js(html_content)
    
    # Extract fields as key-value pairs
    infos_fields = {}
    
    # Look for common patterns: label: value
    # Try to find definition lists, tables, or div pairs
    for dl in parser.css("dl"):
        dt = dl.css_first("dt")
        dd = dl.css_first("dd")
        if dt and dd:
            key = dt.text(strip=True)
            value = dd.text(strip=True)
            if key and value:
                # Try to resolve template variables like {{price(...)}}
                resolved_value = _resolve_template_value(value, resolved_values)
                infos_fields[key] = resolved_value
    
    # Try tables
    for table in parser.css("table"):
        for row in table.css("tr"):
            cells = row.css("td, th")
            if len(cells) >= 2:
                key = cells[0].text(strip=True)
                value = cells[1].text(strip=True)
                if key and value:
                    # Try to resolve template variables
                    resolved_value = _resolve_template_value(value, resolved_values)
                    infos_fields[key] = resolved_value
    
    if infos_fields:
        extracted["infos_fields"] = infos_fields
    
    # Also store raw template expressions if found
    template_vars = _extract_template_variables(html_content)
    if template_vars:
        extracted["template_variables"] = template_vars
    
    # Extract JSinfos if present
    jsinfos = parse_jsinfos(html_content)
    if jsinfos:
        extracted["jsinfos"] = jsinfos
    
    return extracted


def _extract_numeric_values_from_js(html_content: str) -> Dict[str, float]:
    """Extract numeric values from JavaScript variables/JSON in HTML."""
    import re
    values = {}
    
    # Try to find common variable patterns
    patterns = [
        (r"(?:var|let|const)\s+(totaltax|totalTax|total_tax)\s*=\s*([\d.]+)", "totaltax"),
        (r"(?:var|let|const)\s+(totalprice|totalPrice|total_price)\s*=\s*([\d.]+)", "totalprice"),
        (r"(?:var|let|const)\s+(shippingprice|shippingPrice|shipping_price|port)\s*=\s*([\d.]+)", "shippingprice"),
        (r'"totaltax"\s*:\s*([\d.]+)', "totaltax"),
        (r'"totalprice"\s*:\s*([\d.]+)', "totalprice"),
        (r'"shippingprice"\s*:\s*([\d.]+)', "shippingprice"),
        (r"data-total-tax\s*=\s*['\"]([\d.]+)['\"]", "totaltax"),
        (r"data-total-price\s*=\s*['\"]([\d.]+)['\"]", "totalprice"),
        (r"data-shipping-price\s*=\s*['\"]([\d.]+)['\"]", "shippingprice"),
    ]
    
    for pattern, key in patterns:
        matches = re.finditer(pattern, html_content, re.IGNORECASE)
        for match in matches:
            try:
                value = float(match.group(1) if match.groups() else match.group(0))
                if key not in values:  # Keep first match
                    values[key] = value
            except (ValueError, IndexError):
                continue
    
    return values


def _resolve_template_value(value: str, resolved_values: Dict[str, float]) -> str | float:
    """Try to resolve template variables in value, fallback to original."""
    import re
    
    # Check if it's a template like {{price(...)}} or {{totalTax}}
    template_match = re.search(r"\{\{([^}]+)\}\}", value)
    if template_match:
        expr = template_match.group(1).strip()
        
        # Try to extract variable name
        var_match = re.search(r"(totaltax|totalprice|shippingprice)", expr, re.IGNORECASE)
        if var_match:
            var_name = var_match.group(1).lower()
            if var_name in resolved_values:
                return resolved_values[var_name]
        
        # Return original if can't resolve
        return value
    
    # If not a template, try to parse as number
    numeric = _extract_numeric_from_text(value)
    if numeric is not None:
        return numeric
    
    return value


def _extract_template_variables(html_content: str) -> Dict[str, Any]:
    """Extract template variables used in the page."""
    import re
    
    variables = {}
    template_pattern = r"\{\{([^}]+)\}\}"
    
    for match in re.finditer(template_pattern, html_content):
        expr = match.group(1).strip()
        # Extract variable names from expressions
        var_matches = re.findall(r"(totaltax|totalprice|shippingprice|total|price|tax)", expr, re.IGNORECASE)
        for var in var_matches:
            var_lower = var.lower()
            if var_lower not in variables:
                variables[var_lower] = expr
    
    return variables


def extract_orders_data(html_content: str) -> Dict[str, Any]:
    """Extract orders tab data - must return at least minimal structure."""
    parser = HTMLParser(html_content)
    extracted = {}
    
    # Orders summary (always present, even if empty)
    orders_summary = {}
    
    # Try to extract summary fields
    total_orders = _extract_numeric(parser, [".total-orders", "[class*='total-orders']", "[data-total-orders]"])
    if total_orders is not None:
        orders_summary["total_orders"] = total_orders
    
    extracted["orders_summary"] = orders_summary
    
    # Extract purchase lines (similar to basket but for purchases)
    purchase_lines = []
    
    # Method 1: Look for table rows with data attributes
    for row in parser.css("tr[data-line], tr[data-product], .purchase-line, [class*='purchase-line'], [class*='order-line']"):
        line_data = {}
        cells = row.css("td")
        if len(cells) >= 2:
            line_data["name"] = cells[0].text(strip=True) if cells[0] else ""
            if len(cells) > 1:
                line_data["amount"] = _extract_numeric_from_text(cells[1].text(strip=True))
            if len(cells) > 2:
                line_data["quantity"] = _extract_numeric_from_text(cells[2].text(strip=True))
            if len(cells) > 3:
                line_data["date"] = cells[3].text(strip=True) if cells[3] else None
            if line_data.get("name") or line_data.get("amount"):
                purchase_lines.append(line_data)
    
    # Method 2: Look for list items or divs with order data
    if not purchase_lines:
        for item in parser.css("li[data-product], .order-item, [class*='order-item']"):
            line_data = {}
            name = item.css_first(".name, .product-name")
            amount = item.css_first(".amount, .price")
            qty = item.css_first(".quantity, .qty")
            date = item.css_first(".date")
            
            if name:
                line_data["name"] = name.text(strip=True)
            if amount:
                line_data["amount"] = _extract_numeric_from_text(amount.text(strip=True))
            if qty:
                line_data["quantity"] = _extract_numeric_from_text(qty.text(strip=True))
            if date:
                line_data["date"] = date.text(strip=True)
            
            if line_data.get("name") or line_data.get("amount"):
                purchase_lines.append(line_data)
    
    if purchase_lines:
        extracted["purchase_lines"] = purchase_lines
    
    # Extract totals
    totals = {}
    total_amount = _extract_numeric(parser, [".total-amount", "[class*='total-amount']", "[data-total]"])
    if total_amount is not None:
        totals["total"] = total_amount
    
    # Extract margin if available
    margin = _extract_numeric(parser, [".margin", "[class*='margin']", "[data-margin]", ".marge"])
    if margin is not None:
        totals["margin"] = margin
    
    if totals:
        extracted["totals"] = totals
    
    # Extract JSinfos if present
    jsinfos = parse_jsinfos(html_content)
    if jsinfos:
        extracted["jsinfos"] = jsinfos
    
    return extracted


def _extract_text_by_patterns(parser: HTMLParser, selectors: list[str]) -> str:
    """Try multiple selectors to extract text."""
    for selector in selectors:
        node = parser.css_first(selector)
        if node:
            text = node.text(strip=True)
            if text:
                return text
    return ""


def _extract_numeric(parser: HTMLParser, selectors: list[str]) -> float | None:
    """Extract numeric value using multiple selectors."""
    for selector in selectors:
        node = parser.css_first(selector)
        if node:
            text = node.text(strip=True)
            value = _extract_numeric_from_text(text)
            if value is not None:
                return value
    return None


def _extract_numeric_from_text(text: str) -> float | None:
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


def _extract_list_items(parser: HTMLParser, item_type: str, keywords: list[str]) -> list[Dict[str, Any]]:
    """Extract list items (invoices, transactions, etc.)."""
    items = []
    
    # Look for rows or list items containing keywords
    for row in parser.css("tr, li, .item"):
        text = row.text(strip=True).lower()
        if any(keyword in text for keyword in keywords):
            item = {}
            # Try to extract structured data
            cells = row.css("td, .cell")
            if cells:
                item["label"] = cells[0].text(strip=True) if cells[0] else ""
                if len(cells) > 1:
                    item["amount"] = _extract_numeric_from_text(cells[1].text(strip=True))
            else:
                item["label"] = row.text(strip=True)
            
            if item.get("label"):
                items.append(item)
    
    return items

