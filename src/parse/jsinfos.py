"""Extract and decode span.JSinfos.base64 elements."""
import base64
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def decode_base64_safe(data: str) -> bytes:
    """Decode base64 with padding handling."""
    # Add padding if needed
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    try:
        return base64.b64decode(data)
    except Exception as e:
        logger.warning(f"Base64 decode error: {e}")
        raise


def parse_jsinfos(html_content: str) -> dict[str, Any]:
    """
    Extract all span.JSinfos.base64 elements and decode them.
    Masks gmKey if present and stores config.title.
    """
    from selectolax.parser import HTMLParser

    parser = HTMLParser(html_content)
    jsinfos = {}

    # Find all span elements with classes "JSinfos" and "base64"
    for span in parser.css("span.JSinfos.base64"):
        text = span.text(strip=True)
        if not text:
            continue

        try:
            # Decode base64
            decoded = decode_base64_safe(text)
            decoded_str = decoded.decode("utf-8", errors="ignore")

            # Try to parse as JSON if it starts with { or [
            if decoded_str.strip().startswith(("{", "[")):
                try:
                    parsed = json.loads(decoded_str)
                    
                    # Mask gmKey if present
                    if isinstance(parsed, dict):
                        if "gmKey" in parsed:
                            parsed["gmKey"] = "[MASKED]"
                        if "config" in parsed and isinstance(parsed["config"], dict):
                            if "gmKey" in parsed["config"]:
                                parsed["config"]["gmKey"] = "[MASKED]"
                    
                    # Store with title if available
                    title = None
                    if isinstance(parsed, dict):
                        if "config" in parsed and isinstance(parsed["config"], dict):
                            title = parsed["config"].get("title")
                        elif "title" in parsed:
                            title = parsed["title"]
                    
                    # Use title as key if available, otherwise use index
                    if title:
                        key = f"jsinfos_{title}"
                    else:
                        key = f"jsinfos_{len(jsinfos)}"
                    
                    # Ensure unique key
                    if key in jsinfos:
                        key = f"{key}_{len(jsinfos)}"
                    
                    jsinfos[key] = parsed
                except json.JSONDecodeError:
                    # Store as raw string if not valid JSON
                    key = f"jsinfos_raw_{len(jsinfos)}"
                    jsinfos[key] = decoded_str
            else:
                # Store as raw string
                key = f"jsinfos_raw_{len(jsinfos)}"
                jsinfos[key] = decoded_str

        except Exception as e:
            logger.debug(f"Error parsing JSinfos element: {e}")
            continue

    return jsinfos

