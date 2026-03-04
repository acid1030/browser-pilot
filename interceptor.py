"""
Browser Pilot - Network Interceptor
Captures network requests via Playwright's response event system.

Replaces the old Selenium/CDP-based interception with Playwright's
more reliable and comprehensive network capture.
"""
import json
import re
import logging
from typing import List, Dict, Optional

log = logging.getLogger("browser-pilot.interceptor")


def intercept_page(
    page_url: str,
    url_pattern: str,
    wait_seconds: int = 30,
    site: str = None,
    account: str = "default",
    headless: bool = False,
) -> List[Dict]:
    """
    Load a page and intercept network requests matching url_pattern.
    Uses Playwright's response event system for reliable capture.
    
    Args:
        page_url: URL to navigate to
        url_pattern: Regex pattern to match request URLs
        wait_seconds: How long to wait for requests
        site: Site key for cookie loading/saving
        account: Account identifier for multi-account
        headless: Run browser in headless mode (default False to see what's happening)
    
    Returns:
        List of intercepted request/response info:
        [
            {
                "url": str,
                "method": str,
                "request_headers": dict,
                "post_data": str,
                "status": int,
                "response_headers": dict,
                "mime_type": str,
                "body": str,
            },
            ...
        ]
    """
    from playwright_browser import PlaywrightBrowser
    
    pattern = re.compile(url_pattern)
    intercepted = []
    
    with PlaywrightBrowser(site=site, account=account, headless=headless) as browser:
        def on_response(response):
            """Handle response event - capture matching requests."""
            try:
                if pattern.search(response.url):
                    # Get request info
                    request = response.request
                    
                    # Try to get response body
                    body = ""
                    try:
                        if response.ok:
                            # Check content type for text-based responses
                            content_type = response.headers.get("content-type", "")
                            if any(t in content_type for t in ["json", "text", "javascript", "xml", "html"]):
                                body = response.text()
                            else:
                                # Binary content - skip or truncate
                                body = f"[Binary content: {content_type}]"
                    except Exception as e:
                        body = f"[Error getting body: {e}]"
                    
                    intercepted.append({
                        "url": response.url,
                        "method": request.method,
                        "request_headers": dict(request.headers),
                        "post_data": request.post_data or "",
                        "status": response.status,
                        "response_headers": dict(response.headers),
                        "mime_type": response.headers.get("content-type", ""),
                        "body": body[:100000] if body else "",  # Truncate very large responses
                    })
            except Exception as e:
                log.warning(f"Error capturing response: {e}")
        
        # Register response handler
        browser.page.on("response", on_response)
        
        # Navigate to page
        browser.goto(page_url)
        
        # Wait for requests to complete
        browser.page.wait_for_timeout(wait_seconds * 1000)
        
        # Unregister handler
        browser.page.remove_listener("response", on_response)
    
    log.info(f"Intercepted {len(intercepted)} requests matching '{url_pattern}'")
    return intercepted


def intercept_xhr(
    page_url: str,
    url_pattern: str,
    wait_seconds: int = 15,
    site: str = None,
    account: str = "default",
) -> List[str]:
    """
    Simplified interception: load page, wait, and return matched response bodies.
    
    Args:
        page_url: URL to navigate to
        url_pattern: Regex pattern to match request URLs
        wait_seconds: How long to wait
        site: Site key for cookies
        account: Account identifier
    
    Returns:
        List of response bodies (strings)
    """
    results = intercept_page(
        page_url=page_url,
        url_pattern=url_pattern,
        wait_seconds=wait_seconds,
        site=site,
        account=account,
        headless=True,  # Headless for speed
    )
    return [r["body"] for r in results if r.get("body") and not r["body"].startswith("[")]


def intercept_api_json(
    page_url: str,
    url_pattern: str,
    wait_seconds: int = 15,
    site: str = None,
    account: str = "default",
) -> List[Dict]:
    """
    Intercept and parse JSON API responses.
    
    Args:
        page_url: URL to navigate to
        url_pattern: Regex pattern to match API URLs
        wait_seconds: How long to wait
        site: Site key for cookies
        account: Account identifier
    
    Returns:
        List of parsed JSON objects
    """
    bodies = intercept_xhr(page_url, url_pattern, wait_seconds, site, account)
    parsed = []
    
    for body in bodies:
        try:
            data = json.loads(body)
            parsed.append(data)
        except json.JSONDecodeError:
            continue
    
    return parsed


# ─── Legacy Compatibility (deprecated) ───

def intercept_page_legacy(driver, page_url, url_pattern, wait_seconds=30, load_cookies_site=None):
    """
    DEPRECATED: Legacy Selenium-based interception.
    
    Use intercept_page() instead:
        intercept_page(page_url, url_pattern, wait_seconds, site=load_cookies_site)
    
    This function is kept for backward compatibility but will be removed in a future version.
    """
    log.warning(
        "intercept_page_legacy() is deprecated. Use intercept_page() instead. "
        "The driver parameter is no longer needed - Playwright is used internally."
    )
    # Delegate to new implementation
    return intercept_page(
        page_url=page_url,
        url_pattern=url_pattern,
        wait_seconds=wait_seconds,
        site=load_cookies_site,
        headless=False,
    )
