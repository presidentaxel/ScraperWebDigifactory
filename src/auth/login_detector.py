"""Detect login pages and authentication issues."""
import re
import logging

logger = logging.getLogger(__name__)


def is_double_session_popup(response_html: str | None) -> bool:
    """
    Detect if response contains the "Double session" popup.
    This happens when too many concurrent requests create multiple sessions.
    """
    if not response_html:
        return False
    
    html_lower = response_html.lower()
    
    # Check for double session indicators
    double_session_indicators = [
        r'double session',
        r'deuxième session.*active',
        r'session en trop',
        r'quittez et reconnectez',
        r'fermer la session',
    ]
    
    # Need at least 2 indicators to be sure
    matches = sum(1 for pattern in double_session_indicators if re.search(pattern, html_lower, re.IGNORECASE))
    return matches >= 2


def is_login_page(
    response_html: str | None,
    status_code: int,
    final_url: str,
) -> bool:
    """
    Detect if response is a login page.
    Returns True if at least one condition is met:
    - status_code is 302 and Location contains "login"
    - final_url contains "login"
    - HTML contains "se connecter" or "connexion" prominently
    """
    # Check redirect to login
    if status_code == 302:
        return True  # Will check Location header separately
    
    # Check URL
    url_lower = final_url.lower()
    if "login" in url_lower or "connexion" in url_lower:
        return True
    
    # Check HTML content
    if not response_html:
        return False
    
    html_lower = response_html.lower()
    
    # Strong indicators
    login_indicators = [
        r'<title[^>]*>.*connexion.*</title>',
        r'<h1[^>]*>.*se connecter.*</h1>',
        r'<h2[^>]*>.*connexion.*</h2>',
        r'name=["\']username["\']',
        r'name=["\']password["\']',
        r'id=["\']login["\']',
        r'class=["\'][^"\']*login[^"\']*["\']',
    ]
    
    for pattern in login_indicators:
        if re.search(pattern, html_lower, re.IGNORECASE):
            return True
    
    # Weak indicators (need multiple)
    weak_indicators = [
        "se connecter",
        "connexion",
        "identifiant",
        "mot de passe",
    ]
    
    count = sum(1 for indicator in weak_indicators if indicator in html_lower)
    if count >= 2:
        return True
    
    # Check for double session popup (also requires re-authentication)
    if is_double_session_popup(response_html):
        return True
    
    return False

