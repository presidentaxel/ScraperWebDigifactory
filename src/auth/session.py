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
        self._last_validation_time: float = 0.0
        self._validation_cache_seconds: float = 30.0  # Cache validation for 30 seconds

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid session, login if needed."""
        if self._session_cookie:
            # Only validate session periodically (not on every call) to reduce overhead
            import time
            time_since_validation = time.time() - self._last_validation_time
            if time_since_validation < self._validation_cache_seconds:
                # Use cached validation result
                return
            
            # Verify session is still valid (with retry on network errors)
            try:
                if await self._is_session_valid():
                    self._last_validation_time = time.time()
                    return
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                # Network errors during validation don't mean session is invalid
                # Just log and continue with existing session
                logger.debug(f"Network error during session validation (assuming valid): {e}")
                self._last_validation_time = time.time()
                return
            
            logger.warning("Session expired, re-authenticating...")

        await self.login()
        import time
        self._last_validation_time = time.time()

    async def check_and_relogin_if_needed(self, response: httpx.Response) -> bool:
        """
        Check if response indicates login needed, and relogin if so.
        Returns True if relogin was attempted and succeeded.
        """
        # Check for double session popup first
        from src.auth.login_detector import is_double_session_popup
        if is_double_session_popup(response.text):
            logger.warning("Detected 'Double session' popup, resetting session...")
            # Invalidate current session
            self._session_cookie = None
            # Clear client cookies
            self.client.cookies.clear()
            try:
                await self.login()
                self._relogin_failed = False
                return True
            except Exception as e:
                logger.error(f"Relogin after double session failed: {e}")
                self._relogin_failed = True
                return False
        
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
        logger.debug(f"Login URL: {config.LOGIN_URL}")

        # Try to login - adjust form data based on actual DigiFactory login form
        # Common field names for DigiFactory
        login_data = {
            "username": config.USERNAME,
            "password": config.PASSWORD,
        }
        
        # Also try alternative field names
        # DigiFactory might use: login, email, user, etc.

        try:
            response = await self._login_request(login_data)
            
            # Extract session cookie from response
            # Method 1: Check response.cookies
            session_cookie = None
            cookies = response.cookies
            if cookies:
                session_cookie = cookies.get("DigifactoryBO")
                if not session_cookie:
                    # Try case variations
                    for key in cookies.keys():
                        if key.lower() == "digifactorybo":
                            session_cookie = cookies.get(key)
                            break
            
            # Method 2: Extract from Set-Cookie headers
            if not session_cookie:
                set_cookie_headers = response.headers.get_list("Set-Cookie")
                if not set_cookie_headers:
                    # Try get_list with different case
                    set_cookie_headers = response.headers.get_list("set-cookie")
                
                for cookie_header in set_cookie_headers:
                    if "DigifactoryBO" in cookie_header or "digifactorybo" in cookie_header.lower():
                        # Extract cookie value
                        parts = cookie_header.split(";")
                        for part in parts:
                            if "=" in part and ("DigifactoryBO" in part or "digifactorybo" in part.lower()):
                                key_value = part.strip().split("=", 1)
                                if len(key_value) == 2:
                                    key, value = key_value
                                    if key.lower() == "digifactorybo":
                                        session_cookie = value
                                        break
                        if session_cookie:
                            break
            
            # Method 3: Check client's cookie jar (httpx stores cookies automatically)
            if not session_cookie:
                # httpx client automatically stores cookies in its jar
                try:
                    # Access cookies from the client's cookie jar
                    jar_cookies = self.client.cookies
                    if jar_cookies:
                        # Try to get the cookie directly by name (httpx.Cookies is dict-like)
                        try:
                            # httpx.Cookies can be accessed like a dict
                            if hasattr(jar_cookies, 'get'):
                                session_cookie = jar_cookies.get("DigifactoryBO")
                            # Or iterate through all cookies
                            if not session_cookie:
                                # Try to access all cookies
                                all_cookies = dict(jar_cookies) if hasattr(jar_cookies, '__iter__') else {}
                                for name, value in all_cookies.items():
                                    if "digifactorybo" in name.lower():
                                        session_cookie = value
                                        break
                        except (KeyError, AttributeError, TypeError) as e:
                            logger.debug(f"Error accessing cookie jar directly: {e}")
                            
                        # Alternative: try to extract from cookie jar's internal structure
                        if not session_cookie and hasattr(jar_cookies, '_cookies'):
                            # Access internal cookie storage
                            for domain_cookies in jar_cookies._cookies.values():
                                for path_cookies in domain_cookies.values():
                                    for name, cookie_obj in path_cookies.items():
                                        if "digifactorybo" in name.lower():
                                            session_cookie = cookie_obj.value if hasattr(cookie_obj, 'value') else str(cookie_obj)
                                            break
                                    if session_cookie:
                                        break
                                if session_cookie:
                                    break
                except Exception as e:
                    logger.debug(f"Error accessing cookie jar: {e}")

            if session_cookie:
                self._session_cookie = f"DigifactoryBO={session_cookie}"
                logger.info("Login successful - session cookie obtained")
            else:
                # Debug: log response details
                logger.error("=" * 60)
                logger.error("LOGIN FAILED: No session cookie found")
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response URL: {response.url}")
                logger.error(f"Response cookies: {dict(cookies) if cookies else 'None'}")
                logger.error(f"Set-Cookie headers: {response.headers.get_list('Set-Cookie')}")
                logger.error("=" * 60)
                logger.error("SOLUTION: Use --cookie-only with a manually extracted cookie")
                logger.error("See TROUBLESHOOTING.md for instructions")
                raise ValueError("No session cookie found in login response. Use --cookie-only with SESSION_COOKIE or check login URL/credentials.")
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
        # httpx client stores cookies automatically in its cookie jar
        # We need to make sure cookies are enabled
        response = await self.client.post(
            config.LOGIN_URL,
            data=login_data,
            follow_redirects=True,
            timeout=config.TIMEOUT,
        )
        response.raise_for_status()
        
        # Check if login was successful by examining the response
        # If we're redirected away from login page, it's likely successful
        final_url = str(response.url)
        if "login" in final_url.lower():
            logger.warning(f"Still on login page after POST: {final_url}")
        
        return response

    async def _is_session_valid(self) -> bool:
        """Check if current session is still valid."""
        if not self._session_cookie:
            return False

        try:
            # Try to access a protected page with short timeout
            test_url = f"{config.BASE_URL}/digi/com/cto/view?nr=1"
            headers = {"Cookie": self._session_cookie}
            response = await self.client.get(
                test_url,
                headers=headers,
                timeout=5,  # Short timeout for validation
                follow_redirects=False,
            )

            # If redirected to login or contains "se connecter", session is invalid
            if response.status_code == 302:
                location = response.headers.get("Location", "")
                if "login" in location.lower():
                    return False

            if response.status_code == 200:
                text = response.text.lower()
                # Check for login page indicators
                if "se connecter" in text or "connexion" in text:
                    # But don't fail if it's just mentioned in the page content
                    # Only fail if it's clearly a login page (has login form)
                    if "name=\"username\"" in text or "name=\"password\"" in text or "id=\"login\"" in text:
                        return False
                return True

            return False
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            # Network errors don't mean session is invalid - re-raise to let caller handle
            logger.debug(f"Network error during session validation: {e}")
            raise
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

