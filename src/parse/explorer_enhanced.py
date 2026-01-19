"""Enhanced explorer links extraction with normalization, filtering, and tagging."""
import re
from typing import List, Dict
from urllib.parse import urljoin, urlparse, parse_qs

from src.parse.explorer import extract_explorer_links
from src.config import config


def tag_link_type(url: str) -> str:
    """Tag link type based on URL pattern."""
    url_lower = url.lower()
    
    if "/cto/view" in url_lower or "/cto/viewpayment" in url_lower or "/cto/viewlogistic" in url_lower:
        return "tab"
    elif "/ct/view" in url_lower or "/crm/ct" in url_lower:
        return "contact"
    elif "/vehicles/view" in url_lower or "/mod-ep/vehicles" in url_lower:
        return "vehicle"
    elif "/biz/view" in url_lower or "/com/biz" in url_lower:
        return "biz"
    elif url_lower.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
        return "doc"
    elif "logout" in url_lower or "quit" in url_lower or "del" in url_lower:
        return "dangerous"
    else:
        return "other"


def is_dangerous_link(url: str) -> bool:
    """Check if link is dangerous (logout, delete, etc.)."""
    url_lower = url.lower()
    
    # Logout patterns
    if "logout" in url_lower or "quit=1" in url_lower:
        return True
    
    # Delete patterns
    if "/del" in url_lower or "xact:'del'" in url_lower or "action=delete" in url_lower:
        return True
    
    # Other dangerous patterns
    if "destroy" in url_lower or "remove" in url_lower:
        return True
    
    return False


def is_heavy_download(url: str) -> bool:
    """Check if link is a heavy download (PDF, etc.)."""
    url_lower = url.lower()
    return url_lower.endswith(('.pdf', '.zip', '.tar', '.gz', '.rar'))


def filter_and_tag_explorer_links(
    html_content: str,
    base_url: str,
    max_links: int = 200,
) -> List[Dict[str, str]]:
    """
    Extract, normalize, filter, and tag explorer links.
    Returns list of dicts with url, type, reason (if dangerous), scope, and notes.
    Deduplicates links and canonicalizes URLs.
    """
    # Extract raw links
    raw_links = extract_explorer_links(html_content, base_url)
    
    # Canonicalize and deduplicate by URL
    seen = set()
    unique_links = []
    for link in raw_links:
        # Canonicalize URL (remove duplicate paths, normalize)
        canonical = _canonicalize_url(link, base_url)
        if canonical and canonical not in seen:
            seen.add(canonical)
            unique_links.append(canonical)
    
    # Filter and tag
    filtered = []
    for url in unique_links[:max_links]:
        link_type = tag_link_type(url)
        scope = _extract_scope(url)
        
        # Handle dangerous links (note but don't skip - user wants to see them)
        if is_dangerous_link(url):
            filtered.append({
                "url": url,
                "type": "dangerous",
                "scope": scope,
                "reason": "dangerous_action",  # logout, delete, etc.
                "noted": True,
            })
            continue
        
        # Note heavy downloads but include them
        notes = []
        if is_heavy_download(url):
            notes.append("heavy_download")
        
        filtered.append({
            "url": url,
            "type": link_type,
            "scope": scope,
            "noted": len(notes) > 0,
            "notes": notes if notes else None,
        })
    
    return filtered


def _canonicalize_url(url: str, base_url: str) -> str | None:
    """Canonicalize URL to remove functional duplicates."""
    normalized = _normalize_url(url, base_url)
    if not normalized:
        return None
    
    # Parse URL
    parsed = urlparse(normalized)
    
    # Remove duplicate /digi/ or /com/ in path
    path = parsed.path
    # Replace /digi/com/ with /digi/com/ (single occurrence)
    path = re.sub(r"/digi/digi/", "/digi/", path)
    path = re.sub(r"/com/com/", "/com/", path)
    
    # Reconstruct canonical URL
    canonical = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        canonical += f"?{parsed.query}"
    if parsed.fragment:
        canonical += f"#{parsed.fragment}"
    
    return canonical


def _extract_scope(url: str) -> str:
    """Extract URL scope (digi, com, crm, help, etc.)."""
    url_lower = url.lower()
    if "/digi/" in url_lower:
        return "digi"
    elif "/com/" in url_lower:
        return "com"
    elif "/crm/" in url_lower:
        return "crm"
    elif "/help/" in url_lower or "/doc/" in url_lower:
        return "help"
    else:
        return "other"


def _normalize_url(url: str, base_url: str) -> str | None:
    """Normalize URL to absolute form (from explorer.py)."""
    from urllib.parse import urljoin, urlparse
    
    if not url or url.startswith("#") or url.startswith("javascript:"):
        return None

    # Remove whitespace
    url = url.strip()

    # Make absolute
    if url.startswith("http://") or url.startswith("https://"):
        return url
    elif url.startswith("//"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}:{url}"
    elif url.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{url}"
    else:
        # Relative URL
        return urljoin(base_url, url)


def get_explorer_links_summary(links: List[Dict[str, str]]) -> Dict[str, int]:
    """Get summary statistics of explorer links."""
    summary = {
        "total": len(links),
        "tab": 0,
        "contact": 0,
        "vehicle": 0,
        "biz": 0,
        "doc": 0,
        "dangerous": 0,
        "other": 0,
    }
    
    for link in links:
        link_type = link.get("type", "other")
        if link_type in summary:
            summary[link_type] += 1
    
    return summary

