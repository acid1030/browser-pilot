#!/bin/bash
# Browser Pilot Installation Script
# Installs Python dependencies and MCP tools

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Browser Pilot Installation ==="

# 1. Install Python dependencies
echo ""
echo "[1/3] Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"

# 2. Install Playwright browsers
echo ""
echo "[2/3] Installing Playwright browsers (Chromium)..."
python3 -m playwright install chromium

# 3. Install browser-use MCP (optional but recommended)
echo ""
echo "[3/3] Installing browser-use MCP..."
if command -v npx &> /dev/null; then
    # Check if already installed
    if npx @anthropic-ai/mcp-installer list 2>/dev/null | grep -q "browser-use"; then
        echo "browser-use MCP already installed"
    else
        npx @anthropic-ai/mcp-installer@latest install @anthropic-ai/mcp-server-browser-use || {
            echo "Note: browser-use MCP installation skipped (npx not available or failed)"
            echo "You can install it manually: npx @anthropic-ai/mcp-installer install @anthropic-ai/mcp-server-browser-use"
        }
    fi
else
    echo "Note: npx not found. To install browser-use MCP manually:"
    echo "  npm install -g @anthropic-ai/mcp-server-browser-use"
    echo "  Or add to your MCP config manually"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Installed:"
echo "  - playwright (Python library)"
echo "  - Chromium browser (for Playwright)"
echo "  - browser-use MCP (if npx available)"
echo ""
echo "Usage:"
echo "  python3 $SCRIPT_DIR/browser_pilot.py --help"
