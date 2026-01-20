"""HTTP client with retries and error handling."""
import logging
from typing import Optional
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import config
from src.auth.session import SessionManager
from src.fetch.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


def is_retryable_status(response: httpx.Response) -> bool:
    """Check if status code is retryable."""
    return response.status_code in (429, 500, 502, 503, 504)


class FetchClient:
    """HTTP client with rate limiting, retries, and session management."""

    def __init__(self, cookie_only: bool = False, login_only: bool = False):
        # Configure connection pool
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
        )
        
        # httpx automatically manages cookies, but we can access them via client.cookies
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=config.TIMEOUT,
            follow_redirects=False,  # We handle redirects manually to detect login
            limits=limits,
        )
        self.rate_limiter = RateLimiter(config.RATE_PER_DOMAIN)
        self.session_manager = SessionManager(self.client, cookie_only=cookie_only, login_only=login_only)
        self.retry_count = 0
        self.backoff_time_total = 0.0

    async def __aenter__(self):
        await self.session_manager.ensure_authenticated()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def fetch(self, url: str) -> Optional[httpx.Response]:
        """Fetch a URL with rate limiting, retries, and session management."""
        await self.rate_limiter.acquire(url)

        # Ensure authenticated
        await self.session_manager.ensure_authenticated()

        headers = {"Cookie": self.session_manager.get_cookie_header()}

        try:
            response = await self.client.get(url, headers=headers, timeout=config.TIMEOUT)

            # Check for double session popup first (requires session reset)
            from src.auth.login_detector import is_double_session_popup
            if is_double_session_popup(response.text):
                logger.warning(f"Detected 'Double session' popup for {url} - too many concurrent sessions")
                logger.warning("Invalidating current session and re-authenticating...")
                # Invalidate current session
                self.session_manager._session_cookie = None
                # Clear client cookies to force new session
                self.client.cookies.clear()
                # Re-authenticate
                await self.session_manager.ensure_authenticated()
                # Retry with new session
                headers = {"Cookie": self.session_manager.get_cookie_header()}
                response = await self.client.get(url, headers=headers, timeout=config.TIMEOUT)
                # Check again if still double session (shouldn't happen but just in case)
                if is_double_session_popup(response.text):
                    logger.error("Still getting 'Double session' popup after re-authentication")
                    logger.error("Consider reducing CONCURRENCY or RATE_PER_DOMAIN to avoid multiple sessions")
                    raise RuntimeError("Double session popup persists after re-authentication - reduce concurrency")

            # Check for login page (using detector)
            from src.auth.login_detector import is_login_page
            if is_login_page(response.text, response.status_code, str(response.url)):
                logger.warning(f"Detected login page for {url}, attempting relogin...")
                relogin_success = await self.session_manager.check_and_relogin_if_needed(response)
                if relogin_success:
                    # Retry once after re-auth
                    headers = {"Cookie": self.session_manager.get_cookie_header()}
                    response = await self.client.get(url, headers=headers, timeout=config.TIMEOUT)
                    # Check again if still login page
                    if is_login_page(response.text, response.status_code, str(response.url)):
                        logger.error("Still on login page after relogin - authentication may have failed")
                        raise RuntimeError("Authentication failed: still on login page after relogin")
                else:
                    # Relogin failed
                    if self.session_manager._relogin_failed:
                        raise RuntimeError("Authentication failed: relogin unsuccessful")

            # Check for retryable errors
            if is_retryable_status(response):
                response.raise_for_status()

            return response

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Not found is not retryable
                return e.response
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"Network error for {url}: {e}")
            raise

    async def fetch_all(self, urls: list[str]) -> dict[str, Optional[httpx.Response]]:
        """Fetch multiple URLs concurrently."""
        tasks = {url: self.fetch(url) for url in urls}
        results = {}
        for url, task in tasks.items():
            try:
                results[url] = await task
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {e}")
                results[url] = None
        return results

