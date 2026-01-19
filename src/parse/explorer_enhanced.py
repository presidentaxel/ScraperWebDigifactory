"""Enhanced explorer links extraction with normalization, filtering, and tagging."""
import re
from typing import List, Dict
from urllib.parse import urljoin, urlparse, parse_qs

from src.parse.explorer import extract_explorer_links, _normalize_url
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
    Returns list of dicts with url, type, and notes.
    """
    # Extract raw links
    raw_links = extract_explorer_links(html_content, base_url)
    
    # Deduplicate
    seen = set()
    unique_links = []
    for link in raw_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    
    # Filter and tag
    filtered = []
    for url in unique_links[:max_links]:
        link_type = tag_link_type(url)
        
        # Skip dangerous links but note them
        if is_dangerous_link(url):
            filtered.append({
                "url": url,
                "type": "dangerous",
                "noted": True,
                "reason": "dangerous_action",
            })
            continue
        
        # Note heavy downloads but include them
        notes = []
        if is_heavy_download(url):
            notes.append("heavy_download")
        
        filtered.append({
            "url": url,
            "type": link_type,
            "noted": len(notes) > 0,
            "notes": notes if notes else None,
        })
    
    return filtered


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

