#!/usr/bin/env python3
"""
Browser Pilot - Main CLI
Selenium-based browser automation with CDP interception, cookie persistence,
and auto-login detection for OpenClaw.

Usage:
    python browser_pilot.py <command> [options]

Commands:
    open       Open browser to URL with optional cookie restore
    login      Handle login flow (auto or manual)
    fetch      Fetch data via HTTP or CDP
    intercept  CDP network request interception
    cookies    Cookie management (list/export/import/delete/check)
    history    Request history (list/replay)
    dom        DOM operations (click/type/extract/screenshot)
"""
import sys
import os
import json
import argparse
import logging
import time

# Add skill directory to path for relative imports
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SKILL_DIR))

# Use direct imports (not relative) for CLI execution
sys.path.insert(0, SKILL_DIR)
import db
import driver as drv
import cookie_manager as cm
import http_client as hc
import interceptor as icp

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("browser-pilot")


def output_json(data, success=True):
    """Unified JSON output."""
    result = {"success": success}
    if isinstance(data, dict):
        result.update(data)
    else:
        result["data"] = data
    print(json.dumps(result, ensure_ascii=False, indent=2))


def output_error(msg):
    output_json({"error": str(msg)}, success=False)


# ─── Command: open ───

def cmd_open(args):
    """Open browser to URL, optionally with stored cookies."""
    driver = None
    try:
        driver = drv.create_driver(profile=args.profile, headless=args.headless)
        site = cm.extract_site(args.url)

        # Try to load stored cookies
        cookies = db.load_cookies(site)
        if cookies:
            cm.load_to_driver(driver, site, args.url)
            driver.get(args.url)
            log.info(f"Opened {args.url} with stored cookies")
        else:
            driver.get(args.url)
            log.info(f"Opened {args.url} (no stored cookies)")

        if args.wait_login:
            success = cm.wait_for_login(
                driver,
                check_url=args.check_url,
                check_selector=args.check_selector,
                timeout=args.timeout,
            )
            if success:
                count = cm.save_from_driver(driver, site, args.profile)
                db.update_login_state(site, True, args.check_url, args.check_selector)
                output_json({"message": f"Login detected, saved {count} cookies", "site": site})
            else:
                output_json({"message": "Login timeout"}, success=False)
        else:
            # Keep browser open, wait for user to close
            output_json({"message": f"Browser opened at {args.url}", "site": site})
            try:
                input("Press Enter to close browser...")
            except (EOFError, KeyboardInterrupt):
                pass

    except Exception as e:
        output_error(e)
    finally:
        if driver and not args.wait_login:
            pass  # User controls when to close
        elif driver:
            drv.close_driver(driver)


# ─── Command: login ───

def cmd_login(args):
    """Handle login flow - auto or manual."""
    driver = None
    try:
        driver = drv.create_driver(profile=args.profile, headless=False)
        site = cm.extract_site(args.url)
        driver.get(args.url)
        time.sleep(2)

        if args.username and args.password:
            # Auto-login with Selenium
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            log.info(f"Auto-login to {args.url}")

            # Find and fill username
            user_selectors = [
                args.selector_user,
                "input[type='email']", "input[type='text']",
                "input[name='username']", "input[name='email']",
                "input[name='account']", "input[name='loginId']",
                "#username", "#email", "#account",
            ]
            user_el = None
            for sel in user_selectors:
                if not sel:
                    continue
                try:
                    user_el = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    break
                except Exception:
                    continue

            if not user_el:
                output_error("Could not find username input field")
                return

            user_el.clear()
            time.sleep(0.5)
            user_el.send_keys(args.username)
            time.sleep(0.5)

            # Find and fill password
            pass_selectors = [
                args.selector_pass,
                "input[type='password']",
                "input[name='password']", "input[name='pwd']",
                "#password",
            ]
            pass_el = None
            for sel in pass_selectors:
                if not sel:
                    continue
                try:
                    pass_el = driver.find_element(By.CSS_SELECTOR, sel)
                    break
                except Exception:
                    continue

            if not pass_el:
                output_error("Could not find password input field")
                return

            pass_el.clear()
            time.sleep(0.5)
            pass_el.send_keys(args.password)
            time.sleep(0.5)

            # Submit
            submit_selectors = [
                "button[type='submit']", "input[type='submit']",
                "button.login-btn", "button.submit",
                "button:not([type='button'])",
            ]
            for sel in submit_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, sel)
                    btn.click()
                    break
                except Exception:
                    continue

            log.info("Credentials submitted, waiting for login...")
            time.sleep(3)

        # Wait for login (manual or post-auto)
        success = cm.wait_for_login(
            driver,
            check_url=args.check_url,
            check_selector=args.check_selector,
            timeout=args.timeout,
        )

        if success:
            count = cm.save_from_driver(driver, site, args.profile)
            db.update_login_state(site, True, args.check_url, args.check_selector)
            output_json({"message": f"Login successful, saved {count} cookies", "site": site})
        else:
            # Save whatever cookies we have anyway
            cm.save_from_driver(driver, site, args.profile)
            db.update_login_state(site, False)
            output_json({"message": "Login detection timed out, cookies saved anyway", "site": site}, success=False)

    except Exception as e:
        output_error(e)
    finally:
        drv.close_driver(driver)


# ─── Command: fetch ───

def cmd_fetch(args):
    """Fetch data via HTTP or CDP."""
    try:
        if args.cdp:
            # Browser-based CDP fetch
            driver = drv.create_driver(profile=args.profile, headless=True)
            try:
                site = cm.extract_site(args.url)
                if args.use_cookies:
                    cm.load_to_driver(driver, args.use_cookies, args.url)

                results = icp.intercept_page(driver, args.url, args.pattern or ".*", args.wait or 15)
                for r in results:
                    db.save_request(
                        url=r["url"], method=r.get("method", "GET"),
                        headers=r.get("request_headers"),
                        status_code=r.get("status"),
                        response_preview=r.get("body", "")[:2000],
                        via="cdp", site=site,
                    )

                if args.output:
                    with open(args.output, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    output_json({"message": f"Saved {len(results)} responses to {args.output}"})
                else:
                    output_json({"count": len(results), "results": results})
            finally:
                drv.close_driver(driver)
        else:
            # Direct HTTP
            headers = json.loads(args.headers) if args.headers else None
            result = hc.do_request(
                url=args.url,
                method=args.method,
                headers=headers,
                data=args.data,
                cookies_site=args.use_cookies,
            )

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(result.get("body", ""))
                output_json({"message": f"Response saved to {args.output}", "status": result["status_code"]})
            else:
                output_json(result)

    except Exception as e:
        output_error(e)


# ─── Command: intercept ───

def cmd_intercept(args):
    """CDP network interception."""
    driver = None
    try:
        driver = drv.create_driver(profile=args.profile, headless=args.headless)
        site = cm.extract_site(args.url)

        # Load cookies if available
        cookies = db.load_cookies(site)
        if cookies:
            cm.load_to_driver(driver, site, args.url)

        results = icp.intercept_page(driver, args.url, args.pattern, args.wait)

        for r in results:
            db.save_request(
                url=r["url"], method=r.get("method", "GET"),
                headers=r.get("request_headers"),
                body=r.get("post_data"),
                status_code=r.get("status"),
                response_preview=r.get("body", "")[:2000],
                via="cdp", site=site,
            )

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            output_json({"message": f"Intercepted {len(results)} requests, saved to {args.output}"})
        else:
            output_json({"count": len(results), "results": results})

    except Exception as e:
        output_error(e)
    finally:
        drv.close_driver(driver)


# ─── Command: cookies ───

def cmd_cookies(args):
    """Cookie management."""
    try:
        action = args.cookie_action

        if action == "list":
            sites = db.list_cookie_sites()
            if args.site:
                sites = [s for s in sites if args.site in s["site"]]
            output_json({"cookies": sites})

        elif action == "export":
            if not args.site:
                output_error("--site is required for export")
                return
            store = db.get_cookie_store(args.site)
            if not store:
                output_error(f"No cookies found for {args.site}")
                return
            if args.format == "header":
                header_str = cm.cookies_as_header_string(args.site)
                output_json({"cookie_header": header_str})
            else:
                cookies = json.loads(store["cookies_json"])
                output_json({"site": args.site, "cookies": cookies})

        elif action == "import":
            if not args.site or not args.file:
                output_error("--site and --file are required for import")
                return
            with open(args.file, "r") as f:
                cookies = json.load(f)
            db.save_cookies(args.site, args.profile or "default", cookies)
            output_json({"message": f"Imported {len(cookies)} cookies for {args.site}"})

        elif action == "delete":
            if not args.site:
                output_error("--site is required for delete")
                return
            db.delete_cookies(args.site)
            output_json({"message": f"Deleted cookies for {args.site}"})

        elif action == "check":
            if not args.site or not args.url:
                output_error("--site and --url are required for check")
                return
            is_valid = cm.check_validity(args.site, args.url)
            output_json({"site": args.site, "is_valid": is_valid})

    except Exception as e:
        output_error(e)


# ─── Command: history ───

def cmd_history(args):
    """Request history management."""
    try:
        action = args.history_action

        if action == "list":
            requests = db.list_requests(limit=args.limit, site=args.site)
            output_json({"requests": requests})

        elif action == "replay":
            if not args.id:
                output_error("--id is required for replay")
                return
            req = db.get_request(args.id)
            if not req:
                output_error(f"Request #{args.id} not found")
                return

            headers = json.loads(req["headers_json"]) if req.get("headers_json") else None
            result = hc.do_request(
                url=req["url"],
                method=req.get("method", "GET"),
                headers=headers,
                data=req.get("body_json"),
                cookies_site=req.get("site"),
            )

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(result.get("body", ""))
                output_json({"message": f"Replay response saved to {args.output}"})
            else:
                output_json(result)

    except Exception as e:
        output_error(e)


# ─── Command: dom ───

def cmd_dom(args):
    """DOM operations on a web page."""
    driver = None
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver = drv.create_driver(profile=args.profile, headless=args.headless)
        site = cm.extract_site(args.url)

        # Load cookies if available
        cookies = db.load_cookies(site)
        if cookies:
            cm.load_to_driver(driver, site, args.url)

        driver.get(args.url)
        time.sleep(args.wait or 3)

        # Determine selector type
        by = By.XPATH if args.selector.startswith("//") or args.selector.startswith("(") else By.CSS_SELECTOR

        if args.action == "click":
            el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by, args.selector)))
            el.click()
            time.sleep(1)
            output_json({"message": f"Clicked element: {args.selector}"})

        elif args.action == "type":
            el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((by, args.selector)))
            el.clear()
            el.send_keys(args.value or "")
            output_json({"message": f"Typed into element: {args.selector}"})

        elif args.action == "extract":
            elements = driver.find_elements(by, args.selector)
            extracted = []
            for el in elements:
                extracted.append({
                    "text": el.text,
                    "tag": el.tag_name,
                    "html": el.get_attribute("innerHTML")[:500],
                })
            output_json({"count": len(extracted), "elements": extracted})

        elif args.action == "screenshot":
            output_path = args.output or "/tmp/browser_pilot_screenshot.png"
            driver.save_screenshot(output_path)
            output_json({"message": f"Screenshot saved to {output_path}"})

        # Save cookies after any DOM operation
        cm.save_from_driver(driver, site, args.profile)

    except Exception as e:
        output_error(e)
    finally:
        if args.action != "screenshot" or not args.keep_open:
            drv.close_driver(driver)


# ─── Argument Parser ───

def build_parser():
    parser = argparse.ArgumentParser(
        description="Browser Pilot - Selenium browser automation with CDP"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── open ──
    p_open = subparsers.add_parser("open", help="Open browser to URL")
    p_open.add_argument("--url", required=True, help="Target URL")
    p_open.add_argument("--profile", default="default", help="Browser profile name")
    p_open.add_argument("--headless", action="store_true", help="Run headless")
    p_open.add_argument("--wait-login", action="store_true", help="Wait for login")
    p_open.add_argument("--check-url", help="URL to verify login status")
    p_open.add_argument("--check-selector", help="CSS selector indicating logged-in state")
    p_open.add_argument("--timeout", type=int, default=300, help="Login wait timeout (seconds)")

    # ── login ──
    p_login = subparsers.add_parser("login", help="Handle login flow")
    p_login.add_argument("--url", required=True, help="Login page URL")
    p_login.add_argument("--username", help="Username/email for auto-login")
    p_login.add_argument("--password", help="Password for auto-login")
    p_login.add_argument("--selector-user", help="CSS selector for username input")
    p_login.add_argument("--selector-pass", help="CSS selector for password input")
    p_login.add_argument("--check-url", help="URL to verify login")
    p_login.add_argument("--check-selector", help="Selector indicating logged-in state")
    p_login.add_argument("--profile", default="default", help="Browser profile")
    p_login.add_argument("--timeout", type=int, default=300, help="Wait timeout")

    # ── fetch ──
    p_fetch = subparsers.add_parser("fetch", help="Fetch data via HTTP or CDP")
    p_fetch.add_argument("--url", required=True, help="Target URL")
    p_fetch.add_argument("--method", default="GET", help="HTTP method")
    p_fetch.add_argument("--use-cookies", help="Site name to load cookies from")
    p_fetch.add_argument("--headers", help="JSON headers string")
    p_fetch.add_argument("--data", help="POST data (JSON string)")
    p_fetch.add_argument("--cdp", action="store_true", help="Use CDP interception")
    p_fetch.add_argument("--pattern", help="URL pattern for CDP interception")
    p_fetch.add_argument("--wait", type=int, help="CDP wait seconds")
    p_fetch.add_argument("--output", help="Save response to file")
    p_fetch.add_argument("--profile", default="default", help="Browser profile")

    # ── intercept ──
    p_intercept = subparsers.add_parser("intercept", help="CDP network interception")
    p_intercept.add_argument("--url", required=True, help="Page URL to load")
    p_intercept.add_argument("--pattern", required=True, help="URL regex pattern to match")
    p_intercept.add_argument("--wait", type=int, default=30, help="Listen duration (seconds)")
    p_intercept.add_argument("--profile", default="default", help="Browser profile")
    p_intercept.add_argument("--headless", action="store_true", help="Run headless")
    p_intercept.add_argument("--output", help="Save results to file")

    # ── cookies ──
    p_cookies = subparsers.add_parser("cookies", help="Cookie management")
    p_cookies_sub = p_cookies.add_subparsers(dest="cookie_action")

    p_cl = p_cookies_sub.add_parser("list", help="List stored cookies")
    p_cl.add_argument("--site", help="Filter by site")

    p_ce = p_cookies_sub.add_parser("export", help="Export cookies")
    p_ce.add_argument("--site", required=True, help="Site to export")
    p_ce.add_argument("--format", choices=["json", "header"], default="json")

    p_ci = p_cookies_sub.add_parser("import", help="Import cookies from file")
    p_ci.add_argument("--site", required=True, help="Site name")
    p_ci.add_argument("--file", required=True, help="JSON file path")
    p_ci.add_argument("--profile", default="default")

    p_cd = p_cookies_sub.add_parser("delete", help="Delete stored cookies")
    p_cd.add_argument("--site", required=True, help="Site to delete")

    p_cc = p_cookies_sub.add_parser("check", help="Check cookie validity")
    p_cc.add_argument("--site", required=True, help="Site to check")
    p_cc.add_argument("--url", required=True, help="URL to test with cookies")

    # ── history ──
    p_history = subparsers.add_parser("history", help="Request history")
    p_history_sub = p_history.add_subparsers(dest="history_action")

    p_hl = p_history_sub.add_parser("list", help="List recent requests")
    p_hl.add_argument("--limit", type=int, default=20, help="Number of results")
    p_hl.add_argument("--site", help="Filter by site")

    p_hr = p_history_sub.add_parser("replay", help="Replay a request")
    p_hr.add_argument("--id", type=int, required=True, help="Request ID to replay")
    p_hr.add_argument("--output", help="Save response to file")

    # ── dom ──
    p_dom = subparsers.add_parser("dom", help="DOM operations")
    p_dom.add_argument("--url", required=True, help="Page URL")
    p_dom.add_argument("--action", required=True, choices=["click", "type", "extract", "screenshot"])
    p_dom.add_argument("--selector", required=True, help="CSS/XPath selector")
    p_dom.add_argument("--value", help="Value for type action")
    p_dom.add_argument("--profile", default="default", help="Browser profile")
    p_dom.add_argument("--headless", action="store_true", help="Run headless")
    p_dom.add_argument("--wait", type=int, default=3, help="Page load wait (seconds)")
    p_dom.add_argument("--output", help="Output file path")
    p_dom.add_argument("--keep-open", action="store_true", help="Keep browser open")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "open": cmd_open,
        "login": cmd_login,
        "fetch": cmd_fetch,
        "intercept": cmd_intercept,
        "cookies": cmd_cookies,
        "history": cmd_history,
        "dom": cmd_dom,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
