# Browser Pilot

Selenium-based browser automation with Chrome DevTools Protocol (CDP) interception, cookie persistence, automatic login detection, and CAPTCHA solving capabilities.

## Features

- **Browser Automation**: Selenium WebDriver with anti-detection measures
- **CDP Network Interception**: Capture XHR/Fetch requests via Performance Log
- **Cookie Persistence**: Save/load cookies to SQLite or MySQL database
- **Multi-Account Support**: Store cookies per account with `--account` parameter
- **Smart Cookie Loading**: Database → Validate → Chrome browser import fallback
- **Auto Login Detection**: Poll-based login state detection (5-second intervals)
- **Dual Database Backend**: Automatic MySQL/SQLite switching with fallback
- **Direct HTTP Client**: Replay requests with stored cookies
- **Enhanced DOM Operations**: Find by text/class/id, hold, drag, hover, scroll
- **CAPTCHA Recognition**: Local OCR (ddddocr) + slider auto-drag

## Installation

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install selenium requests webdriver-manager brotli mysql-connector-python
pip install browser_cookie3 ddddocr opencv-python Pillow  # Enhanced features
```

## Quick Start

```bash
# Fetch a URL (direct HTTP)
python browser_pilot.py fetch --url https://httpbin.org/get

# Open browser with smart cookie loading
python browser_pilot.py open --url https://example.com --smart-cookies

# Open with specific account's cookies
python browser_pilot.py open --url https://example.com --account "user@example.com" --smart-cookies

# Auto-login with credentials and save to account
python browser_pilot.py login --url https://example.com/login \
  --username user@example.com --password secret --account "user@example.com"

# Intercept network requests
python browser_pilot.py intercept --url https://example.com \
  --pattern "api/.*" --wait 30

# DOM operations
python browser_pilot.py dom --url https://example.com \
  --action extract --selector "h1"
```

## Commands

| Command | Description |
|---------|-------------|
| `open` | Open browser to URL with smart cookie loading |
| `login` | Handle login flow (auto or manual) |
| `fetch` | Fetch data via HTTP or CDP |
| `intercept` | CDP network request interception |
| `cookies` | Cookie management (list/export/import/delete/check/chrome) |
| `history` | Request history (list/replay) |
| `dom` | DOM operations (click/type/extract/screenshot/find/hold/drag/hover/scroll) |
| `captcha` | CAPTCHA recognition (image/slider) |

## Multi-Account Cookie Storage

Store and retrieve cookies per account identifier:

```bash
# Login and save cookies for specific account
python browser_pilot.py login --url https://example.com/login \
  --account "account1@example.com"

# Open with specific account's cookies
python browser_pilot.py open --url https://example.com \
  --account "account1@example.com" --smart-cookies

# List cookies filtered by account
python browser_pilot.py cookies list --account "account1@example.com"

# Export specific account's cookies
python browser_pilot.py cookies export --site example.com --account "account1@example.com"

# Import Chrome cookies and associate with account
python browser_pilot.py cookies chrome --site example.com --account "account1@example.com"
```

## Smart Cookie Loading

The `--smart-cookies` flag enables intelligent cookie loading with fallback chain:

1. **Database Check**: Load stored cookies from database
2. **Validation**: POST/GET test to verify cookies are still valid
3. **Chrome Import**: If invalid/missing, import from local Chrome browser
4. **Inject**: Load valid cookies into Selenium driver

```bash
# Smart load with validation
python browser_pilot.py open --url https://example.com \
  --smart-cookies --validate-url https://example.com/api/me

# Specify Chrome profile for import fallback
python browser_pilot.py open --url https://example.com \
  --smart-cookies --chrome-profile "Profile 1"
```

## Enhanced DOM Operations

```bash
# Find element by text content
python browser_pilot.py dom --url https://example.com \
  --action find --selector "text:Login"

# Hold element for 2 seconds (click and hold)
python browser_pilot.py dom --url https://example.com \
  --action hold --selector "#button" --value 2

# Drag slider by offset
python browser_pilot.py dom --url https://example.com \
  --action drag --selector ".slider" --offset "200,0"

# Drag element to target
python browser_pilot.py dom --url https://example.com \
  --action drag --selector "#source" --target "#destination"

# Hover over element
python browser_pilot.py dom --url https://example.com \
  --action hover --selector ".menu-item"

# Scroll page
python browser_pilot.py dom --url https://example.com \
  --action scroll --selector page --direction down --value 500

# Type with human-like delays
python browser_pilot.py dom --url https://example.com \
  --action type_human --selector "#input" --value "Hello World"
```

## CAPTCHA Recognition

```bash
# Check CAPTCHA dependencies
python browser_pilot.py captcha check

# Recognize image CAPTCHA from file
python browser_pilot.py captcha recognize --file captcha.png

# Recognize CAPTCHA from page element
python browser_pilot.py captcha image --url https://example.com \
  --selector "#captcha-img" --input-selector "#captcha-input"

# Solve slider CAPTCHA
python browser_pilot.py captcha slider --url https://example.com \
  --selector ".slider-btn" --background ".slider-bg"

# Find gap position only
python browser_pilot.py captcha find_gap --url https://example.com \
  --selector ".slider-background"
```

## Database Configuration

### Default: SQLite
No configuration needed. Data stored at `~/.qoder/browser-pilot/browser_pilot.db`

### MySQL via Environment Variables
```bash
export BROWSER_PILOT_DB=mysql
export BROWSER_PILOT_MYSQL_HOST=127.0.0.1
export BROWSER_PILOT_MYSQL_PORT=3306
export BROWSER_PILOT_MYSQL_USER=root
export BROWSER_PILOT_MYSQL_PASSWORD=your_password
export BROWSER_PILOT_MYSQL_DATABASE=browser_pilot
```

### MySQL via Config File
Create `~/.qoder/browser-pilot/db_config.json`:
```json
{
  "backend": "mysql",
  "mysql": {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "your_password",
    "database": "browser_pilot"
  }
}
```

## Cookie Management

```bash
# List stored cookies
python browser_pilot.py cookies list

# List by account
python browser_pilot.py cookies list --account "user@example.com"

# Export cookies as JSON
python browser_pilot.py cookies export --site example.com

# Export as Cookie header string
python browser_pilot.py cookies export --site example.com --format header

# Import cookies from file
python browser_pilot.py cookies import --site example.com --file cookies.json

# Import from Chrome browser
python browser_pilot.py cookies chrome --site example.com

# List available Chrome profiles
python browser_pilot.py cookies profiles

# Check cookie validity
python browser_pilot.py cookies check --site example.com --url https://example.com/dashboard

# Delete cookies
python browser_pilot.py cookies delete --site example.com
```

## Request History

```bash
# List recent requests
python browser_pilot.py history list --limit 10

# Replay a request
python browser_pilot.py history replay --id 5
```

## Anti-Detection Features

- `--disable-blink-features=AutomationControlled`
- Stealth JavaScript injection (navigator.webdriver override)
- Chrome profile isolation per session
- Realistic User-Agent strings
- Human-like mouse movements for slider CAPTCHA

## Architecture

```
browser_pilot.py          <- CLI entry point
├── backends/
│   ├── base.py           <- Abstract database interface
│   ├── sqlite_backend.py <- SQLite implementation
│   └── mysql_backend.py  <- MySQL implementation (connection pool)
├── db.py                 <- Database facade with auto-detection
├── driver.py             <- Selenium/CDP driver factory
├── cookie_manager.py     <- Cookie persistence & login detection
├── http_client.py        <- Direct HTTP client with cookie injection
├── interceptor.py        <- CDP network interception
├── chrome_cookies.py     <- Chrome cookie extraction
├── dom_helper.py         <- Enhanced DOM interaction utilities
└── captcha_solver.py     <- CAPTCHA recognition (ddddocr + slider)
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Pull requests welcome! Please ensure tests pass before submitting.
