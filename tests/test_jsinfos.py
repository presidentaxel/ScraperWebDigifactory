"""Tests for JSinfos base64 decoding."""
import base64
import json
import pytest
from src.parse.jsinfos import decode_base64_safe, parse_jsinfos


def test_decode_base64_safe():
    """Test base64 decoding with padding."""
    data = {"test": "value"}
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode()).decode()
    
    decoded = decode_base64_safe(encoded)
    assert json.loads(decoded.decode()) == data


def test_decode_base64_without_padding():
    """Test base64 decoding without padding (auto-add)."""
    data = {"test": "value"}
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode()).decode()
    # Remove padding
    encoded_no_pad = encoded.rstrip("=")
    
    decoded = decode_base64_safe(encoded_no_pad)
    assert json.loads(decoded.decode()) == data


def test_parse_jsinfos_with_json():
    """Test parsing JSinfos with JSON content."""
    data = {"config": {"title": "Test"}, "data": {"key": "value"}}
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode()).decode()
    
    html = f'<span class="JSinfos base64">{encoded}</span>'
    result = parse_jsinfos(html)
    
    assert len(result) > 0
    # Check that gmKey is masked if present
    for key, value in result.items():
        if isinstance(value, dict) and "gmKey" in value:
            assert value["gmKey"] == "[MASKED]"


def test_parse_jsinfos_masks_gmkey():
    """Test that gmKey is masked in parsed JSinfos."""
    data = {
        "config": {"title": "Test", "gmKey": "secret-key"},
        "data": {"key": "value"}
    }
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode()).decode()
    
    html = f'<span class="JSinfos base64">{encoded}</span>'
    result = parse_jsinfos(html)
    
    # Find the parsed data
    parsed = None
    for value in result.values():
        if isinstance(value, dict) and "config" in value:
            parsed = value
            break
    
    assert parsed is not None
    assert parsed["config"]["gmKey"] == "[MASKED]"

