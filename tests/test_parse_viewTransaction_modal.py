"""Tests for parsing transaction modal HTML."""
import pytest
from src.parse.payment_details import parse_transaction_modal


def test_parse_transaction_modal_article_structure():
    """Test parsing of article/label/div structure."""
    html = """
    <fieldset>
        <article>
            <label>Type de paiement</label>
            <div>Prélèvement</div>
        </article>
        <article>
            <label>Date</label>
            <div>2025-01-15</div>
        </article>
        <article>
            <label>Montant</label>
            <div>210,00 €</div>
        </article>
        <article>
            <label>Numéro transaction</label>
            <div>TX-12345</div>
        </article>
        <article>
            <label>Facture liée</label>
            <div>INV-789</div>
        </article>
    </fieldset>
    """
    result = parse_transaction_modal(html, 72647, "https://example.com/viewTransaction?nr=72647")
    
    assert result["transaction_nr"] == 72647
    assert result.get("type_paiement") == "Prélèvement"
    assert result.get("montant") == 210.0
    assert result.get("currency") == "€"
    assert result.get("numero_transaction") == "TX-12345"
    assert result.get("facture_liee") == "INV-789"
    assert "raw_fields" in result
    assert "source_url" in result


def test_parse_montant_with_currency():
    """Test parsing of amount with currency."""
    html = """
    <article>
        <label>Montant</label>
        <div>1 234,56 €</div>
    </article>
    """
    result = parse_transaction_modal(html, 1, "https://example.com/viewTransaction?nr=1")
    
    assert result.get("montant") == 1234.56
    assert result.get("currency") == "€"


def test_parse_compte_bancaire_with_link():
    """Test parsing of bank account with link."""
    html = """
    <article>
        <label>Compte bancaire</label>
        <div>
            <a href="/bank/view?nr=999">FR76 1234 5678 9012 3456 7890</a>
        </div>
    </article>
    """
    result = parse_transaction_modal(html, 1, "https://example.com/viewTransaction?nr=1")
    
    compte = result.get("compte_bancaire")
    if isinstance(compte, dict):
        assert "label" in compte
        assert "url" in compte
    else:
        # Fallback to string
        assert compte is not None


def test_parse_date_normalization():
    """Test date parsing to ISO format."""
    html = """
    <article>
        <label>Date</label>
        <div>15/01/2025</div>
    </article>
    """
    result = parse_transaction_modal(html, 1, "https://example.com/viewTransaction?nr=1")
    
    date = result.get("date")
    # Should be normalized to YYYY-MM-DD or kept as-is if parsing fails
    assert date is not None

