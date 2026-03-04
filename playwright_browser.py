"""
Browser Pilot - Playwright Browser Manager
Provides browser automation with automatic cookie sync to/from database.

Features:
- Context manager for automatic resource cleanup
- Auto-load cookies from DB on start
- Auto-save cookies to DB on close
- Anti-detection measures
- CDP support via Playwright's CDP protocol
"""
import json
import logging
import re
import time
from typing import List, Dict, Any, Optional, Callable

log = logging.getLogger("browser-pilot.playwright")

# Lazy import to avoid startup penalty if not using browser features
_playwright_module = None


def _get_playwright():
    """Lazy import of playwright to avoid slow startup."""
    global _playwright_module
    if _playwright_module is None:
        try:
            from playwright.sync_api import sync_playwright
            _playwright_module = sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
    return _playwright_module


class PlaywrightBrowser:
    """
    Playwright browser manager with automatic cookie persistence.
    
    Usage:
        with PlaywrightBrowser(site="example.com", account="user1") as browser:
            browser.goto("https://example.com")
            data = browser.evaluate("document.title")
            # Cookies auto-saved on exit
    
    Args:
        site: Domain for cookie storage (e.g., "douyin.com")
        account: Account identifier for multi-account support (default: "default")
        headless: Run browser in headless mode (default: True)
        auto_save_cookies: Auto-save cookies on close (default: True)
        user_agent: Custom user agent (default: realistic Chrome UA)
    """
    
    # Default realistic user agent
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    def __init__(
        self,
        site: str = None,
        account: str = "default",
        headless: bool = True,
        auto_save_cookies: bool = True,
        user_agent: str = None,
    ):
        self.site = site
        self.account = account
        self.headless = headless
        self.auto_save_cookies = auto_save_cookies
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        
        # Playwright objects (initialized in start())
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # Tracking
        self._started = False
        self._response_handlers: List[Callable] = []
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Don't suppress exceptions
    
    def start(self) -> "PlaywrightBrowser":
        """Start browser and load cookies from database."""
        if self._started:
            return self
        
        sync_playwright = _get_playwright()
        self._playwright = sync_playwright().start()
        
        # Launch browser with anti-detection args
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
        
        # Create context with realistic settings
        self.context = self.browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        
        # Inject anti-detection scripts
        self.context.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override navigator.plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Override navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
        """)
        
        # Load cookies from database
        if self.site:
            self._load_cookies_from_db()
        
        # Create page
        self.page = self.context.new_page()
        self._started = True
        
        log.info(f"Playwright browser started (site={self.site}, account={self.account}, headless={self.headless})")
        return self
    
    def _load_cookies_from_db(self):
        """Load cookies from database into browser context."""
        import db
        import cookie_manager
        
        cookies_list = db.load_cookies(self.site, account=self.account)
        if not cookies_list:
            log.debug(f"No cookies found for {self.site} (account={self.account})")
            return 0
        
        # Convert to Playwright format
        pw_cookies = cookie_manager.cookies_to_playwright_format(cookies_list)
        
        # Filter out invalid cookies (must have name and domain)
        valid_cookies = []
        for c in pw_cookies:
            name = c.get("name", "").strip()
            domain = c.get("domain", "").strip()
            if name and domain:
                valid_cookies.append(c)
            else:
                log.debug(f"Skipping invalid cookie: name='{name}', domain='{domain}'")
        
        if valid_cookies:
            self.context.add_cookies(valid_cookies)
            log.info(f"Loaded {len(valid_cookies)} cookies for {self.site}")
        
        return len(valid_cookies)
    
    def save_cookies_to_db(self, site: str = None):
        """Save current browser cookies to database."""
        import db
        import cookie_manager
        
        target_site = site or self.site
        if not target_site:
            log.warning("Cannot save cookies: no site specified")
            return 0
        
        # Get all cookies from context
        pw_cookies = self.context.cookies()
        
        if not pw_cookies:
            log.debug("No cookies to save")
            return 0
        
        # Filter to matching domain
        domain_cookies = []
        for c in pw_cookies:
            cookie_domain = c.get("domain", "").lstrip(".")
            if target_site in cookie_domain or cookie_domain in target_site:
                domain_cookies.append(c)
        
        if not domain_cookies:
            # Save all if no domain match (user explicitly called save)
            domain_cookies = pw_cookies
        
        # Convert to DB format
        db_cookies = cookie_manager.cookies_from_playwright_format(domain_cookies)
        
        # Save to database
        db.save_cookies(
            site=target_site,
            profile="playwright",
            cookies_list=db_cookies,
            user_agent=self.user_agent,
            account=self.account
        )
        
        log.info(f"Saved {len(db_cookies)} cookies for {target_site} (account={self.account})")
        return len(db_cookies)
    
    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000):
        """
        Navigate to URL.
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition - "load", "domcontentloaded", "networkidle", "commit"
            timeout: Timeout in milliseconds
        
        Returns:
            Response object
        """
        return self.page.goto(url, wait_until=wait_until, timeout=timeout)
    
    def snapshot(self) -> Dict:
        """
        Get page content snapshot.
        Returns page title, URL, and text content.
        
        Returns:
            dict: Page snapshot with title, url, and content
        """
        return {
            "title": self.page.title(),
            "url": self.page.url,
            "content": self.page.content()[:5000],  # First 5000 chars of HTML
            "text": self.page.inner_text("body")[:3000] if self.page.query_selector("body") else ""
        }
    
    def evaluate(self, script: str) -> Any:
        """
        Execute JavaScript in the page context.
        
        Args:
            script: JavaScript code to execute
        
        Returns:
            Result of the script execution
        """
        return self.page.evaluate(script)
    
    def screenshot(self, path: str = None, full_page: bool = False) -> bytes:
        """
        Take a screenshot.
        
        Args:
            path: File path to save screenshot (optional)
            full_page: Capture full scrollable page
        
        Returns:
            Screenshot as bytes
        """
        return self.page.screenshot(path=path, full_page=full_page)
    
    def wait_for_timeout(self, timeout: int):
        """Wait for specified milliseconds."""
        self.page.wait_for_timeout(timeout)
    
    def wait_for_selector(self, selector: str, timeout: int = 30000):
        """Wait for element matching selector to appear."""
        return self.page.wait_for_selector(selector, timeout=timeout)
    
    def click(self, selector: str):
        """Click element matching selector."""
        self.page.click(selector)
    
    def fill(self, selector: str, value: str):
        """Fill input element with value."""
        self.page.fill(selector, value)
    
    def content(self) -> str:
        """Get page HTML content."""
        return self.page.content()
    
    def title(self) -> str:
        """Get page title."""
        return self.page.title()
    
    def url(self) -> str:
        """Get current page URL."""
        return self.page.url
    
    def intercept_requests(
        self,
        url_pattern: str,
        timeout: int = 30,
        navigate_to: str = None
    ) -> List[Dict]:
        """
        Capture network requests matching a pattern.
        
        Args:
            url_pattern: Regex pattern to match URLs
            timeout: How long to wait for requests (seconds)
            navigate_to: URL to navigate to (if not already on page)
        
        Returns:
            List of captured request/response pairs
        """
        captured = []
        pattern = re.compile(url_pattern)
        
        def handle_response(response):
            if pattern.search(response.url):
                try:
                    body = response.text() if response.ok else ""
                except Exception:
                    body = ""
                
                captured.append({
                    "url": response.url,
                    "method": response.request.method,
                    "status": response.status,
                    "request_headers": dict(response.request.headers),
                    "response_headers": dict(response.headers),
                    "body": body[:50000] if body else "",  # Truncate large responses
                })
        
        # Register handler
        self.page.on("response", handle_response)
        
        # Navigate if requested
        if navigate_to:
            self.goto(navigate_to)
        
        # Wait for timeout
        self.page.wait_for_timeout(timeout * 1000)
        
        # Unregister handler
        self.page.remove_listener("response", handle_response)
        
        return captured
    
    def close(self):
        """Close browser and save cookies."""
        if not self._started:
            return
        
        # Auto-save cookies before closing
        if self.auto_save_cookies and self.site and self.context:
            try:
                self.save_cookies_to_db()
            except Exception as e:
                log.warning(f"Failed to save cookies on close: {e}")
        
        # Clean up resources
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None
        
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
        
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        
        self._started = False
        log.info("Playwright browser closed")


# ─── Convenience Functions ───


def quick_fetch(url: str, site: str = None, account: str = "default", 
                script: str = None, headless: bool = True) -> Dict:
    """
    Quick one-shot page fetch with optional JS execution.
    
    Args:
        url: URL to fetch
        site: Site for cookie loading/saving
        account: Account identifier
        script: Optional JS to execute (e.g., "document.title")
        headless: Run headless
    
    Returns:
        dict: {"success": bool, "title": str, "url": str, "data": any, "cookies_saved": int}
    """
    result = {
        "success": False,
        "title": "",
        "url": url,
        "data": None,
        "cookies_saved": 0,
    }
    
    try:
        with PlaywrightBrowser(site=site, account=account, headless=headless) as browser:
            browser.goto(url)
            result["title"] = browser.title()
            result["url"] = browser.url()
            
            if script:
                result["data"] = browser.evaluate(script)
            
            result["cookies_saved"] = browser.save_cookies_to_db() if site else 0
            result["success"] = True
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def intercept_api(
    url: str,
    pattern: str,
    site: str = None,
    account: str = "default",
    wait: int = 30,
    headless: bool = False
) -> List[Dict]:
    """
    Navigate to URL and capture API requests matching pattern.
    
    Args:
        url: URL to navigate to
        pattern: Regex pattern to match API URLs
        site: Site for cookie loading/saving
        account: Account identifier
        wait: Seconds to wait for requests
        headless: Run headless (default False to see browser)
    
    Returns:
        List of captured request/response pairs
    """
    with PlaywrightBrowser(site=site, account=account, headless=headless) as browser:
        return browser.intercept_requests(pattern, timeout=wait, navigate_to=url)
