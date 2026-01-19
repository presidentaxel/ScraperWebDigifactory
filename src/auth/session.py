"""Session management with automatic login and cookie persistence."""
import logging
import asyncio
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import config
from src.auth.login_detector import is_login_page

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages authentication session with automatic refresh."""

    def __init__(self, client: httpx.AsyncClient, cookie_only: bool = False, login_only: bool = False):
        self.client = client
        self._session_cookie: Optional[str] = None
        self.cookie_only = cookie_only
        self.login_only = login_only
        self._relogin_failed = False

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid session, login if needed."""
        if self._session_cookie:
            # Verify session is still valid
            if await self._is_session_valid():
                return
            logger.warning("Session expired, re-authenticating...")

        await self.login()

    async def check_and_relogin_if_needed(self, response: httpx.Response) -> bool:
        """
        Check if response indicates login needed, and relogin if so.
        Returns True if relogin was attempted and succeeded.
        """
        # Check if it's a login page
        if is_login_page(response.text, response.status_code, str(response.url)):
            logger.warning("Detected login page, attempting relogin...")
            try:
                await self.login()
                self._relogin_failed = False
                return True
            except Exception as e:
                logger.error(f"Relogin failed: {e}")
                self._relogin_failed = True
                return False
        return False

    async def login(self) -> None:
        """Perform login and store session cookie."""
        # Cookie-only mode: only use cookie, never login
        if self.cookie_only:
            if not config.SESSION_COOKIE:
                raise ValueError("cookie-only mode requires SESSION_COOKIE")
            self._session_cookie = config.SESSION_COOKIE
            logger.info("Using provided session cookie (cookie-only mode)")
            return
        
        # Login-only mode: ignore cookie, always login
        if self.login_only:
            if not config.USERNAME or not config.PASSWORD:
                raise ValueError("login-only mode requires USERNAME/PASSWORD")
            # Force login even if cookie exists
            pass
        elif config.SESSION_COOKIE:
            # Use provided cookie if available
            self._session_cookie = config.SESSION_COOKIE
            logger.info("Using provided session cookie")
            return

        if not config.USERNAME or not config.PASSWORD:
            raise ValueError("Either SESSION_COOKIE or USERNAME/PASSWORD must be provided")

        logger.info(f"Logging in as {config.USERNAME}...")

        # Try to login - adjust form data based on actual DigiFactory login form
        login_data = {
            "username": config.USERNAME,
            "password": config.PASSWORD,
        }

        try:
            response = await self._login_request(login_data)
            # Extract session cookie from response
            cookies = response.cookies
            session_cookie = cookies.get("DigifactoryBO")
            if not session_cookie:
                # Try to extract from Set-Cookie header
                for cookie in response.headers.get_list("Set-Cookie", []):
                    if "DigifactoryBO" in cookie:
                        session_cookie = cookie.split("DigifactoryBO=")[1].split(";")[0]
                        break

            if session_cookie:
                self._session_cookie = f"DigifactoryBO={session_cookie}"
                logger.info("Login successful")
            else:
                raise ValueError("No session cookie found in login response")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def _login_request(self, login_data: dict) -> httpx.Response:
        """Make login request with retries."""
        response = await self.client.post(
            config.LOGIN_URL,
            data=login_data,
            follow_redirects=True,
            timeout=config.TIMEOUT,
        )
        response.raise_for_status()
        return response

    async def _is_session_valid(self) -> bool:
        """Check if current session is still valid."""
        if not self._session_cookie:
            return False

        try:
            # Try to access a protected page
            test_url = f"{config.BASE_URL}/digi/com/cto/view?nr=1"
            headers = {"Cookie": self._session_cookie}
            response = await self.client.get(
                test_url,
                headers=headers,
                timeout=5,
                follow_redirects=False,
            )

            # If redirected to login or contains "se connecter", session is invalid
            if response.status_code == 302:
                location = response.headers.get("Location", "")
                if "login" in location.lower():
                    return False

            if response.status_code == 200:
                text = response.text.lower()
                if "se connecter" in text or "connexion" in text:
                    return False
                return True

            return False
        except Exception as e:
            logger.debug(f"Session validation error: {e}")
            return False

    def get_cookie_header(self) -> str:
        """Get the session cookie header value."""
        if not self._session_cookie:
            raise RuntimeError("Not authenticated. Call ensure_authenticated() first.")
        return self._session_cookie

    def is_authenticated(self) -> bool:
        """Check if we have a session cookie."""
        return self._session_cookie is not None

