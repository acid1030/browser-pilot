"""
Browser Pilot - Cookie Manager
Handles cookie serialization between Selenium driver, SQLite, and requests.Session.
"""
import json
import re
import time
import logging
from urllib.parse import urlparse

import db
from driver import get_user_agent

log = logging.getLogger("browser-pilot")


def extract_site(url):
    """Extract domain from URL for use as site key."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Remove 'www.' prefix
    if host.startswith("www."):
        host = host[4:]
    return host


def save_from_driver(driver, site=None, profile="default"):
    """Save browser cookies to database."""
    if site is None:
        site = extract_site(driver.current_url)

    cookies = driver.get_cookies()
    # Clean cookies for serialization
    clean_cookies = []
    for c in cookies:
        cookie = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }
        if c.get("expiry"):
            cookie["expiry"] = c["expiry"]
        if c.get("sameSite"):
            cookie["sameSite"] = c["sameSite"]
        clean_cookies.append(cookie)

    ua = get_user_agent(driver)
    db.save_cookies(site, profile, clean_cookies, ua)
    log.info(f"Saved {len(clean_cookies)} cookies for {site}")
    return len(clean_cookies)


def load_to_driver(driver, site, target_url=None):
    """Load stored cookies into browser driver."""
    cookies = db.load_cookies(site)
    if not cookies:
        log.warning(f"No stored cookies for {site}")
        return 0

    # Must navigate to the domain first
    if target_url:
        try:
            driver.get(target_url)
            time.sleep(1)
        except Exception as e:
            log.warning(f"Failed to navigate to {target_url}: {e}")

    count = 0
    for cookie in cookies:
        try:
            # Remove sameSite if not supported or has issues
            add_cookie = {k: v for k, v in cookie.items() if v is not None}
            if "sameSite" in add_cookie and add_cookie["sameSite"] not in ("Strict", "Lax", "None"):
                del add_cookie["sameSite"]
            driver.add_cookie(add_cookie)
            count += 1
        except Exception as e:
            log.debug(f"Failed to add cookie {cookie.get('name')}: {e}")

    log.info(f"Loaded {count}/{len(cookies)} cookies for {site}")
    return count


def load_to_requests_session(session, site):
    """Inject stored cookies into a requests.Session."""
    cookies = db.load_cookies(site)
    if not cookies:
        return 0

    for cookie in cookies:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain", ""),
            path=cookie.get("path", "/")
        )

    # Also set user agent if available
    store = db.get_cookie_store(site)
    if store and store.get("user_agent"):
        session.headers["User-Agent"] = store["user_agent"]

    return len(cookies)


def cookies_as_header_string(site):
    """Format stored cookies as a Cookie header string."""
    cookies = db.load_cookies(site)
    if not cookies:
        return ""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def check_validity(site, check_url):
    """Check if stored cookies are still valid by making an HTTP request."""
    import requests as req

    cookies = db.load_cookies(site)
    if not cookies:
        return False

    session = req.Session()
    load_to_requests_session(session, site)

    try:
        resp = session.get(check_url, timeout=15, allow_redirects=False)
        # Valid if not redirecting to login and status is 200
        is_valid = (
            resp.status_code == 200
            and "login" not in resp.headers.get("Location", "").lower()
        )
        db.update_cookie_validity(site, is_valid)
        return is_valid
    except Exception as e:
        log.warning(f"Cookie validity check failed for {site}: {e}")
        db.update_cookie_validity(site, False)
        return False


def wait_for_login(driver, check_url=None, check_selector=None, timeout=300, interval=5):
    """Poll every `interval` seconds to detect login completion."""
    from selenium.webdriver.common.by import By

    start = time.time()
    initial_url = driver.current_url

    print(f"Waiting for login (polling every {interval}s, timeout {timeout}s)...")
    print("Please complete the login in the browser window.")

    while time.time() - start < timeout:
        time.sleep(interval)
        elapsed = int(time.time() - start)

        try:
            current_url = driver.current_url

            # Check 1: Selector-based detection
            if check_selector:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, check_selector)
                    if el:
                        print(f"\n[{elapsed}s] Login detected! (selector found)")
                        return True
                except Exception:
                    pass

            # Check 2: URL changed away from login page
            login_patterns = re.compile(r"(login|signin|sign-in|auth|passport|sso)", re.I)
            if login_patterns.search(initial_url) and not login_patterns.search(current_url):
                print(f"\n[{elapsed}s] Login detected! (URL changed from login page)")
                return True

            # Check 3: Cookie count increased significantly
            cookies = driver.get_cookies()
            if len(cookies) > 5:
                # If we have cookies and URL doesn't look like login, likely logged in
                if not login_patterns.search(current_url):
                    print(f"\n[{elapsed}s] Login detected! ({len(cookies)} cookies, non-login URL)")
                    return True

            # Check 4: HTTP check with current cookies
            if check_url:
                cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                try:
                    import requests as req
                    resp = req.get(check_url, headers={"Cookie": cookie_str}, timeout=10, allow_redirects=False)
                    if resp.status_code == 200 and "login" not in resp.headers.get("Location", "").lower():
                        print(f"\n[{elapsed}s] Login detected! (check URL returned 200)")
                        return True
                except Exception:
                    pass

            print(f"  [{elapsed}s] Still waiting for login...", end="\r")

        except Exception as e:
            log.debug(f"Login check error: {e}")

    print(f"\nLogin detection timed out after {timeout}s")
    return False
