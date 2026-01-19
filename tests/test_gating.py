"""Tests for gating logic."""
import pytest
from src.parse.html_parser import contains_location_vehicule


def test_contains_location_vehicule_h5():
    """Test detection via <h5> tag."""
    html = '<html><body><h5>Location de véhicule</h5></body></html>'
    assert contains_location_vehicule(html) is True


def test_contains_location_vehicule_regex():
    """Test detection via regex pattern."""
    html = '<html><body><p>Location de véhicule</p></body></html>'
    assert contains_location_vehicule(html) is True


def test_contains_location_vehicule_case_insensitive():
    """Test case-insensitive detection."""
    html = '<html><body><p>LOCATION DE VÉHICULE</p></body></html>'
    assert contains_location_vehicule(html) is True


def test_contains_location_vehicule_subscription():
    """Test detection via Location_Subscription."""
    html = '<html><body><p>Type de vente (code) = Location_Subscription</p></body></html>'
    assert contains_location_vehicule(html) is True


def test_not_contains_location_vehicule():
    """Test negative case."""
    html = '<html><body><p>Vente normale</p></body></html>'
    assert contains_location_vehicule(html) is False


def test_empty_html():
    """Test empty HTML."""
    assert contains_location_vehicule("") is False
    assert contains_location_vehicule(None) is False

