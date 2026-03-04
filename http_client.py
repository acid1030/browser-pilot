"""
Browser Pilot - Direct HTTP Client
Makes HTTP requests using stored cookies, without launching a browser.
"""
import json
import logging

import requests

import db
from cookie_manager import load_to_requests_session, extract_site

log = logging.getLogger("browser-pilot")


def build_session(site=None):
    """Create a requests.Session pre-loaded with stored cookies."""
    session = requests.Session()
    session.headers["Accept"] = "application/json, text/html, */*"
    session.headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"

    if site:
        count = load_to_requests_session(session, site)
        log.info(f"Loaded {count} cookies for {site}")

    return session


def do_request(url, method="GET", headers=None, data=None, cookies_site=None, timeout=30):
    """
    Execute an HTTP request, optionally using stored cookies.
    Records the request in history.
    Returns dict with status, headers, body.
    """
    site = cookies_site or extract_site(url)
    session = build_session(cookies_site)

    if headers:
        if isinstance(headers, str):
            headers = json.loads(headers)
        session.headers.update(headers)

    try:
        if method.upper() == "GET":
            resp = session.get(url, timeout=timeout)
        elif method.upper() == "POST":
            content_type = session.headers.get("Content-Type", "")
            if data and isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    pass

            if isinstance(data, dict) and "json" in content_type:
                resp = session.post(url, json=data, timeout=timeout)
            elif isinstance(data, dict):
                resp = session.post(url, data=data, timeout=timeout)
            else:
                resp = session.post(url, data=data, timeout=timeout)
        else:
            resp = session.request(method.upper(), url, timeout=timeout)

        body = resp.text

        # Try Brotli decompression if needed
        if resp.headers.get("Content-Encoding") == "br":
            try:
                import brotli
                body = brotli.decompress(resp.content).decode("utf-8", errors="replace")
            except ImportError:
                pass

        result = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": body,
            "url": str(resp.url),
        }

        # Save to history
        db.save_request(
            url=url,
            method=method.upper(),
            headers=headers,
            body=data if isinstance(data, str) else json.dumps(data) if data else None,
            status_code=resp.status_code,
            response_preview=body[:2000] if body else None,
            via="http",
            site=site,
        )

        return result

    except requests.RequestException as e:
        log.error(f"HTTP request failed: {e}")
        return {
            "status_code": 0,
            "headers": {},
            "body": str(e),
            "url": url,
            "error": str(e),
        }
