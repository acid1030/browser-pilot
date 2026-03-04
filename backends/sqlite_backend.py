"""
Browser Pilot - SQLite Backend
Extracted from the original db.py. All SQLite-specific logic lives here.
Supports account-based cookie storage for multi-account scenarios.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from backends.base import DatabaseBackend

DB_DIR = Path.home() / ".qoder" / "browser-pilot"
DB_PATH = DB_DIR / "browser_pilot.db"


def _now_iso():
    return datetime.now().isoformat()


class SQLiteBackend(DatabaseBackend):

    def __init__(self):
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.ensure_schema()

    def ensure_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS cookie_stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site TEXT NOT NULL,
                account TEXT DEFAULT '',
                profile TEXT DEFAULT 'default',
                cookies_json TEXT NOT NULL,
                user_agent TEXT,
                is_valid INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(site, account)
            );

            CREATE TABLE IF NOT EXISTS request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                method TEXT DEFAULT 'GET',
                headers_json TEXT,
                body_json TEXT,
                status_code INTEGER,
                response_preview TEXT,
                via TEXT DEFAULT 'http',
                site TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site TEXT NOT NULL,
                account TEXT DEFAULT '',
                is_logged_in INTEGER DEFAULT 0,
                check_url TEXT,
                check_selector TEXT,
                last_check TEXT,
                last_login TEXT,
                UNIQUE(site, account)
            );
            
            CREATE INDEX IF NOT EXISTS idx_cookie_site_account ON cookie_stores(site, account);
            CREATE INDEX IF NOT EXISTS idx_login_site_account ON login_states(site, account);
        """)
        self._conn.commit()
        
        # Migration: add account column if missing (for existing databases)
        self._migrate_add_account_column()

    def _migrate_add_account_column(self):
        """Add account column to existing tables if not present."""
        try:
            # Check if account column exists in cookie_stores
            cursor = self._conn.execute("PRAGMA table_info(cookie_stores)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'account' not in columns:
                self._conn.execute("ALTER TABLE cookie_stores ADD COLUMN account TEXT DEFAULT ''")
                self._conn.commit()
        except Exception:
            pass
        
        try:
            # Check if account column exists in login_states
            cursor = self._conn.execute("PRAGMA table_info(login_states)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'account' not in columns:
                self._conn.execute("ALTER TABLE login_states ADD COLUMN account TEXT DEFAULT ''")
                self._conn.commit()
        except Exception:
            pass

    # ─── Cookie Store ───

    def save_cookies(self, site, profile, cookies_list, user_agent=None, account=None):
        ts = _now_iso()
        account = account or ''
        cookies_json = json.dumps(cookies_list, ensure_ascii=False)
        self._conn.execute("""
            INSERT INTO cookie_stores (site, account, profile, cookies_json, user_agent, is_valid, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(site, account) DO UPDATE SET
                profile=excluded.profile,
                cookies_json=excluded.cookies_json,
                user_agent=excluded.user_agent,
                is_valid=1,
                updated_at=excluded.updated_at
        """, (site, account, profile, cookies_json, user_agent, ts, ts))
        self._conn.commit()

    def load_cookies(self, site, account=None):
        if account:
            row = self._conn.execute(
                "SELECT cookies_json FROM cookie_stores WHERE site = ? AND account = ?", (site, account)
            ).fetchone()
        else:
            # If no account specified, try exact empty match first, then any
            row = self._conn.execute(
                "SELECT cookies_json FROM cookie_stores WHERE site = ? AND account = ''", (site,)
            ).fetchone()
            if not row:
                row = self._conn.execute(
                    "SELECT cookies_json FROM cookie_stores WHERE site = ? ORDER BY updated_at DESC LIMIT 1", (site,)
                ).fetchone()
        if row:
            return json.loads(row["cookies_json"])
        return None

    def list_cookie_sites(self, account=None):
        if account:
            rows = self._conn.execute(
                "SELECT site, account, profile, is_valid, updated_at FROM cookie_stores WHERE account = ? ORDER BY updated_at DESC",
                (account,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT site, account, profile, is_valid, updated_at FROM cookie_stores ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_cookies(self, site, account=None):
        if account:
            self._conn.execute("DELETE FROM cookie_stores WHERE site = ? AND account = ?", (site, account))
        else:
            self._conn.execute("DELETE FROM cookie_stores WHERE site = ?", (site,))
        self._conn.commit()

    def update_cookie_validity(self, site, is_valid, account=None):
        if account:
            self._conn.execute(
                "UPDATE cookie_stores SET is_valid = ?, updated_at = ? WHERE site = ? AND account = ?",
                (1 if is_valid else 0, _now_iso(), site, account)
            )
        else:
            self._conn.execute(
                "UPDATE cookie_stores SET is_valid = ?, updated_at = ? WHERE site = ?",
                (1 if is_valid else 0, _now_iso(), site)
            )
        self._conn.commit()

    def get_cookie_store(self, site, account=None):
        if account:
            row = self._conn.execute(
                "SELECT * FROM cookie_stores WHERE site = ? AND account = ?", (site, account)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM cookie_stores WHERE site = ? AND account = ''", (site,)
            ).fetchone()
            if not row:
                row = self._conn.execute(
                    "SELECT * FROM cookie_stores WHERE site = ? ORDER BY updated_at DESC LIMIT 1", (site,)
                ).fetchone()
        return dict(row) if row else None

    # ─── Request History ───

    def save_request(self, url, method="GET", headers=None, body=None,
                     status_code=None, response_preview=None, via="http", site=None):
        self._conn.execute("""
            INSERT INTO request_history (url, method, headers_json, body_json, status_code, response_preview, via, site, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url, method,
            json.dumps(headers, ensure_ascii=False) if headers else None,
            json.dumps(body, ensure_ascii=False) if body and not isinstance(body, str) else body,
            status_code,
            (response_preview[:2000] if response_preview else None),
            via, site, _now_iso()
        ))
        self._conn.commit()

    def list_requests(self, limit=20, site=None):
        if site:
            rows = self._conn.execute(
                "SELECT id, url, method, status_code, via, site, timestamp FROM request_history WHERE site = ? ORDER BY id DESC LIMIT ?",
                (site, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, url, method, status_code, via, site, timestamp FROM request_history ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_request(self, req_id):
        row = self._conn.execute(
            "SELECT * FROM request_history WHERE id = ?", (req_id,)
        ).fetchone()
        return dict(row) if row else None

    # ─── Login State ───

    def update_login_state(self, site, is_logged_in, check_url=None, check_selector=None, account=None):
        ts = _now_iso()
        account = account or ''
        last_login = ts if is_logged_in else None
        self._conn.execute("""
            INSERT INTO login_states (site, account, is_logged_in, check_url, check_selector, last_check, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(site, account) DO UPDATE SET
                is_logged_in=excluded.is_logged_in,
                check_url=COALESCE(excluded.check_url, login_states.check_url),
                check_selector=COALESCE(excluded.check_selector, login_states.check_selector),
                last_check=excluded.last_check,
                last_login=COALESCE(excluded.last_login, login_states.last_login)
        """, (site, account, 1 if is_logged_in else 0, check_url, check_selector, ts, last_login))
        self._conn.commit()

    def get_login_state(self, site, account=None):
        if account:
            row = self._conn.execute(
                "SELECT * FROM login_states WHERE site = ? AND account = ?", (site, account)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM login_states WHERE site = ? AND account = ''", (site,)
            ).fetchone()
            if not row:
                row = self._conn.execute(
                    "SELECT * FROM login_states WHERE site = ? ORDER BY last_check DESC LIMIT 1", (site,)
                ).fetchone()
        return dict(row) if row else None
