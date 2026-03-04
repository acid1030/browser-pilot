#!/usr/bin/env python3
"""
Browser Pilot - Playwright Supplement CLI
Multi-account cookie persistence, cookie-driven HTTP requests, CDP network
interception, CAPTCHA recognition, and request history.

Use alongside Playwright for capabilities it lacks:
- Cookie database with multi-account support
- Direct HTTP requests with stored cookies (no browser)
- CDP full network interception (request + response bodies)
- CAPTCHA image OCR and slider gap detection
- Request history and replay

Usage:
    python browser_pilot.py <command> [options]

Commands:
    fetch      Fetch data via HTTP or CDP
    intercept  CDP network request interception
    cookies    Cookie management (list/export/import/delete/check/chrome/sync)
    chrome     Chrome profile management (copy/list/cleanup)
    history    Request history (list/replay)
    captcha    CAPTCHA recognition (recognize/find-gap/trajectory)
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
import cookie_manager as cm
import http_client as hc
import interceptor as icp
import captcha_solver as captcha

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


# ─── Command: fetch ───

def cmd_fetch(args):
    """Fetch data via HTTP or CDP (Playwright-based interception)."""
    try:
        if args.cdp:
            # Browser-based interception using Playwright
            site = args.use_cookies or cm.extract_site(args.url)
            account = getattr(args, 'account', None)
            
            results = icp.intercept_page(
                page_url=args.url,
                url_pattern=args.pattern or ".*",
                wait_seconds=args.wait or 15,
                site=site,
                account=account,
                headless=True
            )
            
            for r in results:
                db.save_request(
                    url=r["url"], method=r.get("method", "GET"),
                    headers=r.get("request_headers"),
                    status_code=r.get("status"),
                    response_preview=r.get("body", "")[:2000],
                    via="playwright", site=site,
                )

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                output_json({"message": f"Saved {len(results)} responses to {args.output}"})
            else:
                output_json({"count": len(results), "results": results})
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
    """Network interception using Playwright."""
    try:
        site = cm.extract_site(args.url)
        account = getattr(args, 'account', None)
        
        results = icp.intercept_page(
            page_url=args.url,
            url_pattern=args.pattern,
            wait_seconds=args.wait,
            site=site,
            account=account,
            headless=args.headless
        )

        for r in results:
            db.save_request(
                url=r["url"], method=r.get("method", "GET"),
                headers=r.get("request_headers"),
                body=r.get("post_data"),
                status_code=r.get("status"),
                response_preview=r.get("body", "")[:2000],
                via="playwright", site=site,
            )

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            output_json({"message": f"Intercepted {len(results)} requests, saved to {args.output}"})
        else:
            output_json({"count": len(results), "results": results})

    except Exception as e:
        output_error(e)


# ─── Command: cookies ───

def cmd_cookies(args):
    """Cookie management."""
    try:
        action = args.cookie_action
        account = getattr(args, 'account', None)

        if action == "list":
            sites = db.list_cookie_sites(account=account)
            if args.site:
                sites = [s for s in sites if args.site in s["site"]]
            output_json({"cookies": sites})

        elif action == "export":
            if not args.site:
                output_error("--site is required for export")
                return
            store = db.get_cookie_store(args.site, account=account)
            if not store:
                output_error(f"No cookies found for {args.site}" + (f" (account: {account})" if account else ""))
                return
            if args.format == "header":
                header_str = cm.cookies_as_header_string(args.site, account=account)
                output_json({"cookie_header": header_str, "account": account})
            elif args.format == "playwright-json":
                pw_data = cm.export_as_playwright_json(args.site, account=account)
                output_json(pw_data)
            else:
                cookies = json.loads(store["cookies_json"])
                output_json({"site": args.site, "account": store.get("account"), "cookies": cookies})

        elif action == "import":
            if not args.site or not args.file:
                output_error("--site and --file are required for import")
                return
            with open(args.file, "r") as f:
                cookies = json.load(f)
            db.save_cookies(args.site, args.profile or "default", cookies, account=account)
            output_json({"message": f"Imported {len(cookies)} cookies for {args.site}", "account": account})

        elif action == "delete":
            if not args.site:
                output_error("--site is required for delete")
                return
            db.delete_cookies(args.site, account=account)
            output_json({"message": f"Deleted cookies for {args.site}", "account": account})

        elif action == "check":
            if not args.site or not args.url:
                output_error("--site and --url are required for check")
                return
            is_valid = cm.check_validity(args.site, args.url, account=account)
            output_json({"site": args.site, "is_valid": is_valid, "account": account})

        elif action == "chrome":
            # Import cookies from local Chrome browser
            if not args.site:
                output_error("--site is required for chrome import")
                return
            result = cm.import_from_chrome(
                args.site,
                chrome_profile=args.chrome_profile or "Default",
                db_profile=args.profile or "default",
                account=account
            )
            output_json(result)

        elif action == "profiles":
            # List available Chrome profiles
            profiles = cm.list_chrome_profiles()
            output_json({"chrome_profiles": profiles})

        elif action == "sync-from-playwright":
            # Import cookies from Playwright JSON file
            if not args.file:
                output_error("--file is required for sync-from-playwright")
                return
            result = cm.save_from_playwright_json(
                file_path=args.file,
                site=getattr(args, 'site', None),
                profile=getattr(args, 'profile', 'default'),
                account=account
            )
            output_json(result)

        elif action == "sync-to-playwright":
            # Export cookies in Playwright format
            if not args.site:
                output_error("--site is required for sync-to-playwright")
                return
            pw_data = cm.export_as_playwright_json(args.site, account=account)
            if not pw_data["cookies"]:
                output_error(f"No cookies found for {args.site}" + (f" (account: {account})" if account else ""))
                return
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(pw_data, f, ensure_ascii=False, indent=2)
                output_json({"message": f"Exported {len(pw_data['cookies'])} cookies to {args.output}", "format": "playwright-json"})
            else:
                output_json(pw_data)

    except Exception as e:
        output_error(e)


# ─── Command: chrome ───

def cmd_chrome(args):
    """Chrome profile management - copy, list, cleanup."""
    import chrome_cookies
    
    try:
        action = args.chrome_action
        
        if action == "copy":
            result = chrome_cookies.copy_chrome_profile_full(
                chrome_profile=args.chrome_profile or "Default",
                force=args.force
            )
            output_json(result)
        
        elif action == "list-copied":
            profiles = chrome_cookies.get_copied_profiles()
            output_json({"copied_profiles": profiles})
        
        elif action == "list-chrome":
            profiles = chrome_cookies.list_chrome_profiles()
            output_json({"chrome_profiles": profiles})
        
        elif action == "cleanup":
            keep = args.keep or 3
            removed = chrome_cookies.cleanup_old_profiles(keep_count=keep)
            output_json({"message": f"Removed {removed} old profile copies", "kept": keep})
        
        elif action == "check":
            if not args.site:
                output_error("--site is required")
                return
            has_cookies = chrome_cookies.has_chrome_cookies(args.site, args.chrome_profile or "Default")
            output_json({
                "site": args.site,
                "has_cookies": has_cookies,
                "chrome_profile": args.chrome_profile or "Default"
            })
        
        else:
            output_json({"error": f"Unknown chrome action: {action}"}, success=False)
    
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


# ─── Command: browse ───

def cmd_browse(args):
    """Self-contained Playwright browser operations with cookie persistence."""
    from playwright_browser import PlaywrightBrowser
    
    try:
        action = args.browse_action
        site = args.site
        account = getattr(args, 'account', None)
        
        if action == "open":
            # Open URL with auto cookie sync
            with PlaywrightBrowser(
                site=site,
                account=account,
                headless=getattr(args, 'headless', False)
            ) as browser:
                browser.goto(args.url, wait_until=getattr(args, 'wait_until', 'load'))
                
                result = {"url": args.url, "site": site}
                
                if getattr(args, 'wait', None):
                    import time
                    time.sleep(args.wait)
                
                if getattr(args, 'snapshot', False):
                    snapshot = browser.snapshot()
                    result["snapshot"] = snapshot
                
                if getattr(args, 'screenshot', None):
                    browser.screenshot(args.screenshot)
                    result["screenshot"] = args.screenshot
                
                output_json(result)
        
        elif action == "extract":
            # Extract data using JavaScript
            if not args.script:
                output_error("--script is required for extract")
                return
            
            with PlaywrightBrowser(
                site=site,
                account=account,
                headless=getattr(args, 'headless', True)
            ) as browser:
                browser.goto(args.url)
                
                if getattr(args, 'wait', None):
                    import time
                    time.sleep(args.wait)
                
                # Execute extraction script
                data = browser.evaluate(args.script)
                
                result = {"url": args.url, "data": data}
                
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    result["saved_to"] = args.output
                
                output_json(result)
        
        elif action == "intercept-api":
            # Intercept API responses while browsing
            pattern = args.pattern or ".*"
            wait = getattr(args, 'wait', 30)
            
            results = icp.intercept_page(
                page_url=args.url,
                url_pattern=pattern,
                wait_seconds=wait,
                site=site,
                account=account,
                headless=getattr(args, 'headless', False)
            )
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                output_json({"message": f"Captured {len(results)} responses", "saved_to": args.output})
            else:
                output_json({"count": len(results), "results": results})
        
        else:
            output_json({"error": f"Unknown browse action: {action}"}, success=False)
    
    except Exception as e:
        output_error(e)


# ─── Command: captcha ───

def cmd_captcha(args):
    """CAPTCHA recognition and trajectory generation."""
    try:
        action = args.captcha_action

        if action == "check":
            deps = captcha.check_dependencies()
            output_json(deps)

        elif action == "recognize":
            if args.file:
                with open(args.file, "rb") as f:
                    image_data = f.read()
                result = captcha.recognize(image_data)
                output_json(result)
            elif args.image_url:
                solver = captcha.get_solver(args.api_key, args.api_provider or "2captcha")
                result = solver.recognize_image_from_url(args.image_url)
                output_json(result)
            else:
                output_json({"error": "--file or --image-url required"}, success=False)

        elif action == "find-gap":
            if not args.file:
                output_error("--file is required (background image)")
                return
            with open(args.file, "rb") as f:
                bg_data = f.read()
            slider_data = None
            if args.slider_file:
                with open(args.slider_file, "rb") as f:
                    slider_data = f.read()
            result = captcha.find_gap(bg_data, slider_data)
            output_json(result)

        elif action == "trajectory":
            if not args.distance:
                output_error("--distance is required")
                return
            result = captcha.generate_trajectory(
                distance=args.distance,
                duration=args.duration or 0.5,
                points=args.points or 20
            )
            output_json(result)

        else:
            output_json({"error": f"Unknown captcha action: {action}"}, success=False)

    except Exception as e:
        output_error(e)


# ─── Argument Parser ───

def build_parser():
    parser = argparse.ArgumentParser(
        description="Browser Pilot - Playwright supplement for cookies, HTTP, CDP, and CAPTCHA"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── fetch ──
    p_fetch = subparsers.add_parser("fetch", help="Fetch data via HTTP or CDP")
    p_fetch.add_argument("--url", required=True, help="Target URL")
    p_fetch.add_argument("--method", default="GET", help="HTTP method")
    p_fetch.add_argument("--use-cookies", help="Site name to load cookies from")
    p_fetch.add_argument("--account", help="Account identifier for cookie loading")
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
    p_cl.add_argument("--account", help="Filter by account identifier")

    p_ce = p_cookies_sub.add_parser("export", help="Export cookies")
    p_ce.add_argument("--site", required=True, help="Site to export")
    p_ce.add_argument("--account", help="Account identifier")
    p_ce.add_argument("--format", choices=["json", "header", "playwright-json"], default="json")

    p_ci = p_cookies_sub.add_parser("import", help="Import cookies from file")
    p_ci.add_argument("--site", required=True, help="Site name")
    p_ci.add_argument("--file", required=True, help="JSON file path")
    p_ci.add_argument("--profile", default="default")
    p_ci.add_argument("--account", help="Account identifier")

    p_cd = p_cookies_sub.add_parser("delete", help="Delete stored cookies")
    p_cd.add_argument("--site", required=True, help="Site to delete")
    p_cd.add_argument("--account", help="Account identifier")

    p_cc = p_cookies_sub.add_parser("check", help="Check cookie validity")
    p_cc.add_argument("--site", required=True, help="Site to check")
    p_cc.add_argument("--url", required=True, help="URL to test with cookies")
    p_cc.add_argument("--account", help="Account identifier")

    p_cchr = p_cookies_sub.add_parser("chrome", help="Import from Chrome browser")
    p_cchr.add_argument("--site", required=True, help="Site to import cookies for")
    p_cchr.add_argument("--chrome-profile", default="Default", help="Chrome profile name")
    p_cchr.add_argument("--profile", default="default", help="Database profile")
    p_cchr.add_argument("--account", help="Account identifier")

    p_cprof = p_cookies_sub.add_parser("profiles", help="List Chrome profiles")

    p_sync_from = p_cookies_sub.add_parser("sync-from-playwright", help="Import cookies from Playwright JSON")
    p_sync_from.add_argument("--file", required=True, help="Playwright cookies JSON file path")
    p_sync_from.add_argument("--site", help="Site to save under (auto-groups by domain if omitted)")
    p_sync_from.add_argument("--account", help="Account identifier")
    p_sync_from.add_argument("--profile", default="default", help="Database profile")

    p_sync_to = p_cookies_sub.add_parser("sync-to-playwright", help="Export cookies in Playwright format")
    p_sync_to.add_argument("--site", required=True, help="Site to export")
    p_sync_to.add_argument("--account", help="Account identifier")
    p_sync_to.add_argument("--output", help="Output file path (stdout if omitted)")

    # ── chrome ──
    p_chrome = subparsers.add_parser("chrome", help="Chrome profile management")
    p_chrome_sub = p_chrome.add_subparsers(dest="chrome_action")

    p_chr_copy = p_chrome_sub.add_parser("copy", help="Copy Chrome profile directory")
    p_chr_copy.add_argument("--chrome-profile", default="Default", help="Chrome profile to copy")
    p_chr_copy.add_argument("--force", action="store_true", help="Force re-copy")

    p_chr_list = p_chrome_sub.add_parser("list-copied", help="List copied Chrome profiles")

    p_chr_list_chrome = p_chrome_sub.add_parser("list-chrome", help="List available Chrome profiles")

    p_chr_cleanup = p_chrome_sub.add_parser("cleanup", help="Remove old copied profiles")
    p_chr_cleanup.add_argument("--keep", type=int, default=3, help="Number of copies to keep")

    p_chr_check = p_chrome_sub.add_parser("check", help="Check if Chrome has cookies for a site")
    p_chr_check.add_argument("--site", required=True, help="Site to check")
    p_chr_check.add_argument("--chrome-profile", default="Default", help="Chrome profile to check")

    # ── history ──
    p_history = subparsers.add_parser("history", help="Request history")
    p_history_sub = p_history.add_subparsers(dest="history_action")

    p_hl = p_history_sub.add_parser("list", help="List recent requests")
    p_hl.add_argument("--limit", type=int, default=20, help="Number of results")
    p_hl.add_argument("--site", help="Filter by site")

    p_hr = p_history_sub.add_parser("replay", help="Replay a request")
    p_hr.add_argument("--id", type=int, required=True, help="Request ID to replay")
    p_hr.add_argument("--output", help="Save response to file")

    # ── browse ──
    p_browse = subparsers.add_parser("browse", help="Playwright browser with cookie persistence")
    p_browse_sub = p_browse.add_subparsers(dest="browse_action")

    p_br_open = p_browse_sub.add_parser("open", help="Open URL with auto cookie sync")
    p_br_open.add_argument("--url", required=True, help="URL to open")
    p_br_open.add_argument("--site", required=True, help="Site name for cookie storage")
    p_br_open.add_argument("--account", help="Account identifier")
    p_br_open.add_argument("--headless", action="store_true", help="Run headless")
    p_br_open.add_argument("--wait", type=float, help="Wait seconds after page load")
    p_br_open.add_argument("--wait-until", default="load", choices=["load", "domcontentloaded", "networkidle"], help="Wait until event")
    p_br_open.add_argument("--screenshot", help="Save screenshot to file")
    p_br_open.add_argument("--snapshot", action="store_true", help="Return accessibility snapshot")

    p_br_extract = p_browse_sub.add_parser("extract", help="Extract data using JavaScript")
    p_br_extract.add_argument("--url", required=True, help="URL to open")
    p_br_extract.add_argument("--site", required=True, help="Site name for cookie storage")
    p_br_extract.add_argument("--script", required=True, help="JavaScript to execute (return value is captured)")
    p_br_extract.add_argument("--account", help="Account identifier")
    p_br_extract.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    p_br_extract.add_argument("--wait", type=float, help="Wait seconds before extraction")
    p_br_extract.add_argument("--output", help="Save extracted data to file")

    p_br_intercept = p_browse_sub.add_parser("intercept-api", help="Intercept API responses")
    p_br_intercept.add_argument("--url", required=True, help="Page URL to open")
    p_br_intercept.add_argument("--site", required=True, help="Site name for cookie storage")
    p_br_intercept.add_argument("--pattern", help="URL regex pattern to match (default: .*)")
    p_br_intercept.add_argument("--account", help="Account identifier")
    p_br_intercept.add_argument("--headless", action="store_true", help="Run headless")
    p_br_intercept.add_argument("--wait", type=int, default=30, help="Listen duration (seconds)")
    p_br_intercept.add_argument("--output", help="Save results to file")

    # ── captcha ──
    p_captcha = subparsers.add_parser("captcha", help="CAPTCHA recognition and trajectory")
    p_captcha_sub = p_captcha.add_subparsers(dest="captcha_action")

    p_cap_check = p_captcha_sub.add_parser("check", help="Check CAPTCHA dependencies")

    p_cap_rec = p_captcha_sub.add_parser("recognize", help="Recognize image CAPTCHA")
    p_cap_rec.add_argument("--file", help="Image file path")
    p_cap_rec.add_argument("--image-url", help="Image URL")
    p_cap_rec.add_argument("--api-key", help="API key for fallback service")
    p_cap_rec.add_argument("--api-provider", choices=["2captcha", "anticaptcha"], default="2captcha")

    p_cap_gap = p_captcha_sub.add_parser("find-gap", help="Find gap position in slider CAPTCHA")
    p_cap_gap.add_argument("--file", required=True, help="Background image file")
    p_cap_gap.add_argument("--slider-file", help="Slider piece image file (optional)")

    p_cap_traj = p_captcha_sub.add_parser("trajectory", help="Generate human-like mouse trajectory")
    p_cap_traj.add_argument("--distance", type=int, required=True, help="Distance to move (pixels)")
    p_cap_traj.add_argument("--duration", type=float, default=0.5, help="Duration (seconds)")
    p_cap_traj.add_argument("--points", type=int, default=20, help="Number of trajectory points")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "fetch": cmd_fetch,
        "intercept": cmd_intercept,
        "cookies": cmd_cookies,
        "chrome": cmd_chrome,
        "history": cmd_history,
        "browse": cmd_browse,
        "captcha": cmd_captcha,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
