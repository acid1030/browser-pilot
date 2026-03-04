"""
Browser Pilot - MySQL Backend
Uses mysql-connector-python with connection pooling.
Supports account-based cookie storage for multi-account scenarios.
"""
import json
import logging
from datetime import datetime

from backends.base import DatabaseBackend

log = logging.getLogger("browser-pilot.db")


def _now_iso():
    return datetime.now().isoformat()


_SCHEMA_COOKIE_STORES = """
CREATE TABLE IF NOT EXISTS cookie_stores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(255) NOT NULL,
    account VARCHAR(255) NOT NULL DEFAULT '',
    profile VARCHAR(255) DEFAULT 'default',
    cookies_json LONGTEXT NOT NULL,
    user_agent VARCHAR(512),
    is_valid TINYINT(1) DEFAULT 1,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    UNIQUE KEY uk_site_account (site, account),
    INDEX idx_site_account (site, account)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_SCHEMA_REQUEST_HISTORY = """
CREATE TABLE IF NOT EXISTS request_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url TEXT NOT NULL,
    method VARCHAR(16) DEFAULT 'GET',
    headers_json LONGTEXT,
    body_json LONGTEXT,
    status_code SMALLINT,
    response_preview TEXT,
    via VARCHAR(16) DEFAULT 'http',
    site VARCHAR(255),
    timestamp VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_SCHEMA_LOGIN_STATES = """
CREATE TABLE IF NOT EXISTS login_states (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(255) NOT NULL,
    account VARCHAR(255) NOT NULL DEFAULT '',
    is_logged_in TINYINT(1) DEFAULT 0,
    check_url VARCHAR(512),
    check_selector VARCHAR(512),
    last_check VARCHAR(32),
    last_login VARCHAR(32),
    UNIQUE KEY uk_site_account (site, account),
    INDEX idx_site_account (site, account)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


class MySQLBackend(DatabaseBackend):

    def __init__(self, config):
        import mysql.connector
        from mysql.connector import pooling

        # Ensure database exists (connect without specifying database first)
        db_name = config.get("database", "browser_pilot")
        init_conn = mysql.connector.connect(
            host=config.get("host", "127.0.0.1"),
            port=config.get("port", 3306),
            user=config.get("user", "root"),
            password=config.get("password", ""),
        )
        cursor = init_conn.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.close()
        init_conn.close()

        # Create connection pool
        self._pool = pooling.MySQLConnectionPool(
            pool_name="browser_pilot_pool",
            pool_size=3,
            pool_reset_session=True,
            host=config.get("host", "127.0.0.1"),
            port=config.get("port", 3306),
            user=config.get("user", "root"),
            password=config.get("password", ""),
            database=db_name,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            autocommit=False,
        )

        self.ensure_schema()
        log.info(f"MySQL backend ready: {config.get('host')}:{config.get('port', 3306)}/{db_name}")

    def _exec(self, sql, params=None, fetch=None, commit=False):
        """Execute SQL with automatic connection acquire/release."""
        conn = self._pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            result = None
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            if commit:
                conn.commit()
            cursor.close()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()  # returns to pool

    def ensure_schema(self):
        conn = self._pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(_SCHEMA_COOKIE_STORES)
            cursor.execute(_SCHEMA_REQUEST_HISTORY)
            cursor.execute(_SCHEMA_LOGIN_STATES)
            conn.commit()
            cursor.close()
            
            # Migration: add account column if missing
            self._migrate_add_account_column(conn)
        finally:
            conn.close()

    def _migrate_add_account_column(self, conn):
        """Add account column to existing tables if not present."""
        cursor = conn.cursor()
        try:
            # Check cookie_stores
            cursor.execute("SHOW COLUMNS FROM cookie_stores LIKE 'account'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE cookie_stores ADD COLUMN account VARCHAR(255) NOT NULL DEFAULT '' AFTER site")
                cursor.execute("ALTER TABLE cookie_stores DROP INDEX site")
                cursor.execute("ALTER TABLE cookie_stores ADD UNIQUE KEY uk_site_account (site, account)")
                conn.commit()
        except Exception:
            pass
        
        try:
            # Check login_states
            cursor.execute("SHOW COLUMNS FROM login_states LIKE 'account'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE login_states ADD COLUMN account VARCHAR(255) NOT NULL DEFAULT '' AFTER site")
                cursor.execute("ALTER TABLE login_states DROP INDEX site")
                cursor.execute("ALTER TABLE login_states ADD UNIQUE KEY uk_site_account (site, account)")
                conn.commit()
        except Exception:
            pass
        
        cursor.close()

    # ─── Cookie Store ───

    def save_cookies(self, site, profile, cookies_list, user_agent=None, account=None):
        ts = _now_iso()
        account = account or ''
        cookies_json = json.dumps(cookies_list, ensure_ascii=False)
        self._exec("""
            INSERT INTO cookie_stores (site, account, profile, cookies_json, user_agent, is_valid, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
            ON DUPLICATE KEY UPDATE
                profile=VALUES(profile),
                cookies_json=VALUES(cookies_json),
                user_agent=VALUES(user_agent),
                is_valid=1,
                updated_at=VALUES(updated_at)
        """, (site, account, profile, cookies_json, user_agent, ts, ts), commit=True)

    def load_cookies(self, site, account=None):
        if account:
            row = self._exec(
                "SELECT cookies_json FROM cookie_stores WHERE site = %s AND account = %s",
                (site, account), fetch="one"
            )
        else:
            # If no account specified, try exact empty match first, then any
            row = self._exec(
                "SELECT cookies_json FROM cookie_stores WHERE site = %s AND account = ''",
                (site,), fetch="one"
            )
            if not row:
                row = self._exec(
                    "SELECT cookies_json FROM cookie_stores WHERE site = %s ORDER BY updated_at DESC LIMIT 1",
                    (site,), fetch="one"
                )
        if row:
            return json.loads(row["cookies_json"])
        return None

    def list_cookie_sites(self, account=None):
        if account:
            rows = self._exec(
                "SELECT site, account, profile, is_valid, updated_at FROM cookie_stores WHERE account = %s ORDER BY updated_at DESC",
                (account,), fetch="all"
            )
        else:
            rows = self._exec(
                "SELECT site, account, profile, is_valid, updated_at FROM cookie_stores ORDER BY updated_at DESC",
                fetch="all"
            )
        return rows or []

    def delete_cookies(self, site, account=None):
        if account:
            self._exec("DELETE FROM cookie_stores WHERE site = %s AND account = %s", (site, account), commit=True)
        else:
            self._exec("DELETE FROM cookie_stores WHERE site = %s", (site,), commit=True)

    def update_cookie_validity(self, site, is_valid, account=None):
        if account:
            self._exec(
                "UPDATE cookie_stores SET is_valid = %s, updated_at = %s WHERE site = %s AND account = %s",
                (1 if is_valid else 0, _now_iso(), site, account), commit=True
            )
        else:
            self._exec(
                "UPDATE cookie_stores SET is_valid = %s, updated_at = %s WHERE site = %s",
                (1 if is_valid else 0, _now_iso(), site), commit=True
            )

    def get_cookie_store(self, site, account=None):
        if account:
            return self._exec(
                "SELECT * FROM cookie_stores WHERE site = %s AND account = %s",
                (site, account), fetch="one"
            )
        else:
            row = self._exec(
                "SELECT * FROM cookie_stores WHERE site = %s AND account = ''",
                (site,), fetch="one"
            )
            if not row:
                row = self._exec(
                    "SELECT * FROM cookie_stores WHERE site = %s ORDER BY updated_at DESC LIMIT 1",
                    (site,), fetch="one"
                )
            return row

    # ─── Request History ───

    def save_request(self, url, method="GET", headers=None, body=None,
                     status_code=None, response_preview=None, via="http", site=None):
        self._exec("""
            INSERT INTO request_history (url, method, headers_json, body_json, status_code, response_preview, via, site, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            url, method,
            json.dumps(headers, ensure_ascii=False) if headers else None,
            json.dumps(body, ensure_ascii=False) if body and not isinstance(body, str) else body,
            status_code,
            (response_preview[:2000] if response_preview else None),
            via, site, _now_iso()
        ), commit=True)

    def list_requests(self, limit=20, site=None):
        if site:
            rows = self._exec(
                "SELECT id, url, method, status_code, via, site, timestamp FROM request_history WHERE site = %s ORDER BY id DESC LIMIT %s",
                (site, limit), fetch="all"
            )
        else:
            rows = self._exec(
                "SELECT id, url, method, status_code, via, site, timestamp FROM request_history ORDER BY id DESC LIMIT %s",
                (limit,), fetch="all"
            )
        return rows or []

    def get_request(self, req_id):
        return self._exec(
            "SELECT * FROM request_history WHERE id = %s",
            (req_id,), fetch="one"
        )

    # ─── Login State ───

    def update_login_state(self, site, is_logged_in, check_url=None, check_selector=None, account=None):
        ts = _now_iso()
        account = account or ''
        last_login = ts if is_logged_in else None
        self._exec("""
            INSERT INTO login_states (site, account, is_logged_in, check_url, check_selector, last_check, last_login)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_logged_in=VALUES(is_logged_in),
                check_url=COALESCE(VALUES(check_url), check_url),
                check_selector=COALESCE(VALUES(check_selector), check_selector),
                last_check=VALUES(last_check),
                last_login=COALESCE(VALUES(last_login), last_login)
        """, (site, account, 1 if is_logged_in else 0, check_url, check_selector, ts, last_login),
            commit=True)

    def get_login_state(self, site, account=None):
        if account:
            return self._exec(
                "SELECT * FROM login_states WHERE site = %s AND account = %s",
                (site, account), fetch="one"
            )
        else:
            row = self._exec(
                "SELECT * FROM login_states WHERE site = %s AND account = ''",
                (site,), fetch="one"
            )
            if not row:
                row = self._exec(
                    "SELECT * FROM login_states WHERE site = %s ORDER BY last_check DESC LIMIT 1",
                    (site,), fetch="one"
                )
            return row
