"""Extract explorer links from HTML pages."""
import logging
import re
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)


def extract_explorer_links(html_content: str, base_url: str) -> list[str]:
    """
    Extract all explorer links from HTML:
    - <a href="...">
    - jsinfos="url:'...'" attributes
    - jsinfos="{url:'...'}" attributes
    Returns normalized absolute URLs (deduplicated).
    """
    if not html_content:
        return []

    parser = HTMLParser(html_content)
    links: set[str] = set()

    # Extract <a href="...">
    for link in parser.css("a[href]"):
        href = link.attributes.get("href")
        if href:
            normalized = _normalize_url(href, base_url)
            if normalized:
                links.add(normalized)

    # Extract jsinfos attributes
    # Pattern: jsinfos="url:'...'" or jsinfos="{url:'...'}"
    jsinfos_pattern = r'jsinfos\s*=\s*["\'](?:url:\s*["\']([^"\']+)["\']|url:\s*([^"\']+)|{url:\s*["\']([^"\']+)["\']|{url:\s*([^"\']+))'
    
    for match in re.finditer(jsinfos_pattern, html_content, re.IGNORECASE):
        for group in match.groups():
            if group:
                normalized = _normalize_url(group, base_url)
                if normalized:
                    links.add(normalized)

    # Also check data attributes
    for element in parser.css("[data-url], [data-href]"):
        url = element.attributes.get("data-url") or element.attributes.get("data-href")
        if url:
            normalized = _normalize_url(url, base_url)
            if normalized:
                links.add(normalized)

    return sorted(list(links))


def _normalize_url(url: str, base_url: str) -> str | None:
    """Normalize URL to absolute form."""
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

