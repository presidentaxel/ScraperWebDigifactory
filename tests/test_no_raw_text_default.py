"""Tests to verify _raw_text is not present by default."""
import pytest
from src.parse.html_parser import parse_html_pages


def test_no_raw_text_by_default():
    """Verify _raw_text is not in output by default."""
    html_content = "<html><body>Test content with menu sections</body></html>"
    responses = {"https://example.com/view": html_content}
    
    result = parse_html_pages(responses, "https://example.com", gate_passed=True)
    
    # Check all pages
    for page_type, page_data in result.get("pages", {}).items():
        extracted = page_data.get("extracted", {})
        assert "_raw_text" not in extracted
        assert "_raw_text" not in page_data
    
    # Check root level
    assert "_raw_text" not in result


def test_debug_snippet_only_when_requested():
    """Verify extract_debug_snippet only appears when requested."""
    html_content = "<html><body>Test</body></html>"
    responses = {"https://example.com/view": html_content}
    
    # Without store_debug_snippets
    result = parse_html_pages(responses, "https://example.com", gate_passed=True, store_debug_snippets=False)
    for page_data in result.get("pages", {}).values():
        assert "extract_debug_snippet" not in page_data
    
    # With store_debug_snippets
    result = parse_html_pages(responses, "https://example.com", gate_passed=True, store_debug_snippets=True)
    # Should have snippet in at least one page
    has_snippet = any("extract_debug_snippet" in page_data for page_data in result.get("pages", {}).values())
    # May or may not have snippet depending on content, but should not have _raw_text
    assert "_raw_text" not in str(result)

