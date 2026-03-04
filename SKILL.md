---
name: browser-pilot
description: "Playwright supplement for multi-account cookie persistence, cookie-driven HTTP requests, CDP network interception, CAPTCHA recognition, and request history. Use alongside Playwright when you need cookie database management, fast HTTP requests with stored cookies, deep network capture, or CAPTCHA solving."
dependencies:
  python:
    - playwright>=1.40.0
    - requests>=2.31.0
    - brotli>=1.1.0
  mcp:
    - browser-use
    - playwright
  post_install:
    - "playwright install chromium"
---

# Browser Pilot - Playwright Supplement

Cookie database, HTTP client, network interception, CAPTCHA recognition, and request history - capabilities that complement browser automation tools.

## Installation

Run the install script to set up all dependencies:

```bash
~/.qoder/skills/browser-pilot/install.sh
```

Or install manually:

```bash
# 1. Python dependencies
pip install -r ~/.qoder/skills/browser-pilot/requirements.txt

# 2. Playwright browser
playwright install chromium

# 3. browser-use MCP (recommended)
npx @anthropic-ai/mcp-installer install @anthropic-ai/mcp-server-browser-use
```

## Tool Selection Logic

**IMPORTANT**: browser-pilot is designed to work alongside MCP browser tools (browser-use, playwright) or use its internal Playwright fallback.

### Decision Flow:

```
Task requires browser automation?
├── YES: Check for available MCP browser tools
│   ├── browser-use MCP available → Use browser-use for automation
│   ├── playwright MCP available → Use playwright MCP for automation
│   └── No MCP browser tools → Use browser-pilot's `browse` command (internal Playwright)
│
└── browser-pilot handles these REGARDLESS of MCP availability:
    ├── Cookie database (persist, sync, multi-account)
    ├── Direct HTTP with stored cookies (no browser needed)
    ├── Network interception (request+response bodies)
    ├── CAPTCHA recognition and trajectory generation
    └── Request history and replay
```

### When to Use MCP Browser Tools (Preferred)
If `browser-use` or `playwright` MCP tools are available in your environment:
- Page navigation, element interactions (click, type, hover)
- Login flows, form filling, screenshots
- DOM operations, accessibility snapshots
- Complex multi-step browser workflows

### When to Use browser-pilot
Always use browser-pilot for:
- **Cookie persistence**: `cookies sync-from-playwright`, `cookies sync-to-playwright`
- **Multi-account management**: Store cookies with `--account` parameter
- **Fast HTTP requests**: `fetch --use-cookies` (10x faster than browser)
- **Network capture**: `intercept` or `browse intercept-api` (full request+response bodies)
- **CAPTCHA solving**: `captcha recognize`, `captcha find-gap`, `captcha trajectory`
- **History/replay**: `history list`, `history replay`

### When to Use `browse` Command (Internal Playwright Fallback)
Use `browse` when:
- No MCP browser tools available in environment
- Need auto cookie sync with database (load on start, save on close)
- Simple open-extract-close workflows

## CLI Reference

All commands are run via:
```bash
python ~/.qoder/skills/browser-pilot/browser_pilot.py <command> [options]
```

### browse - Self-contained Playwright with cookie persistence

When MCP browser tools are unavailable, use these commands:

```bash
# Open URL with auto cookie sync (loads from DB, saves on close)
python browser_pilot.py browse open --url URL --site SITE [--account ACCOUNT]
  [--headless] [--wait SECONDS] [--wait-until load|domcontentloaded|networkidle]
  [--screenshot FILE] [--snapshot]

# Extract data using JavaScript
python browser_pilot.py browse extract --url URL --site SITE --script "JS_CODE"
  [--account ACCOUNT] [--headless] [--wait SECONDS] [--output FILE]

# Intercept API responses while browsing
python browser_pilot.py browse intercept-api --url URL --site SITE
  [--pattern REGEX] [--account ACCOUNT] [--headless] [--wait 30] [--output FILE]
```

**Examples:**
```bash
# Open page with cookies, take snapshot
python browser_pilot.py browse open --url "https://example.com/dashboard" \
  --site example.com --account user1 --snapshot

# Extract data from page
python browser_pilot.py browse extract --url "https://example.com/profile" \
  --site example.com --account user1 \
  --script "Array.from(document.querySelectorAll('.item')).map(e => e.textContent)"

# Capture API responses
python browser_pilot.py browse intercept-api --url "https://example.com/feed" \
  --site example.com --pattern "api/v2/posts" --wait 15 --output /tmp/posts.json
```

### fetch - HTTP requests with stored cookies

```bash
# Direct HTTP (fast, no browser needed)
python browser_pilot.py fetch --url URL [--method GET] [--use-cookies SITE]
  [--account ACCOUNT] [--headers JSON] [--data JSON] [--output FILE]

# Playwright-based interception (captures request+response bodies)
python browser_pilot.py fetch --url URL --cdp [--pattern REGEX] [--wait 15] [--output FILE]
```

### intercept - Network interception

```bash
python browser_pilot.py intercept --url URL --pattern REGEX [--wait 30]
  [--headless] [--output FILE]
```
Loads a page via Playwright and captures all network requests matching the URL pattern, including full POST bodies and response data.

### cookies - Cookie management + sync

```bash
# List stored cookies
python browser_pilot.py cookies list [--site SITE] [--account ACCOUNT]

# Export cookies
python browser_pilot.py cookies export --site SITE [--account ACCOUNT] [--format json|header|playwright-json]

# Import cookies from file
python browser_pilot.py cookies import --site SITE --file FILE [--account ACCOUNT]

# Delete cookies
python browser_pilot.py cookies delete --site SITE [--account ACCOUNT]

# Check cookie validity via HTTP
python browser_pilot.py cookies check --site SITE --url URL [--account ACCOUNT]

# Import from Chrome browser
python browser_pilot.py cookies chrome --site SITE [--account ACCOUNT] [--chrome-profile Default]

# List Chrome profiles
python browser_pilot.py cookies profiles

# Sync FROM Playwright/MCP -> DB
python browser_pilot.py cookies sync-from-playwright --file PW_COOKIES.json [--site SITE] [--account ACCOUNT]

# Sync TO Playwright/MCP <- DB
python browser_pilot.py cookies sync-to-playwright --site SITE [--account ACCOUNT] [--output FILE]
```

### chrome - Chrome profile management

```bash
python browser_pilot.py chrome copy [--chrome-profile Default] [--force]
python browser_pilot.py chrome list-copied
python browser_pilot.py chrome list-chrome
python browser_pilot.py chrome cleanup [--keep 3]
python browser_pilot.py chrome check --site SITE [--chrome-profile Default]
```

### history - Request history

```bash
python browser_pilot.py history list [--limit 20] [--site SITE]
python browser_pilot.py history replay --id ID [--output FILE]
```

### captcha - CAPTCHA recognition + trajectory

```bash
# Check dependencies
python browser_pilot.py captcha check

# Recognize image CAPTCHA from file
python browser_pilot.py captcha recognize --file IMAGE.png
python browser_pilot.py captcha recognize --image-url URL

# Find slider gap position
python browser_pilot.py captcha find-gap --file BACKGROUND.png [--slider-file SLIDER.png]

# Generate human-like mouse trajectory
python browser_pilot.py captcha trajectory --distance 187 [--duration 0.5] [--points 20]
```

## Integration Workflows

### Workflow 1: MCP Browser Login -> Fast HTTP

```bash
# 1. AI logs in via browser-use/playwright MCP (navigate, fill, click)
# 2. AI extracts cookies via MCP:
#    browser_snapshot or evaluate: JSON.stringify(await page.context().cookies())
#    -> save to /tmp/pw_cookies.json

# 3. Import to browser-pilot database for persistence
python browser_pilot.py cookies sync-from-playwright \
  --file /tmp/pw_cookies.json --site example.com --account user1

# 4. Fast HTTP requests without browser (subsequent sessions)
python browser_pilot.py fetch --url "https://api.example.com/data" \
  --use-cookies example.com --account user1
```

### Workflow 2: No MCP Available - Use browse Command

```bash
# When no browser MCP tools are available, browser-pilot handles everything

# Open page with auto cookie sync
python browser_pilot.py browse open --url "https://example.com/dashboard" \
  --site example.com --account user1 --snapshot

# Extract structured data
python browser_pilot.py browse extract --url "https://example.com/api-page" \
  --site example.com --script "document.querySelector('#data').innerText" \
  --output /tmp/data.json
```

### Workflow 3: Multi-account Management

```bash
# Import cookies for multiple accounts
python browser_pilot.py cookies sync-from-playwright --file /tmp/user1.json --site shop.com --account user1
python browser_pilot.py cookies sync-from-playwright --file /tmp/user2.json --site shop.com --account user2

# Fetch data with different accounts
python browser_pilot.py fetch --url "https://shop.com/api/orders" --use-cookies shop.com --account user1
python browser_pilot.py fetch --url "https://shop.com/api/orders" --use-cookies shop.com --account user2
```

### Workflow 4: CAPTCHA Solving with MCP/Playwright

```bash
# 1. AI uses MCP/Playwright to screenshot the CAPTCHA background image
#    -> saves to /tmp/captcha_bg.png

# 2. Detect gap position
python browser_pilot.py captcha find-gap --file /tmp/captcha_bg.png
# -> {"success": true, "x": 187, "y": 45, "method": "edge_detection"}

# 3. Generate human-like trajectory
python browser_pilot.py captcha trajectory --distance 187
# -> {"trajectory": [{"x": 5, "y": 0, "delay_ms": 25}, ...]}

# 4. AI executes trajectory via MCP/Playwright mouse API
```

### Workflow 5: Deep Network Capture

```bash
# When MCP response monitoring isn't enough (need POST bodies)
python browser_pilot.py intercept --url "https://example.com/page" \
  --pattern "api/v2/.*" --wait 30

# Or using browse command
python browser_pilot.py browse intercept-api --url "https://example.com/page" \
  --site example.com --pattern "api/v2/.*" --output /tmp/api_calls.json

# Replay captured requests later
python browser_pilot.py history list --site example.com
python browser_pilot.py history replay --id 42
```

### Workflow 6: Export Cookies Back to MCP/Playwright

```bash
# Export cookies in Playwright format for MCP session
python browser_pilot.py cookies sync-to-playwright --site example.com \
  --account user1 --output /tmp/pw_state.json

# Use in MCP: context.add_cookies(json.load('/tmp/pw_state.json')['cookies'])
```

## Data Storage

- **Database**: `~/.qoder/browser-pilot/browser_pilot.db` (SQLite) or MySQL
- **Chrome imports**: `~/.qoder/browser-pilot/chrome-imports/`
- **Tables**: `cookie_stores`, `request_history`, `login_states`
- **Account field**: Cookies stored as `(site, account)` unique key

## Key Principles

1. **Prefer MCP browser tools** when available for complex browser automation
2. **Use `browse` command** as fallback when no MCP tools exist
3. **Always persist cookies** via `sync-from-playwright` after successful logins
4. **Use `--account`** parameter for multi-account scenarios
5. **Use HTTP fetch** with stored cookies for API calls (10x faster)
6. **Use network interception** only when response body capture is needed
7. **CAPTCHA**: recognize locally, output trajectory data for browser to execute
