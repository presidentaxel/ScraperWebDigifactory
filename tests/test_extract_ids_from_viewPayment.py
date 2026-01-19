"""Tests for extraction of payment refs from viewPayment page."""
import pytest
from src.parse.payment_details import extract_payment_refs_from_view_payment


def test_extract_debit_request_refs_from_link():
    """Test extraction of debit request refs from href links."""
    html = """
    <html>
    <body>
        <h3>Les demandes de prélèvement</h3>
        <table>
            <tr>
                <td>Request 123</td>
                <td><a href="/digi/com/gocardless/viewPaymentRequestInfos?spaceSelect=1&nr=456789">
                    <i class="i-eye-open"></i>
                </a></td>
            </tr>
        </table>
    </body>
    </html>
    """
    result = extract_payment_refs_from_view_payment(html, "https://example.com")
    
    assert "debit_request_refs" in result
    assert len(result["debit_request_refs"]) >= 1
    assert result["debit_request_refs"][0]["request_nr"] == 456789
    assert "details_url" in result["debit_request_refs"][0]


def test_extract_transaction_refs_from_link():
    """Test extraction of transaction refs from href links."""
    html = """
    <html>
    <body>
        <h3>Les transactions</h3>
        <table>
            <tr>
                <td>Transaction 789</td>
                <td><a href="/digi/cfg/modal/ajax/viewTransaction?nr=72647">
                    <i class="i-eye-open"></i>
                </a></td>
            </tr>
        </table>
    </body>
    </html>
    """
    result = extract_payment_refs_from_view_payment(html, "https://example.com")
    
    assert "transaction_refs" in result
    assert len(result["transaction_refs"]) >= 1
    assert result["transaction_refs"][0]["transaction_nr"] == 72647
    assert "details_url" in result["transaction_refs"][0]


def test_extract_from_onclick():
    """Test extraction from onclick attributes."""
    html = """
    <button onclick="openModal('/digi/cfg/modal/ajax/viewTransaction?nr=12345')">
        <i class="i-eye-open"></i>
    </button>
    """
    result = extract_payment_refs_from_view_payment(html, "https://example.com")
    
    assert "transaction_refs" in result
    # Should find transaction_nr from onclick
    assert any(ref.get("transaction_nr") == 12345 for ref in result["transaction_refs"])


def test_deduplication():
    """Test that duplicate refs are deduplicated."""
    html = """
    <a href="/digi/com/gocardless/viewPaymentRequestInfos?nr=999">
        <i class="i-eye-open"></i>
    </a>
    <a href="/digi/com/gocardless/viewPaymentRequestInfos?nr=999">
        <i class="i-eye-open"></i>
    </a>
    """
    result = extract_payment_refs_from_view_payment(html, "https://example.com")
    
    request_nrs = [ref["request_nr"] for ref in result.get("debit_request_refs", [])]
    assert len(request_nrs) == len(set(request_nrs))  # All unique

