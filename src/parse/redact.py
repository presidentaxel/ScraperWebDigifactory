"""Redaction module to mask secrets in outputs and logs."""
import re
import json
from typing import Any, Dict, List


def redact_string(text: str) -> str:
    """Redact secrets from a string."""
    if not text:
        return text
    
    # Patterns to redact
    patterns = [
        (r'digiSuiteVars\.websocketAuthToken\s*[:=]\s*["\']([^"\']+)["\']', r'digiSuiteVars.websocketAuthToken = "[REDACTED]"'),
        (r'gmKey["\']?\s*[:=]\s*["\']([^"\']+)["\']', r'gmKey = "[REDACTED]"'),
        (r'access_token["\']?\s*[:=]\s*["\']([^"\']+)["\']', r'access_token = "[REDACTED]"'),
        (r'refresh_token["\']?\s*[:=]\s*["\']([^"\']+)["\']', r'refresh_token = "[REDACTED]"'),
        (r'Authorization["\']?\s*[:=]\s*["\']Bearer\s+([^"\']+)["\']', r'Authorization = "Bearer [REDACTED]"'),
        (r'DigifactoryBO=([^;,\s]+)', r'DigifactoryBO=[REDACTED]'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact secrets from a dictionary."""
    if not isinstance(data, dict):
        return data
    
    redacted = {}
    for key, value in data.items():
        # Skip gmKey entirely or mask it
        if key.lower() in ('gmkey', 'gm_key', 'websocketauthtoken', 'access_token', 'refresh_token'):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [redact_dict(item) if isinstance(item, dict) else redact_string(str(item)) if isinstance(item, str) else item for item in value]
        elif isinstance(value, str):
            redacted[key] = redact_string(value)
        else:
            redacted[key] = value
    
    # Special handling for nested config objects
    if 'config' in redacted and isinstance(redacted['config'], dict):
        if 'gmKey' in redacted['config']:
            redacted['config']['gmKey'] = "[REDACTED]"
    
    return redacted


def redact_json(data: Any) -> Any:
    """Redact secrets from JSON-serializable data."""
    if isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, list):
        return [redact_json(item) for item in data]
    elif isinstance(data, str):
        return redact_string(data)
    else:
        return data

