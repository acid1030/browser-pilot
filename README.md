# Browser Pilot

Selenium-based browser automation with Chrome DevTools Protocol (CDP) interception, cookie persistence, and automatic login detection.

## Features

- **Browser Automation**: Selenium WebDriver with anti-detection measures
- **CDP Network Interception**: Capture XHR/Fetch requests via Performance Log
- **Cookie Persistence**: Save/load cookies to SQLite or MySQL database
- **Auto Login Detection**: Poll-based login state detection (5-second intervals)
- **Dual Database Backend**: Automatic MySQL/SQLite switching with fallback
- **Direct HTTP Client**: Replay requests with stored cookies

## Installation

```bash
pip install selenium requests webdriver-manager brotli mysql-connector-python
```

## Quick Start

```bash
# Fetch a URL (direct HTTP)
python browser_pilot.py fetch --url https://httpbin.org/get

# Open browser and wait for manual login
python browser_pilot.py open --url https://example.com/login --wait-login

# Auto-login with credentials
python browser_pilot.py login --url https://example.com/login \
  --username user@example.com --password secret

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
| `open` | Open browser to URL with optional cookie restore |
| `login` | Handle login flow (auto or manual) |
| `fetch` | Fetch data via HTTP or CDP |
| `intercept` | CDP network request interception |
| `cookies` | Cookie management (list/export/import/delete/check) |
| `history` | Request history (list/replay) |
| `dom` | DOM operations (click/type/extract/screenshot) |

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

# Export cookies as JSON
python browser_pilot.py cookies export --site example.com

# Export as Cookie header string
python browser_pilot.py cookies export --site example.com --format header

# Import cookies from file
python browser_pilot.py cookies import --site example.com --file cookies.json

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
└── interceptor.py        <- CDP network interception
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Pull requests welcome! Please ensure tests pass before submitting.
