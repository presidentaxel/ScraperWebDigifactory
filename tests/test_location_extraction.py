"""Tests for location véhicule extraction."""
import pytest
from src.parse.extractors.view_extractor import extract_location_vehicule


def test_extract_location_vehicule_with_label():
    """Test extraction of vehicle label and nr."""
    html = """
    <h5>Location de véhicule</h5>
    <div>
        <a href="/digi/mod-ep/vehicles/view?nr=28953">TOYOTA PRIUS (GK-345-BT)</a>
        <span class="semaine">2025-43</span>
    </div>
    """
    result = extract_location_vehicule(html)
    
    assert "vehicle_label" in result
    assert "TOYOTA" in result["vehicle_label"]
    assert result.get("vehicle_nr") == 28953
    assert result.get("plate") == "GK-345-BT"
    assert result.get("semaine") == "2025-43"


def test_extract_location_vehicule_with_buttons():
    """Test extraction of contract and subscription buttons."""
    html = """
    <h5>Location de véhicule</h5>
    <a href="/digi/com/cto/view?nr=51535">Contrat initial & Caution</a>
    <a href="/digi/com/cto/view?nr=53028">Dernière vente d'abonnement</a>
    """
    result = extract_location_vehicule(html)
    
    assert result.get("contract_cto_nr") == 51535
    assert result.get("last_subscription_cto_nr") == 53028


def test_extract_location_vehicule_minimal():
    """Test extraction with minimal data."""
    html = """
    <h5>Location de véhicule</h5>
    <div>Some content</div>
    """
    result = extract_location_vehicule(html)
    
    # Should return dict even if empty
    assert isinstance(result, dict)

