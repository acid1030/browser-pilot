"""
Browser Pilot - Cookie Manager
Handles cookie serialization between Selenium driver, SQLite, and requests.Session.
Supports intelligent cookie loading: database -> validate -> Chrome import.
Supports account-based cookie storage for multi-account scenarios.

v2.1: Now supports Chrome profile copying for loading cookies when Chrome is running.
"""
import json
import re
import time
import logging
from urllib.parse import urlparse

import db
from driver import get_user_agent
import chrome_cookies

log = logging.getLogger("browser-pilot")


def extract_site(url):
    """Extract domain from URL for use as site key."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Remove 'www.' prefix
    if host.startswith("www."):
        host = host[4:]
    return host


def save_from_driver(driver, site=None, profile="default", account=None):
    """Save browser cookies to database with optional account identifier."""
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
    db.save_cookies(site, profile, clean_cookies, ua, account=account)
    log.info(f"Saved {len(clean_cookies)} cookies for {site}" + (f" (account: {account})" if account else ""))
    return len(clean_cookies)


def load_to_driver(driver, site, target_url=None, account=None):
    """Load stored cookies into browser driver, optionally filtered by account."""
    cookies = db.load_cookies(site, account=account)
    if not cookies:
        log.warning(f"No stored cookies for {site}" + (f" (account: {account})" if account else ""))
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

    log.info(f"Loaded {count}/{len(cookies)} cookies for {site}" + (f" (account: {account})" if account else ""))
    return count


def load_to_requests_session(session, site, account=None):
    """Inject stored cookies into a requests.Session."""
    cookies = db.load_cookies(site, account=account)
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
    store = db.get_cookie_store(site, account=account)
    if store and store.get("user_agent"):
        session.headers["User-Agent"] = store["user_agent"]

    return len(cookies)


def cookies_as_header_string(site, account=None):
    """Format stored cookies as a Cookie header string."""
    cookies = db.load_cookies(site, account=account)
    if not cookies:
        return ""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def check_validity(site, check_url, account=None):
    """Check if stored cookies are still valid by making an HTTP request."""
    import requests as req

    cookies = db.load_cookies(site, account=account)
    if not cookies:
        return False

    session = req.Session()
    load_to_requests_session(session, site, account=account)

    try:
        resp = session.get(check_url, timeout=15, allow_redirects=False)
        # Valid if not redirecting to login and status is 200
        is_valid = (
            resp.status_code == 200
            and "login" not in resp.headers.get("Location", "").lower()
        )
        db.update_cookie_validity(site, is_valid, account=account)
        return is_valid
    except Exception as e:
        log.warning(f"Cookie validity check failed for {site}: {e}")
        db.update_cookie_validity(site, False, account=account)
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


def validate_cookies(site, test_url, method="GET", account=None):
    """
    Validate stored cookies by making an HTTP request.
    
    Args:
        site: Domain/site key
        test_url: URL to test against (should return 200 if logged in)
        method: HTTP method to use (GET or POST)
        account: Optional account identifier
    
    Returns:
        dict: {"valid": bool, "status_code": int, "reason": str}
    """
    import requests as req
    
    cookies = db.load_cookies(site, account=account)
    if not cookies:
        return {"valid": False, "status_code": 0, "reason": "no_cookies"}
    
    session = req.Session()
    load_to_requests_session(session, site, account=account)
    
    try:
        if method.upper() == "POST":
            resp = session.post(test_url, timeout=15, allow_redirects=False)
        else:
            resp = session.get(test_url, timeout=15, allow_redirects=False)
        
        # Check for login redirect patterns
        location = resp.headers.get("Location", "").lower()
        login_patterns = ["login", "signin", "sign-in", "auth", "passport", "sso"]
        is_login_redirect = any(p in location for p in login_patterns)
        
        if resp.status_code == 200:
            db.update_cookie_validity(site, True, account=account)
            return {"valid": True, "status_code": 200, "reason": "ok"}
        elif resp.status_code in (301, 302, 303, 307, 308):
            if is_login_redirect:
                db.update_cookie_validity(site, False, account=account)
                return {"valid": False, "status_code": resp.status_code, "reason": "login_redirect"}
            else:
                # Non-login redirect might still be valid
                db.update_cookie_validity(site, True, account=account)
                return {"valid": True, "status_code": resp.status_code, "reason": "redirect_non_login"}
        elif resp.status_code == 401 or resp.status_code == 403:
            db.update_cookie_validity(site, False, account=account)
            return {"valid": False, "status_code": resp.status_code, "reason": "auth_failed"}
        else:
            db.update_cookie_validity(site, False, account=account)
            return {"valid": False, "status_code": resp.status_code, "reason": f"http_{resp.status_code}"}
            
    except req.exceptions.Timeout:
        return {"valid": False, "status_code": 0, "reason": "timeout"}
    except req.exceptions.ConnectionError:
        return {"valid": False, "status_code": 0, "reason": "connection_error"}
    except Exception as e:
        log.warning(f"Cookie validation failed for {site}: {e}")
        return {"valid": False, "status_code": 0, "reason": f"error: {str(e)}"}


def import_from_chrome(site, chrome_profile="Default", db_profile="default", account=None):
    """
    Import cookies from local Chrome browser into database.
    
    This uses browser_cookie3 which may fail if Chrome is running.
    For reliable import when Chrome is running, use import_via_profile_copy() instead.
    
    Args:
        site: Domain to extract cookies for (e.g., "douyin.com")
        chrome_profile: Chrome profile name (Default, Profile 1, etc.)
        db_profile: Database profile name to save under
        account: Optional account identifier to save under
    
    Returns:
        dict: {"success": bool, "count": int, "message": str}
    """
    try:
        cookies = chrome_cookies.get_chrome_cookies_for_site(site, chrome_profile)
        
        if not cookies:
            return {"success": False, "count": 0, "message": f"No cookies found in Chrome for {site} (Chrome may be running, try import_via_profile_copy)"}
        
        # Save to database (use None for user_agent as we don't know Chrome's UA)
        db.save_cookies(site, db_profile, cookies, user_agent=None, account=account)
        log.info(f"Imported {len(cookies)} cookies from Chrome for {site}" + (f" (account: {account})" if account else ""))
        
        return {"success": True, "count": len(cookies), "message": f"Imported {len(cookies)} cookies"}
        
    except Exception as e:
        log.error(f"Failed to import cookies from Chrome: {e}")
        return {"success": False, "count": 0, "message": f"Error: {str(e)}"}


def import_via_profile_copy(chrome_profile="Default", force_copy=False):
    """
    Import cookies by copying Chrome profile directory.
    This works even when Chrome is running (like Playwright's persistent context).
    
    Instead of reading cookies directly, this copies the Chrome profile
    so you can launch a browser with it using create_driver_with_chrome_profile().
    
    Args:
        chrome_profile: Chrome profile name (Default, Profile 1, etc.)
        force_copy: If True, always create a fresh copy
    
    Returns:
        dict: {
            "success": bool,
            "profile_path": str or None,  # Path to copied profile
            "message": str
        }
    """
    result = chrome_cookies.copy_chrome_profile_full(
        chrome_profile=chrome_profile,
        force=force_copy
    )
    
    return {
        "success": result["success"],
        "profile_path": result.get("path"),
        "message": result["message"]
    }


def smart_load_cookies(driver, site, test_url=None, chrome_profile="Default", account=None):
    """
    Intelligent cookie loading with fallback chain:
    1. Load from database (filtered by account if specified)
    2. Validate via HTTP request (if test_url provided)
    3. If invalid/missing, import from Chrome (using browser_cookie3)
    4. Inject into driver
    
    Note: This uses browser_cookie3 for Chrome import, which may fail if Chrome is running.
    For a more reliable approach when Chrome is running, use create_driver_with_chrome_profile()
    from driver.py instead.
    
    Args:
        driver: Selenium WebDriver
        site: Domain/site key
        test_url: URL to validate cookies (optional)
        chrome_profile: Chrome profile for import fallback
        account: Optional account identifier
    
    Returns:
        dict: {"source": str, "count": int, "valid": bool, "account": str}
    """
    result = {"source": None, "count": 0, "valid": False, "account": account}
    
    # Step 1: Check database
    db_cookies = db.load_cookies(site, account=account)
    
    if db_cookies:
        log.info(f"Found {len(db_cookies)} cookies in database for {site}" + (f" (account: {account})" if account else ""))
        
        # Step 2: Validate if test_url provided
        if test_url:
            validation = validate_cookies(site, test_url, account=account)
            if validation["valid"]:
                count = load_to_driver(driver, site, account=account)
                return {"source": "database", "count": count, "valid": True, "account": account}
            else:
                log.info(f"Database cookies invalid: {validation['reason']}")
        else:
            # No validation URL, assume valid
            count = load_to_driver(driver, site, account=account)
            return {"source": "database", "count": count, "valid": True, "account": account}
    
    # Step 3: Try Chrome import (may fail if Chrome is running)
    log.info(f"Attempting to import from Chrome ({chrome_profile})...")
    import_result = import_from_chrome(site, chrome_profile, account=account)
    
    if import_result["success"]:
        # Validate imported cookies if test_url provided
        if test_url:
            validation = validate_cookies(site, test_url, account=account)
            if not validation["valid"]:
                log.warning(f"Imported Chrome cookies also invalid: {validation['reason']}")
                return {"source": "chrome", "count": import_result["count"], "valid": False, "account": account}
        
        count = load_to_driver(driver, site, account=account)
        return {"source": "chrome", "count": count, "valid": True, "account": account}
    
    log.warning(f"No valid cookies found for {site}" + (f" (account: {account})" if account else ""))
    return {"source": None, "count": 0, "valid": False, "account": account}


def list_chrome_profiles():
    """List available Chrome profiles for cookie import."""
    return chrome_cookies.list_chrome_profiles()


def has_chrome_cookies(site, profile="Default"):
    """Check if Chrome has cookies for a site."""
    return chrome_cookies.has_chrome_cookies(site, profile)


def get_copied_profiles():
    """List all copied Chrome profile directories."""
    return chrome_cookies.get_copied_profiles()


def cleanup_old_profiles(keep_count=3):
    """Remove old copied Chrome profiles."""
    return chrome_cookies.cleanup_old_profiles(keep_count)
