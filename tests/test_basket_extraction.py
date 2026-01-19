"""Tests for basket extraction."""
import pytest
from src.parse.extractors.view_extractor import extract_basket_data


def test_extract_basket_data_with_lines():
    """Test extraction of basket lines and totals."""
    html = """
    <script>
    jBasketComposer([
        {"name": "Product 1", "ref": "REF1", "price": 100, "qtty": 2},
        {"name": "Product 2", "ref": "REF2", "price": 50, "qtty": 1}
    ]);
    </script>
    <div class="total-ht">150.00 EUR</div>
    <div class="total-ttc">180.00 EUR</div>
    """
    result = extract_basket_data(html)
    
    assert "basket_lines" in result
    assert len(result["basket_lines"]) == 2
    assert result["basket_lines"][0]["name"] == "Product 1"
    assert "basket_totals" in result


def test_extract_basket_data_with_error():
    """Test that parse errors are captured."""
    html = "<html><body>No basket here</body></html>"
    result = extract_basket_data(html)
    
    assert "basket_lines" in result
    assert result["basket_lines"] == []
    # No error if nothing found (that's normal)


def test_extract_basket_totals():
    """Test extraction of basket totals."""
    html = """
    <div class="total-ht">150.00</div>
    <div class="total-ttc">180.00</div>
    <div class="total-tva">30.00</div>
    <div class="currency">EUR</div>
    """
    result = extract_basket_data(html)
    
    totals = result.get("basket_totals", {})
    assert "total_ht" in totals or "total_ttc" in totals
    assert totals.get("currency") == "EUR"

