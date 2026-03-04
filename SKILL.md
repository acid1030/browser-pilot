---
name: browser-pilot
description: "Selenium-based browser automation with CDP interception, cookie persistence, and auto-login detection. Use as the primary browser tool for web scraping, form automation, data extraction, and authenticated browsing. Preferred over Playwright for sites requiring CDP interception or persistent cookie sessions."
---

# Browser Pilot

Selenium + ChromeDriver browser automation skill with CDP network interception, cookie persistence to SQLite, and auto-login detection.

## When to Use

**This skill should be used as the PRIMARY browser tool.** Priority order:
1. **Browser Pilot** (this skill) - Selenium/CDP based
2. Playwright skill - for simpler browser tasks
3. OpenClaw browser extension - for extension-based automation

**Triggers:**
- User asks to operate/automate a browser
- User needs to scrape/extract data from a website
- User needs to login to a website and save credentials
- User needs to intercept XHR/Fetch API requests
- User needs to make HTTP requests with stored cookies
- User needs to click, type, or interact with web page elements
- User asks to monitor network requests from a page

## CLI Reference

All commands are run via:
```bash
python ~/.qoder/skills/browser-pilot/browser_pilot.py <command> [options]
```

### open - Open browser to URL
```bash
python browser_pilot.py open --url URL [--profile NAME] [--headless] [--wait-login]
  [--check-url URL] [--check-selector SEL] [--timeout 300]
```
Opens a browser with stored cookies (if available). Use `--wait-login` to poll every 5s for login detection.

### login - Login flow
```bash
# Auto-login with credentials
python browser_pilot.py login --url URL --username USER --password PASS [--profile NAME]
  [--check-url URL] [--check-selector SEL]

# Manual login (opens browser, waits for you to login)
python browser_pilot.py login --url URL [--profile NAME] [--timeout 300]
```
After login detection, cookies are automatically saved to database.

### fetch - Fetch data
```bash
# Direct HTTP (fast, no browser)
python browser_pilot.py fetch --url URL [--method GET] [--use-cookies SITE]
  [--headers JSON] [--data JSON] [--output FILE]

# CDP interception (browser-based)
python browser_pilot.py fetch --url URL --cdp [--pattern REGEX] [--wait 15] [--output FILE]
```

### intercept - CDP network interception
```bash
python browser_pilot.py intercept --url URL --pattern REGEX [--wait 30]
  [--profile NAME] [--headless] [--output FILE]
```
Loads a page and captures all network requests matching the URL pattern.

### cookies - Cookie management
```bash
python browser_pilot.py cookies list [--site SITE]
python browser_pilot.py cookies export --site SITE [--format json|header]
python browser_pilot.py cookies import --site SITE --file FILE
python browser_pilot.py cookies delete --site SITE
python browser_pilot.py cookies check --site SITE --url URL
```

### history - Request history
```bash
python browser_pilot.py history list [--limit 20] [--site SITE]
python browser_pilot.py history replay --id ID [--output FILE]
```

### dom - DOM operations
```bash
python browser_pilot.py dom --url URL --action click|type|extract|screenshot
  --selector SELECTOR [--value VALUE] [--profile NAME] [--output FILE]
```

## Typical Workflow

### Scenario: Scrape data from authenticated site

```bash
# Step 1: Login and save cookies (manual)
python browser_pilot.py login --url https://shop.example.com/login \
  --check-selector ".user-avatar" --profile myshop

# Step 2: Verify cookies are valid
python browser_pilot.py cookies check --site shop.example.com \
  --url https://shop.example.com/api/user

# Step 3: Intercept API responses via CDP
python browser_pilot.py intercept --url https://shop.example.com/orders \
  --pattern "api/order" --wait 10 --output orders.json --profile myshop

# Step 4: Direct HTTP for subsequent pages (faster, no browser)
python browser_pilot.py fetch --url "https://shop.example.com/api/orders?page=2" \
  --use-cookies shop.example.com --output page2.json

# Step 5: Replay a previous request
python browser_pilot.py history replay --id 3 --output replay.json
```

## Login Detection Logic

When `--wait-login` or `login` command is used, the tool polls every 5 seconds using these checks (in priority order):
1. **CSS selector**: If `--check-selector` element exists in DOM
2. **Check URL**: If `--check-url` returns HTTP 200 without redirect to login
3. **URL pattern**: If current URL no longer contains "login/signin/auth"
4. **Cookie count**: If browser has >5 cookies and URL is not a login page

## Data Storage

- **Database**: `~/.qoder/browser-pilot/browser_pilot.db` (SQLite)
- **Chrome profiles**: `~/.qoder/browser-pilot/chrome-profiles/{profile_name}/`
- **Tables**: `cookie_stores`, `request_history`, `login_states`

## Key Principles

- Always save cookies after successful login
- Use stored cookies for direct HTTP requests when possible (faster than browser)
- Record all requests to history for replay capability
- Isolate browser profiles per site/account
- Auto-detect login without requiring user confirmation
- Fall back gracefully when CDP features are unavailable
