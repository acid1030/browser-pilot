"""
Browser Pilot - Cookie Manager
Handles cookie serialization between database, requests.Session, and Playwright.
Supports multi-account cookie storage and Playwright cookie format conversion.

Positioned as Playwright supplement: provides persistent cookie database,
HTTP cookie injection, and Playwright <-> DB cookie sync.
"""
import json
import logging
from urllib.parse import urlparse

import db
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
            return {"success": False, "count": 0, "message": f"No cookies found in Chrome for {site}"}
        
        db.save_cookies(site, db_profile, cookies, user_agent=None, account=account)
        log.info(f"Imported {len(cookies)} cookies from Chrome for {site}" + (f" (account: {account})" if account else ""))
        
        return {"success": True, "count": len(cookies), "message": f"Imported {len(cookies)} cookies"}
        
    except Exception as e:
        log.error(f"Failed to import cookies from Chrome: {e}")
        return {"success": False, "count": 0, "message": f"Error: {str(e)}"}


def import_via_profile_copy(chrome_profile="Default", force_copy=False):
    """
    Import cookies by copying Chrome profile directory.
    Works even when Chrome is running.
    
    Args:
        chrome_profile: Chrome profile name (Default, Profile 1, etc.)
        force_copy: If True, always create a fresh copy
    
    Returns:
        dict: {"success": bool, "profile_path": str or None, "message": str}
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


# ─── Playwright Cookie Interop ───


def cookies_to_playwright_format(db_cookies):
    """
    Convert DB-format cookies to Playwright context.add_cookies() format.
    
    Key difference: DB uses 'expiry' (int), Playwright uses 'expires' (float, -1 for session).
    
    Args:
        db_cookies: List of cookies in DB format
    
    Returns:
        list: Cookies in Playwright format
    """
    pw_cookies = []
    for c in db_cookies:
        pw_cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),  # Ensure boolean
            "httpOnly": bool(c.get("httpOnly", False)),  # Ensure boolean
        }
        # expiry -> expires
        if c.get("expiry"):
            pw_cookie["expires"] = float(c["expiry"])
        else:
            pw_cookie["expires"] = -1  # session cookie
        # sameSite normalization
        sam = c.get("sameSite", "")
        if sam in ("Strict", "Lax", "None"):
            pw_cookie["sameSite"] = sam
        pw_cookies.append(pw_cookie)
    return pw_cookies


def cookies_from_playwright_format(pw_cookies):
    """
    Convert Playwright-format cookies to DB format.
    
    Key difference: Playwright uses 'expires' (float), DB uses 'expiry' (int).
    
    Args:
        pw_cookies: List of cookies in Playwright format
    
    Returns:
        list: Cookies in DB format
    """
    db_cookies = []
    for c in pw_cookies:
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),  # Ensure boolean
            "httpOnly": bool(c.get("httpOnly", False)),  # Ensure boolean
        }
        # expires -> expiry
        expires = c.get("expires", -1)
        if expires and expires > 0:
            cookie["expiry"] = int(expires)
        # sameSite
        sam = c.get("sameSite", "")
        if sam in ("Strict", "Lax", "None"):
            cookie["sameSite"] = sam
        db_cookies.append(cookie)
    return db_cookies


def save_from_playwright_json(file_path, site, profile="default", account=None):
    """
    Read Playwright-format cookies from a JSON file and save to DB.
    
    Accepts either:
    - Playwright storage_state format: {"cookies": [...], "origins": [...]}
    - Plain cookie array: [{"name": ..., "value": ..., ...}, ...]
    
    Args:
        file_path: Path to JSON file with Playwright cookies
        site: Site key to store under (if None, auto-groups by domain)
        profile: DB profile name
        account: Optional account identifier
    
    Returns:
        dict: {"success": bool, "count": int, "sites": list, "message": str}
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle storage_state format vs plain array
        if isinstance(data, dict) and "cookies" in data:
            pw_cookies = data["cookies"]
        elif isinstance(data, list):
            pw_cookies = data
        else:
            return {"success": False, "count": 0, "sites": [], "message": "Invalid JSON format: expected cookie array or storage_state object"}
        
        if not pw_cookies:
            return {"success": False, "count": 0, "sites": [], "message": "No cookies found in file"}
        
        # Convert to DB format
        db_cookies = cookies_from_playwright_format(pw_cookies)
        
        if site:
            # Save all cookies under the specified site
            domain_cookies = [c for c in db_cookies if site in c.get("domain", "")]
            if not domain_cookies:
                # If no domain match, save all (user explicitly specified site)
                domain_cookies = db_cookies
            db.save_cookies(site, profile, domain_cookies, account=account)
            log.info(f"Saved {len(domain_cookies)} Playwright cookies for {site}" + (f" (account: {account})" if account else ""))
            return {"success": True, "count": len(domain_cookies), "sites": [site], "message": f"Imported {len(domain_cookies)} cookies for {site}"}
        else:
            # Auto-group by domain
            by_domain = {}
            for c in db_cookies:
                domain = c.get("domain", "").lstrip(".")
                if not domain:
                    continue
                by_domain.setdefault(domain, []).append(c)
            
            total = 0
            sites = []
            for domain, cookies in by_domain.items():
                db.save_cookies(domain, profile, cookies, account=account)
                total += len(cookies)
                sites.append(domain)
            
            log.info(f"Saved {total} Playwright cookies across {len(sites)} sites")
            return {"success": True, "count": total, "sites": sites, "message": f"Imported {total} cookies across {len(sites)} sites"}
    
    except FileNotFoundError:
        return {"success": False, "count": 0, "sites": [], "message": f"File not found: {file_path}"}
    except json.JSONDecodeError as e:
        return {"success": False, "count": 0, "sites": [], "message": f"Invalid JSON: {e}"}
    except Exception as e:
        return {"success": False, "count": 0, "sites": [], "message": f"Error: {str(e)}"}


def export_as_playwright_json(site, account=None):
    """
    Export DB cookies in Playwright storage_state format.
    
    Args:
        site: Site key to export
        account: Optional account identifier
    
    Returns:
        dict: Playwright storage_state format {"cookies": [...], "origins": []}
    """
    db_cookies = db.load_cookies(site, account=account)
    if not db_cookies:
        return {"cookies": [], "origins": []}
    
    pw_cookies = cookies_to_playwright_format(db_cookies)
    return {"cookies": pw_cookies, "origins": []}


# ─── Chrome Utility Functions ───


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
