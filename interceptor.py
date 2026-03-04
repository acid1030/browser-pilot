"""
Browser Pilot - CDP Network Interceptor
Captures XHR/Fetch requests via Chrome DevTools Protocol performance logs.
"""
import json
import re
import time
import logging

from driver import execute_cdp, get_performance_logs

log = logging.getLogger("browser-pilot")


def intercept_page(driver, page_url, url_pattern, wait_seconds=30, load_cookies_site=None):
    """
    Load a page and intercept network requests matching url_pattern.
    Uses Performance Log polling to capture Network events.

    Returns list of intercepted responses:
    [{"url": str, "request_id": str, "status": int, "headers": dict, "body": str}, ...]
    """
    # Ensure Network/Page are enabled
    execute_cdp(driver, "Network.enable", {})
    execute_cdp(driver, "Page.enable", {})

    # Drain any existing logs
    try:
        driver.get_log("performance")
    except Exception:
        pass

    # Navigate to the page
    driver.get(page_url)

    pattern = re.compile(url_pattern)
    intercepted = []
    request_map = {}  # requestId -> request info
    response_map = {}  # requestId -> response info

    start = time.time()
    while time.time() - start < wait_seconds:
        time.sleep(1)

        events = get_performance_logs(driver)
        for event in events:
            method = event["method"]
            params = event["params"]

            if method == "Network.requestWillBeSent":
                req_url = params.get("request", {}).get("url", "")
                request_id = params.get("requestId", "")
                if pattern.search(req_url):
                    request_map[request_id] = {
                        "url": req_url,
                        "method": params.get("request", {}).get("method", "GET"),
                        "headers": params.get("request", {}).get("headers", {}),
                        "post_data": params.get("request", {}).get("postData", ""),
                    }

            elif method == "Network.responseReceived":
                request_id = params.get("requestId", "")
                if request_id in request_map:
                    resp = params.get("response", {})
                    response_map[request_id] = {
                        "status": resp.get("status", 0),
                        "headers": resp.get("headers", {}),
                        "mime_type": resp.get("mimeType", ""),
                    }

            elif method == "Network.loadingFinished":
                request_id = params.get("requestId", "")
                if request_id in request_map and request_id in response_map:
                    # Fetch response body
                    body = get_response_body(driver, request_id)
                    req_info = request_map[request_id]
                    resp_info = response_map[request_id]

                    intercepted.append({
                        "url": req_info["url"],
                        "request_id": request_id,
                        "method": req_info["method"],
                        "request_headers": req_info["headers"],
                        "post_data": req_info["post_data"],
                        "status": resp_info["status"],
                        "response_headers": resp_info["headers"],
                        "mime_type": resp_info["mime_type"],
                        "body": body,
                    })

                    # Clean up
                    del request_map[request_id]
                    del response_map[request_id]

    log.info(f"Intercepted {len(intercepted)} requests matching '{url_pattern}'")
    return intercepted


def get_response_body(driver, request_id):
    """Fetch response body for a given requestId via CDP."""
    result = execute_cdp(driver, "Network.getResponseBody", {"requestId": request_id})
    if result:
        body = result.get("body", "")
        if result.get("base64Encoded"):
            import base64
            try:
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            except Exception:
                pass
        return body
    return ""


def intercept_xhr(driver, page_url, url_pattern, wait_seconds=15):
    """
    Simplified interception: load page, wait, and return matched XHR responses.
    Returns only the response bodies as a list.
    """
    results = intercept_page(driver, page_url, url_pattern, wait_seconds)
    return [r["body"] for r in results if r.get("body")]
