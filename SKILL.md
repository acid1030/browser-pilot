---
name: browser-pilot
description: "Selenium-based browser automation with CDP interception, cookie persistence, multi-account support, and CAPTCHA solving. Use as the primary browser tool for web scraping, form automation, data extraction, and authenticated multi-account browsing. Preferred over Playwright for sites requiring CDP interception, persistent cookie sessions, or CAPTCHA handling."
---

# Browser Pilot

Selenium + ChromeDriver browser automation skill with CDP network interception, multi-account cookie persistence, smart cookie loading, enhanced DOM operations, and CAPTCHA recognition.

## When to Use

**This skill should be used as the PRIMARY browser tool.** Priority order:
1. **Browser Pilot** (this skill) - Selenium/CDP based
2. Playwright skill - for simpler browser tasks
3. OpenClaw browser extension - for extension-based automation

**Triggers:**
- User asks to operate/automate a browser
- User needs to scrape/extract data from a website
- User needs to login to a website and save credentials
- User specifies an account name/identifier for multi-account workflows
- User needs to intercept XHR/Fetch API requests
- User needs to make HTTP requests with stored cookies
- User needs to click, type, drag, hover, or interact with web page elements
- User asks to monitor network requests from a page
- User needs to solve image/slider CAPTCHA

## CLI Reference

All commands are run via:
```bash
python ~/.qoder/skills/browser-pilot/browser_pilot.py <command> [options]
```

### open - Open browser to URL
```bash
python browser_pilot.py open --url URL [--profile NAME] [--account ACCOUNT]
  [--headless] [--wait-login] [--smart-cookies] [--validate-url URL]
  [--chrome-profile NAME] [--use-chrome-profile] [--force-copy]
  [--check-url URL] [--check-selector SEL] [--timeout 300]
```
Opens a browser with stored cookies. Use `--account` to specify which account's cookies to use. Use `--smart-cookies` for intelligent cookie loading with Chrome fallback. Use `--use-chrome-profile` to copy and use Chrome profile directly (works even when Chrome is running).

### login - Login flow
```bash
# Auto-login with credentials
python browser_pilot.py login --url URL --username USER --password PASS
  [--account ACCOUNT] [--profile NAME] [--check-url URL] [--check-selector SEL]

# Manual login (opens browser, waits for you to login)
python browser_pilot.py login --url URL [--account ACCOUNT] [--profile NAME] [--timeout 300]
```
After login detection, cookies are automatically saved to database under the specified account.

### fetch - Fetch data
```bash
# Direct HTTP (fast, no browser)
python browser_pilot.py fetch --url URL [--method GET] [--use-cookies SITE]
  [--account ACCOUNT] [--headers JSON] [--data JSON] [--output FILE]

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
python browser_pilot.py cookies list [--site SITE] [--account ACCOUNT]
python browser_pilot.py cookies export --site SITE [--account ACCOUNT] [--format json|header]
python browser_pilot.py cookies import --site SITE --file FILE [--account ACCOUNT]
python browser_pilot.py cookies delete --site SITE [--account ACCOUNT]
python browser_pilot.py cookies check --site SITE --url URL [--account ACCOUNT]
python browser_pilot.py cookies chrome --site SITE [--account ACCOUNT] [--chrome-profile Default]
python browser_pilot.py cookies profiles
```

### chrome - Chrome profile management
```bash
# Copy Chrome profile (works when Chrome is running)
python browser_pilot.py chrome copy [--chrome-profile Default] [--force]

# List copied profiles
python browser_pilot.py chrome list-copied

# List available Chrome profiles
python browser_pilot.py chrome list-chrome

# Clean up old copied profiles
python browser_pilot.py chrome cleanup [--keep 3]

# Open browser with copied Chrome profile
python browser_pilot.py chrome open-with-profile --url URL [--chrome-profile Default]
  [--profile NAME] [--account ACCOUNT] [--headless] [--force] [--save-cookies]

# Check if Chrome has cookies for a site
python browser_pilot.py chrome check --site SITE [--chrome-profile Default]
```

### history - Request history
```bash
python browser_pilot.py history list [--limit 20] [--site SITE]
python browser_pilot.py history replay --id ID [--output FILE]
```

### dom - DOM operations
```bash
python browser_pilot.py dom --url URL --action ACTION --selector SELECTOR
  [--value VALUE] [--target TARGET] [--offset X,Y] [--direction up|down|left|right]
  [--profile NAME] [--output FILE]
```

**Actions:**
| Action | Description |
|--------|-------------|
| `click` | Click element |
| `double_click` | Double click element |
| `type` | Type text into element |
| `type_human` | Type with human-like delays |
| `extract` | Extract text/HTML from elements |
| `screenshot` | Take page screenshot |
| `find` | Find element (returns info) |
| `hold` | Click and hold for duration |
| `drag` | Drag to target or by offset |
| `hover` | Hover over element |
| `scroll` | Scroll page or to element |

### captcha - CAPTCHA recognition
```bash
# Check dependencies
python browser_pilot.py captcha check

# Recognize image CAPTCHA
python browser_pilot.py captcha recognize --file IMAGE.png
python browser_pilot.py captcha image --url URL --selector "#captcha-img" [--input-selector "#input"]

# Solve slider CAPTCHA
python browser_pilot.py captcha slider --url URL --selector ".slider" [--background ".bg"]
python browser_pilot.py captcha find_gap --url URL --selector ".background"
```

## Multi-Account Workflow

When user specifies an account (e.g., "use account user1@example.com"), use the `--account` parameter:

```bash
# Login and save cookies for specific account
python browser_pilot.py login --url https://example.com/login \
  --account "user1@example.com" --check-selector ".avatar"

# Open with specific account's cookies
python browser_pilot.py open --url https://example.com \
  --account "user1@example.com" --smart-cookies

# List cookies for specific account
python browser_pilot.py cookies list --account "user1@example.com"
```

## Smart Cookie Loading

Use `--smart-cookies` for intelligent cookie loading chain:
1. **Database** → Load stored cookies
2. **Validate** → HTTP test if `--validate-url` provided
3. **Chrome Import** → Import from local Chrome if invalid/missing

```bash
python browser_pilot.py open --url https://example.com \
  --smart-cookies --validate-url https://example.com/api/me \
  --chrome-profile "Profile 1"
```

## Chrome Profile Copying (v2.1)

**Problem**: When Chrome is running, its Cookie SQLite file is locked and cannot be read.

**Solution**: Copy the Chrome profile directory instead of reading the Cookie file directly. This is similar to Playwright's persistent context approach.

```bash
# Copy Chrome profile (works when Chrome is running!)
python browser_pilot.py chrome copy --chrome-profile Default

# Open browser with copied Chrome profile (inherits all cookies/sessions)
python browser_pilot.py open --url https://example.com --use-chrome-profile

# Or use the chrome command directly
python browser_pilot.py chrome open-with-profile --url https://example.com \
  --chrome-profile Default --save-cookies
```

**Key Benefits:**
- Works even when Chrome is running
- Inherits all cookies, sessions, local storage, indexed DB
- No need to manually export/import cookies
- Profile is isolated - changes don't affect original Chrome

## Typical Workflow

### Scenario: Multi-account scraping

```bash
# Step 1: Login Account 1
python browser_pilot.py login --url https://shop.example.com/login \
  --account "account1@gmail.com" --check-selector ".user-avatar"

# Step 2: Login Account 2
python browser_pilot.py login --url https://shop.example.com/login \
  --account "account2@gmail.com" --check-selector ".user-avatar"

# Step 3: Fetch data with Account 1
python browser_pilot.py fetch --url "https://shop.example.com/api/orders" \
  --use-cookies shop.example.com --account "account1@gmail.com"

# Step 4: Fetch data with Account 2
python browser_pilot.py fetch --url "https://shop.example.com/api/orders" \
  --use-cookies shop.example.com --account "account2@gmail.com"
```

### Scenario: CAPTCHA handling

```bash
# Open page with CAPTCHA
python browser_pilot.py open --url https://example.com/login --wait-login

# If image CAPTCHA detected
python browser_pilot.py captcha image --url https://example.com/login \
  --selector "#captcha-img" --input-selector "#captcha-input"

# If slider CAPTCHA detected
python browser_pilot.py captcha slider --url https://example.com/login \
  --selector ".slider-btn" --background ".slider-bg"
```

## Login Detection Logic

When `--wait-login` or `login` command is used, the tool polls every 5 seconds using these checks (in priority order):
1. **CSS selector**: If `--check-selector` element exists in DOM
2. **Check URL**: If `--check-url` returns HTTP 200 without redirect to login
3. **URL pattern**: If current URL no longer contains "login/signin/auth"
4. **Cookie count**: If browser has >5 cookies and URL is not a login page

## Data Storage

- **Database**: `~/.qoder/browser-pilot/browser_pilot.db` (SQLite) or MySQL
- **Chrome profiles**: `~/.qoder/browser-pilot/chrome-profiles/{profile_name}/`
- **Copied Chrome profiles**: `~/.qoder/browser-pilot/chrome-imports/{name}/`
- **Tables**: `cookie_stores`, `request_history`, `login_states`
- **Account field**: Cookies stored as `(site, account)` unique key

## Key Principles

- Always use `--account` when user specifies account name/identifier
- Use `--smart-cookies` for intelligent cookie loading with fallbacks
- Save cookies after successful login
- Use stored cookies for direct HTTP requests when possible (faster than browser)
- Record all requests to history for replay capability
- Isolate browser profiles per site/account
- Auto-detect login without requiring user confirmation
- Fall back gracefully when CDP features are unavailable
