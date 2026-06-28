#!/usr/bin/env bash
# Galaxy Merge Harness — Local Uninstall Script
# Removes the launcher and optionally the venv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
BIN_DIR="$HOME/.local/bin"
LAUNCHER_PATH="$BIN_DIR/gm"
APP_CONFIG_DIR="$HOME/.config/galaxy-merge"
APP_DATA_DIR="$HOME/.local/share/galaxy-merge"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== Galaxy Merge Harness — Uninstall ==="
echo ""

# --- 1. Remove launcher ---
echo "--- Step 1: Launcher ---"
if [ -f "$LAUNCHER_PATH" ]; then
    rm "$LAUNCHER_PATH"
    echo -e "  ${GREEN}REMOVED${NC}: $LAUNCHER_PATH"
else
    echo "  Launcher not found: $LAUNCHER_PATH"
fi

# --- 2. Remove app config ---
echo ""
echo "--- Step 2: App config ---"
if [ -d "$APP_CONFIG_DIR" ]; then
    rm -rf "$APP_CONFIG_DIR"
    echo -e "  ${GREEN}REMOVED${NC}: $APP_CONFIG_DIR"
else
    echo "  App config not found: $APP_CONFIG_DIR"
fi

# --- 3. Remove app data ---
echo ""
echo "--- Step 3: App data ---"
if [ -d "$APP_DATA_DIR" ]; then
    rm -rf "$APP_DATA_DIR"
    echo -e "  ${GREEN}REMOVED${NC}: $APP_DATA_DIR"
else
    echo "  App data not found: $APP_DATA_DIR"
fi

# --- 4. Venv (optional) ---
echo ""
echo "--- Step 4: Virtual environment ---"
if [ -d "$VENV_DIR" ]; then
    echo -e "  ${YELLOW}NOTE${NC}: venv at $VENV_DIR"
    echo "  To remove it: rm -rf $VENV_DIR"
    echo "  (Skipped by default — remove manually if desired)"
else
    echo "  venv not found: $VENV_DIR"
fi

# --- 5. Done ---
echo ""
echo "========================================"
echo -e "${GREEN}Galaxy Merge uninstalled.${NC}"
echo "========================================"
echo ""
echo "  The following were NOT removed:"
echo "    - Repository source directory: $REPO_ROOT"
echo "    - Virtual environment: $VENV_DIR"
echo "    - .gm/ directories in target projects"
echo ""
echo "  To fully remove:"
echo "    rm -rf $VENV_DIR"
echo "    rm -rf $REPO_ROOT"
echo ""
