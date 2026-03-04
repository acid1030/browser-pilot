"""
Browser Pilot - Chrome Cookie Extractor
Reads cookies from Chrome's local SQLite database on macOS.
Uses browser_cookie3 for cross-platform cookie extraction and decryption.
"""
import os
import logging
from pathlib import Path

log = logging.getLogger("browser-pilot.chrome")

# Chrome profile paths on different platforms
CHROME_PATHS = {
    "darwin": Path.home() / "Library" / "Application Support" / "Google" / "Chrome",
    "linux": Path.home() / ".config" / "google-chrome",
    "win32": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
}


def get_chrome_cookies(domain, profile="Default"):
    """
    Extract cookies for a specific domain from Chrome browser.
    
    Args:
        domain: Domain to get cookies for (e.g., "douyin.com", ".douyin.com")
        profile: Chrome profile name (e.g., "Default", "Profile 1")
    
    Returns:
        List of cookie dicts compatible with Selenium, or empty list if failed.
    """
    try:
        import browser_cookie3
    except ImportError:
        log.warning("browser_cookie3 not installed. Run: pip install browser_cookie3")
        return []
    
    cookies = []
    
    try:
        # Get Chrome cookies using browser_cookie3
        # This handles decryption automatically on macOS/Windows/Linux
        cj = browser_cookie3.chrome(domain_name=domain)
        
        for cookie in cj:
            # Convert to Selenium-compatible format
            selenium_cookie = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "httpOnly": cookie.has_nonstandard_attr("HttpOnly"),
            }
            
            # Add expiry if not a session cookie
            if cookie.expires:
                selenium_cookie["expiry"] = cookie.expires
            
            cookies.append(selenium_cookie)
        
        log.info(f"Found {len(cookies)} cookies for domain '{domain}' in Chrome")
        return cookies
        
    except browser_cookie3.BrowserCookieError as e:
        log.warning(f"Failed to read Chrome cookies: {e}")
        return []
    except PermissionError:
        log.warning("Permission denied reading Chrome cookies. Is Chrome running?")
        return []
    except Exception as e:
        log.warning(f"Error extracting Chrome cookies: {e}")
        return []


def get_chrome_cookies_for_site(site):
    """
    Get cookies for a site, trying multiple domain patterns.
    
    Args:
        site: Site name like "douyin.com" or "www.douyin.com"
    
    Returns:
        List of Selenium-compatible cookie dicts.
    """
    # Normalize domain - strip www prefix and add dot prefix
    domain = site.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Try different domain patterns
    patterns = [
        f".{domain}",  # .douyin.com (matches all subdomains)
        domain,        # douyin.com (exact match)
    ]
    
    all_cookies = []
    seen = set()
    
    for pattern in patterns:
        cookies = get_chrome_cookies(pattern)
        for cookie in cookies:
            # Deduplicate by name+domain+path
            key = (cookie["name"], cookie["domain"], cookie["path"])
            if key not in seen:
                seen.add(key)
                all_cookies.append(cookie)
    
    return all_cookies


def list_chrome_profiles():
    """
    List available Chrome profiles.
    
    Returns:
        List of profile names (e.g., ["Default", "Profile 1", "Profile 2"])
    """
    import platform
    system = platform.system().lower()
    
    if system == "darwin":
        system = "darwin"
    elif system == "windows":
        system = "win32"
    
    chrome_path = CHROME_PATHS.get(system)
    if not chrome_path or not chrome_path.exists():
        return []
    
    profiles = []
    
    # Check Default profile
    if (chrome_path / "Default").exists():
        profiles.append("Default")
    
    # Check numbered profiles
    for item in chrome_path.iterdir():
        if item.is_dir() and item.name.startswith("Profile "):
            profiles.append(item.name)
    
    return profiles


def has_chrome_cookies(site):
    """
    Quick check if Chrome has any cookies for a site.
    
    Args:
        site: Site name like "douyin.com"
    
    Returns:
        bool indicating if cookies exist
    """
    cookies = get_chrome_cookies_for_site(site)
    return len(cookies) > 0
