"""
Browser Pilot - Selenium/CDP Driver Factory
Creates WebDriver instances with anti-detection, CDP support, and profile isolation.
Supports using copied Chrome profiles for inheriting cookies/sessions.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

log = logging.getLogger("browser-pilot")

# Default profiles directory for browser-pilot isolated profiles
PROFILES_DIR = Path.home() / ".qoder" / "browser-pilot" / "chrome-profiles"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""


def create_driver(
    profile: str = "default",
    headless: bool = False,
    enable_perf_log: bool = True,
    chrome_profile_path: Optional[str] = None
):
    """
    Create a ChromeDriver with anti-detection and optional CDP logging.
    
    Args:
        profile: Browser-pilot profile name (for isolated storage)
        headless: Run in headless mode
        enable_perf_log: Enable CDP performance logging
        chrome_profile_path: Path to a copied Chrome profile directory.
                            If provided, uses this instead of creating a new profile.
                            This should be a full user-data-dir path from copy_chrome_profile_full().
    
    Returns:
        WebDriver instance
    """
    options = Options()

    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Profile handling
    if chrome_profile_path:
        # Use copied Chrome profile (inherits cookies, sessions, etc.)
        user_data_dir = Path(chrome_profile_path)
        if not user_data_dir.exists():
            log.warning(f"Chrome profile path not found: {chrome_profile_path}")
            # Fall back to default profile
            PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            profile_dir = PROFILES_DIR / profile
            profile_dir.mkdir(parents=True, exist_ok=True)
            options.add_argument(f"--user-data-dir={profile_dir}")
        else:
            log.info(f"Using copied Chrome profile: {chrome_profile_path}")
            options.add_argument(f"--user-data-dir={user_data_dir}")
    else:
        # Use browser-pilot's isolated profile
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        profile_dir = PROFILES_DIR / profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")

    # Common settings
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--start-maximized")

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    # Performance logging for CDP event capture
    if enable_perf_log:
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    try:
        service = Service(ChromeDriverManager().install())
    except Exception:
        # Fallback: assume chromedriver is in PATH
        service = Service()

    driver = webdriver.Chrome(service=service, options=options)

    # Inject stealth JS
    inject_stealth_js(driver)

    # Enable CDP Network and Page domains
    if enable_perf_log:
        execute_cdp(driver, "Network.enable", {})
        execute_cdp(driver, "Page.enable", {})

    return driver


def create_driver_with_chrome_profile(
    chrome_profile: str = "Default",
    headless: bool = False,
    enable_perf_log: bool = True,
    force_copy: bool = False
):
    """
    Create a driver using a copied Chrome profile.
    This copies the Chrome profile first, then launches with that profile.
    Works even when Chrome is running (like Playwright persistent context).
    
    Args:
        chrome_profile: Name of Chrome profile to copy (Default, Profile 1, etc.)
        headless: Run in headless mode
        enable_perf_log: Enable CDP performance logging
        force_copy: Force re-copy of profile even if recent copy exists
    
    Returns:
        tuple: (WebDriver, profile_path) or (None, error_message)
    """
    import chrome_cookies
    
    # Check for existing recent copy if not forcing
    if not force_copy:
        existing = chrome_cookies.get_latest_copied_profile(chrome_profile)
        if existing:
            log.info(f"Using existing profile copy: {existing}")
            driver = create_driver(
                chrome_profile_path=existing,
                headless=headless,
                enable_perf_log=enable_perf_log
            )
            return driver, existing
    
    # Copy Chrome profile
    result = chrome_cookies.copy_chrome_profile_full(
        chrome_profile=chrome_profile,
        force=force_copy
    )
    
    if not result["success"]:
        log.error(f"Failed to copy Chrome profile: {result['message']}")
        return None, result["message"]
    
    profile_path = result["path"]
    
    # Create driver with copied profile
    driver = create_driver(
        chrome_profile_path=profile_path,
        headless=headless,
        enable_perf_log=enable_perf_log
    )
    
    return driver, profile_path


def inject_stealth_js(driver):
    """Override navigator.webdriver and other detection signals."""
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_JS})
    except Exception:
        try:
            driver.execute_script(STEALTH_JS)
        except Exception:
            pass


def execute_cdp(driver, cmd, params=None):
    """Execute a CDP command and return the result."""
    if params is None:
        params = {}
    try:
        return driver.execute_cdp_cmd(cmd, params)
    except Exception as e:
        log.warning(f"CDP command '{cmd}' failed: {e}")
        return None


def get_performance_logs(driver):
    """Parse performance logs to extract Network events."""
    events = []
    try:
        logs = driver.get_log("performance")
    except Exception:
        return events

    for entry in logs:
        try:
            msg = json.loads(entry["message"])
            method = msg.get("message", {}).get("method", "")
            params = msg.get("message", {}).get("params", {})
            if method.startswith("Network."):
                events.append({
                    "method": method,
                    "params": params,
                    "timestamp": entry.get("timestamp")
                })
        except (json.JSONDecodeError, KeyError):
            continue

    return events


def get_user_agent(driver):
    """Get browser user agent string."""
    try:
        return driver.execute_script("return navigator.userAgent")
    except Exception:
        return None


def close_driver(driver):
    """Safely close the driver."""
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
