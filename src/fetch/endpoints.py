"""URL builders for DigiFactory endpoints."""
from src.config import config


def get_urls_for_nr(nr: int) -> list[str]:
    """Get all 5 URLs for a given nr."""
    base = config.BASE_URL
    return [
        f"{base}/digi/com/cto/view?nr={nr}",
        f"{base}/digi/com/cto/viewLogistic?nr={nr}",
        f"{base}/digi/com/cto/viewPayment?nr={nr}",
        f"{base}/digi/com/cto/viewInfos?nr={nr}",
        f"{base}/digi/com/cto/viewOrders?nr={nr}",
    ]


def get_view_url(nr: int) -> str:
    """Get the main view URL for a given nr."""
    return f"{config.BASE_URL}/digi/com/cto/view?nr={nr}"

