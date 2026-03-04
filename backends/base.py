"""
Browser Pilot - Database Backend Abstract Base Class
Defines the interface that both SQLite and MySQL backends must implement.
Supports account-based cookie storage for multi-account scenarios.
"""
from abc import ABC, abstractmethod


class DatabaseBackend(ABC):

    @abstractmethod
    def ensure_schema(self):
        ...

    # ─── Cookie Store ───

    @abstractmethod
    def save_cookies(self, site, profile, cookies_list, user_agent=None, account=None):
        """Save cookies with optional account identifier."""
        ...

    @abstractmethod
    def load_cookies(self, site, account=None):
        """Load cookies, optionally filtered by account."""
        ...

    @abstractmethod
    def list_cookie_sites(self, account=None):
        """List all sites with stored cookies, optionally filtered by account."""
        ...

    @abstractmethod
    def delete_cookies(self, site, account=None):
        """Delete cookies for site, optionally filtered by account."""
        ...

    @abstractmethod
    def update_cookie_validity(self, site, is_valid, account=None):
        """Update validity status for site cookies."""
        ...

    @abstractmethod
    def get_cookie_store(self, site, account=None):
        """Get full cookie store record."""
        ...

    # ─── Request History ───

    @abstractmethod
    def save_request(self, url, method="GET", headers=None, body=None,
                     status_code=None, response_preview=None, via="http", site=None):
        ...

    @abstractmethod
    def list_requests(self, limit=20, site=None):
        ...

    @abstractmethod
    def get_request(self, req_id):
        ...

    # ─── Login State ───

    @abstractmethod
    def update_login_state(self, site, is_logged_in, check_url=None, check_selector=None, account=None):
        """Update login state with optional account."""
        ...

    @abstractmethod
    def get_login_state(self, site, account=None):
        """Get login state, optionally filtered by account."""
        ...
