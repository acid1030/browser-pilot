"""
Browser Pilot - MySQL Backend
Uses mysql-connector-python with connection pooling.
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
    site VARCHAR(255) UNIQUE NOT NULL,
    profile VARCHAR(255) DEFAULT 'default',
    cookies_json LONGTEXT NOT NULL,
    user_agent VARCHAR(512),
    is_valid TINYINT(1) DEFAULT 1,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL
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
    site VARCHAR(255) UNIQUE NOT NULL,
    is_logged_in TINYINT(1) DEFAULT 0,
    check_url VARCHAR(512),
    check_selector VARCHAR(512),
    last_check VARCHAR(32),
    last_login VARCHAR(32)
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
        finally:
            conn.close()

    # ─── Cookie Store ───

    def save_cookies(self, site, profile, cookies_list, user_agent=None):
        ts = _now_iso()
        cookies_json = json.dumps(cookies_list, ensure_ascii=False)
        self._exec("""
            INSERT INTO cookie_stores (site, profile, cookies_json, user_agent, is_valid, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
            ON DUPLICATE KEY UPDATE
                profile=VALUES(profile),
                cookies_json=VALUES(cookies_json),
                user_agent=VALUES(user_agent),
                is_valid=1,
                updated_at=VALUES(updated_at)
        """, (site, profile, cookies_json, user_agent, ts, ts), commit=True)

    def load_cookies(self, site):
        row = self._exec(
            "SELECT cookies_json FROM cookie_stores WHERE site = %s",
            (site,), fetch="one"
        )
        if row:
            return json.loads(row["cookies_json"])
        return None

    def list_cookie_sites(self):
        rows = self._exec(
            "SELECT site, profile, is_valid, updated_at FROM cookie_stores ORDER BY updated_at DESC",
            fetch="all"
        )
        return rows or []

    def delete_cookies(self, site):
        self._exec("DELETE FROM cookie_stores WHERE site = %s", (site,), commit=True)

    def update_cookie_validity(self, site, is_valid):
        self._exec(
            "UPDATE cookie_stores SET is_valid = %s, updated_at = %s WHERE site = %s",
            (1 if is_valid else 0, _now_iso(), site), commit=True
        )

    def get_cookie_store(self, site):
        return self._exec(
            "SELECT * FROM cookie_stores WHERE site = %s",
            (site,), fetch="one"
        )

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

    def update_login_state(self, site, is_logged_in, check_url=None, check_selector=None):
        ts = _now_iso()
        last_login = ts if is_logged_in else None
        self._exec("""
            INSERT INTO login_states (site, is_logged_in, check_url, check_selector, last_check, last_login)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_logged_in=VALUES(is_logged_in),
                check_url=COALESCE(VALUES(check_url), check_url),
                check_selector=COALESCE(VALUES(check_selector), check_selector),
                last_check=VALUES(last_check),
                last_login=COALESCE(VALUES(last_login), last_login)
        """, (site, 1 if is_logged_in else 0, check_url, check_selector, ts, last_login),
            commit=True)

    def get_login_state(self, site):
        return self._exec(
            "SELECT * FROM login_states WHERE site = %s",
            (site,), fetch="one"
        )
