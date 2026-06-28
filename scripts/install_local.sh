#!/usr/bin/env bash
# Galaxy Merge Harness — Local Install Script
# Installs the harness into a local venv and creates a global `gm` launcher.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
LAUNCHER_NAME="gm"
BIN_DIR="$HOME/.local/bin"
LAUNCHER_PATH="$BIN_DIR/$LAUNCHER_NAME"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=12

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC}: $1"; }
fail() { echo -e "  ${RED}FAIL${NC}: $1"; exit 1; }
warn() { echo -e "  ${YELLOW}WARN${NC}: $1"; }

echo "=== Galaxy Merge Harness — Local Install ==="
echo "Repository: $REPO_ROOT"
echo ""

# --- 1. Python version check ---
echo "--- Step 1: Python check ---"
PYTHON_CMD=""
for cmd in python3.12 python3.13 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    fail "Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} not found. Install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ first."
fi
pass "Python: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"

# --- 2. Create virtual environment ---
echo ""
echo "--- Step 2: Virtual environment ---"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    pass "venv already exists: $VENV_DIR"
else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    pass "venv created: $VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# --- 3. Install dependencies ---
echo ""
echo "--- Step 3: Dependencies ---"
if [ -f "$REPO_ROOT/uv.lock" ] && command -v uv >/dev/null 2>&1; then
    uv sync --project "$REPO_ROOT" 2>&1 | tail -3
    pass "Dependencies installed via uv"
elif [ -f "$REPO_ROOT/pyproject.toml" ]; then
    "$VENV_PIP" install -e "$REPO_ROOT" 2>&1 | tail -3
    pass "Dependencies installed via pip"
else
    fail "No pyproject.toml found. Cannot install dependencies."
fi

# --- 4. Verify key packages ---
echo ""
echo "--- Step 4: Package verification ---"
for pkg in fastapi uvicorn pydantic httpx websockets; do
    if "$VENV_PYTHON" -c "import $pkg" 2>/dev/null; then
        pass "$pkg installed"
    else
        warn "$pkg not importable — some features may be unavailable"
    fi
done

# --- 5. Create launcher ---
echo ""
echo "--- Step 5: Launcher ---"
mkdir -p "$BIN_DIR"

cat > "$LAUNCHER_PATH" << LAUNCHER_EOF
#!/usr/bin/env bash
# Galaxy Merge Harness — Global Launcher
# Captures the caller's project directory and launches the harness against it.
set -euo pipefail

GM_INSTALL_DIR="$REPO_ROOT"
GM_VENV_PYTHON="$VENV_PYTHON"
GM_MODULE="galaxy_merge"

# Capture the caller's real working directory before any cd.
CALLER_DIR="\$(pwd)"

# Validate the venv exists.
if [ ! -f "\$GM_VENV_PYTHON" ]; then
    echo "Error: Galaxy Merge venv not found at \$GM_VENV_PYTHON" >&2
    echo "Re-run: $REPO_ROOT/scripts/install_local.sh" >&2
    exit 1
fi

# Forward all arguments to the Python entry point.
# The first positional arg (if any) is treated as the project directory override.
exec "\$GM_VENV_PYTHON" -m "\$GM_MODULE" --project "\$CALLER_DIR" "\$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER_PATH"
pass "Launcher created: $LAUNCHER_PATH"

# --- 6. PATH check ---
echo ""
echo "--- Step 6: PATH check ---"
if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    pass "$BIN_DIR is in PATH"
else
    warn "$BIN_DIR is NOT in PATH"
    echo ""
    echo "  Add it to your shell profile:"
    echo ""
    echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    echo "    source ~/.bashrc"
    echo ""
    echo "  Or for zsh:"
    echo ""
    echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    echo "    source ~/.zshrc"
    echo ""
fi

# --- 7. Config templates ---
echo ""
echo "--- Step 7: Config templates ---"
CONFIG_TEMPLATES_DIR="$REPO_ROOT/galaxy_merge/config_templates"
mkdir -p "$CONFIG_TEMPLATES_DIR"
for name in providers models fusion routing; do
    example="$REPO_ROOT/config/${name}.example.json"
    target="$CONFIG_TEMPLATES_DIR/${name}.json"
    if [ -f "$example" ] && [ ! -f "$target" ]; then
        cp "$example" "$target"
        pass "Created $name.json from example"
    elif [ -f "$target" ]; then
        pass "$name.json already exists"
    fi
done

# --- 8. Done ---
echo ""
echo "========================================"
echo -e "${GREEN}Galaxy Merge installed.${NC}"
echo "========================================"
echo ""
echo "  Launcher: $LAUNCHER_PATH"
echo ""
echo "  Run from any project directory with:"
echo ""
echo "    cd /path/to/your/project"
echo "    gm"
echo ""
echo "  Diagnostics:"
echo ""
echo "    gm --doctor"
echo ""
echo "  Version:"
echo ""
echo "    gm --version"
echo ""
