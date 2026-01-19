"""Tests for redaction module."""
import pytest
from src.parse.redact import redact_string, redact_dict, redact_json


def test_redact_string_websocket_token():
    """Test redaction of websocketAuthToken."""
    text = 'digiSuiteVars.websocketAuthToken = "secret-token-123"'
    result = redact_string(text)
    assert "[REDACTED]" in result
    assert "secret-token-123" not in result


def test_redact_string_gmkey():
    """Test redaction of gmKey."""
    text = 'gmKey: "secret-key-456"'
    result = redact_string(text)
    assert "[REDACTED]" in result
    assert "secret-key-456" not in result


def test_redact_string_cookie():
    """Test redaction of DigifactoryBO cookie."""
    text = 'Cookie: DigifactoryBO=abc123def456'
    result = redact_string(text)
    assert "[REDACTED]" in result
    assert "abc123def456" not in result


def test_redact_dict_gmkey():
    """Test redaction of gmKey in dict."""
    data = {
        "config": {
            "title": "Test",
            "gmKey": "secret-key"
        },
        "data": {"key": "value"}
    }
    result = redact_dict(data)
    assert result["config"]["gmKey"] == "[REDACTED]"
    assert result["data"]["key"] == "value"  # Other data preserved


def test_redact_dict_nested():
    """Test redaction in nested structures."""
    data = {
        "jsinfos": {
            "page1": {
                "config": {"gmKey": "secret"},
                "data": {"access_token": "token123"}
            }
        }
    }
    result = redact_dict(data)
    assert result["jsinfos"]["page1"]["config"]["gmKey"] == "[REDACTED]"
    # access_token should be redacted in string form
    assert isinstance(result["jsinfos"]["page1"]["data"]["access_token"], str)


def test_redact_json_preserves_structure():
    """Test that redaction preserves JSON structure."""
    data = {
        "nr": 52000,
        "gate_passed": True,
        "pages": {
            "view": {
                "url": "http://example.com",
                "jsinfos": {"config": {"gmKey": "secret"}}
            }
        }
    }
    result = redact_json(data)
    assert result["nr"] == 52000
    assert result["gate_passed"] is True
    assert result["pages"]["view"]["jsinfos"]["config"]["gmKey"] == "[REDACTED]"

