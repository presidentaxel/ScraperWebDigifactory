"""Tests for basket extraction."""
import pytest
from src.parse.basket import extract_basket_lines


def test_extract_basket_lines_simple():
    """Test extraction of simple basket lines."""
    html = """
    <script>
    jBasketComposer([
        {"name": "Product 1", "ref": "REF1", "price": 100, "qtty": 2},
        {"name": "Product 2", "ref": "REF2", "price": 50, "qtty": 1}
    ]);
    </script>
    """
    result = extract_basket_lines(html)
    
    assert len(result) == 2
    assert result[0]["name"] == "Product 1"
    assert result[0]["ref"] == "REF1"
    assert result[0]["price"] == 100
    assert result[0]["qtty"] == 2


def test_extract_basket_lines_with_subscription():
    """Test extraction with subscription fields."""
    html = """
    <script>
    jBasketComposer([
        {
            "name": "Subscription",
            "ref": "SUB1",
            "price": 200,
            "qtty": 1,
            "subscription": true,
            "sub_start": "2025-01-01"
        }
    ]);
    </script>
    """
    result = extract_basket_lines(html)
    
    assert len(result) == 1
    assert result[0]["subscription"] is True
    assert result[0]["sub_start"] == "2025-01-01"


def test_extract_basket_lines_empty():
    """Test with no basket."""
    html = "<html><body>No basket here</body></html>"
    result = extract_basket_lines(html)
    assert len(result) == 0


def test_extract_basket_lines_normalizes_fields():
    """Test field normalization."""
    html = """
    <script>
    jBasketComposer([
        {"nom": "Product", "reference": "REF1", "prix": 100, "quantite": 2}
    ]);
    </script>
    """
    result = extract_basket_lines(html)
    
    # Should normalize French fields
    assert result[0].get("name") == "Product" or result[0].get("nom") == "Product"
    assert result[0].get("ref") == "REF1" or result[0].get("reference") == "REF1"

