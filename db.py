"""
Browser Pilot - Database Layer
Thin delegation layer that auto-detects MySQL or falls back to SQLite.
Supports account-based cookie storage for multi-account scenarios.

Configuration priority:
1. Environment variables: BROWSER_PILOT_DB=mysql + BROWSER_PILOT_MYSQL_*
2. Config file: ~/.qoder/browser-pilot/db_config.json
3. Default: SQLite at ~/.qoder/browser-pilot/browser_pilot.db
"""
import os
import sys
import json
import logging
from pathlib import Path

log = logging.getLogger("browser-pilot.db")

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

_backend = None
_CONFIG_PATH = Path.home() / ".qoder" / "browser-pilot" / "db_config.json"


def _detect_config():
    """Detect database backend configuration."""
    # Priority 1: Environment variables
    db_type = os.environ.get("BROWSER_PILOT_DB", "").lower()
    if db_type == "mysql":
        return {
            "backend": "mysql",
            "mysql": {
                "host": os.environ.get("BROWSER_PILOT_MYSQL_HOST", "127.0.0.1"),
                "port": int(os.environ.get("BROWSER_PILOT_MYSQL_PORT", "3306")),
                "user": os.environ.get("BROWSER_PILOT_MYSQL_USER", "root"),
                "password": os.environ.get("BROWSER_PILOT_MYSQL_PASSWORD", ""),
                "database": os.environ.get("BROWSER_PILOT_MYSQL_DATABASE", "browser_pilot"),
            },
        }

    # Priority 2: Config file
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            if cfg.get("backend") == "mysql" and "mysql" in cfg:
                return {"backend": "mysql", "mysql": cfg["mysql"]}
        except Exception as e:
            log.warning(f"Failed to read {_CONFIG_PATH}: {e}")

    # Priority 3: Default SQLite
    return {"backend": "sqlite"}


def _init_backend():
    """Initialize the appropriate database backend."""
    config = _detect_config()

    if config["backend"] == "mysql":
        try:
            from backends.mysql_backend import MySQLBackend
            return MySQLBackend(config["mysql"])
        except Exception as e:
            log.warning(f"MySQL unavailable, falling back to SQLite: {e}")

    from backends.sqlite_backend import SQLiteBackend
    backend = SQLiteBackend()
    log.info(f"Using SQLite backend")
    return backend


def _get_backend():
    global _backend
    if _backend is None:
        _backend = _init_backend()
    return _backend


# ─── Public API (delegate to backend) ───

def save_cookies(site, profile, cookies_list, user_agent=None, account=None):
    """Save cookies with optional account identifier."""
    return _get_backend().save_cookies(site, profile, cookies_list, user_agent, account)


def load_cookies(site, account=None):
    """Load cookies, optionally filtered by account."""
    return _get_backend().load_cookies(site, account)


def list_cookie_sites(account=None):
    """List all sites with stored cookies, optionally filtered by account."""
    return _get_backend().list_cookie_sites(account)


def delete_cookies(site, account=None):
    """Delete cookies for site, optionally filtered by account."""
    return _get_backend().delete_cookies(site, account)


def update_cookie_validity(site, is_valid, account=None):
    """Update validity status for site cookies."""
    return _get_backend().update_cookie_validity(site, is_valid, account)


def get_cookie_store(site, account=None):
    """Get full cookie store record."""
    return _get_backend().get_cookie_store(site, account)


def save_request(url, method="GET", headers=None, body=None,
                 status_code=None, response_preview=None, via="http", site=None):
    return _get_backend().save_request(url, method, headers, body,
                                       status_code, response_preview, via, site)


def list_requests(limit=20, site=None):
    return _get_backend().list_requests(limit, site)


def get_request(req_id):
    return _get_backend().get_request(req_id)


def update_login_state(site, is_logged_in, check_url=None, check_selector=None, account=None):
    """Update login state with optional account."""
    return _get_backend().update_login_state(site, is_logged_in, check_url, check_selector, account)


def get_login_state(site, account=None):
    """Get login state, optionally filtered by account."""
    return _get_backend().get_login_state(site, account)
