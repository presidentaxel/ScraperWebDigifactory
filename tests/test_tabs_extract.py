"""Tests for tab extractors (payment, logistic, infos, orders)."""
import pytest
from src.parse.extractors.tabs_extractors import (
    extract_payment_data,
    extract_logistic_data,
    extract_infos_data,
    extract_orders_data,
)


def test_extract_payment_data():
    """Test payment tab extraction."""
    html = """
    <div class="payment-status">Paid</div>
    <div class="total-due">100.00</div>
    <div class="total-paid">100.00</div>
    <div class="balance">0.00</div>
    """
    result = extract_payment_data(html)
    
    assert "payment_summary" in result
    assert result["payment_summary"].get("status") == "Paid"
    assert result["payment_summary"].get("total_due") == 100.0


def test_extract_logistic_data():
    """Test logistic tab extraction."""
    html = """
    <div class="delivery-method">Standard</div>
    <div class="shipping-status">Delivered</div>
    <a href="/documents/bl.pdf">Bon de livraison</a>
    """
    result = extract_logistic_data(html)
    
    assert "logistic_summary" in result
    assert "documents" in result
    assert len(result["documents"]) > 0


def test_extract_infos_data():
    """Test infos tab extraction."""
    html = """
    <dl>
        <dt>Label 1</dt>
        <dd>Value 1</dd>
        <dt>Label 2</dt>
        <dd>Value 2</dd>
    </dl>
    """
    result = extract_infos_data(html)
    
    assert "infos_fields" in result
    assert result["infos_fields"].get("Label 1") == "Value 1"


def test_extract_orders_data():
    """Test orders tab extraction."""
    html = """
    <div class="total-orders">5</div>
    <div class="margin">25.5</div>
    """
    result = extract_orders_data(html)
    
    assert "orders_summary" in result or "margin" in result


def test_extract_empty_tab():
    """Test extraction from empty tab."""
    html = "<html><body>Empty</body></html>"
    result = extract_payment_data(html)
    
    # Should return dict with extracted, even if empty
    assert isinstance(result, dict)
    # Should not have _raw_text
    assert "_raw_text" not in result

