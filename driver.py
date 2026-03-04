"""
Browser Pilot - Selenium/CDP Driver Factory
Creates WebDriver instances with anti-detection, CDP support, and profile isolation.
"""
import json
import logging
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

log = logging.getLogger("browser-pilot")

PROFILES_DIR = Path.home() / ".qoder" / "browser-pilot" / "chrome-profiles"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""


def create_driver(profile="default", headless=False, enable_perf_log=True):
    """Create a ChromeDriver with anti-detection and optional CDP logging."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_dir = PROFILES_DIR / profile
    profile_dir.mkdir(parents=True, exist_ok=True)

    options = Options()

    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Profile isolation
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
