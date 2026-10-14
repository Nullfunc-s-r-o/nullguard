#!/usr/bin/env bash
# install.sh — Automated bootstrap installer for NullGuard.
# Run this script to automatically build, install, and globally link NullGuard.
set -euo pipefail

echo "=== NullGuard Automated Installer ==="
echo ""

# ── 1. Check Python & Tools ───────────────────────────────────────────────
if ! python3 -c "import sys; assert sys.version_info >= (3,12)" 2>/dev/null; then
    echo "✗ Python 3.12+ is required."
    exit 1
fi
echo "✓ Python $(python3 --version)"

for tool in cmake g++; do
    if ! command -v "$tool" &>/dev/null; then
        echo "✗ '$tool' not found. Install: sudo apt install cmake build-essential"
        exit 1
    fi
done
echo "✓ cmake and g++ present"

# ── 2. Setup Directories & Virtual Environment ───────────────────────────
INSTALL_DIR="${HOME}/.nullguard"
VENV_DIR="${INSTALL_DIR}/venv"

echo ""
echo "Setting up NullGuard at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Using existing virtual environment..."
fi

PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

# Ensure pip is up to date inside the venv
"$PIP_BIN" install --upgrade pip --quiet

# ── 3. Build C++ extension ────────────────────────────────────────────────
echo ""
echo "Building C++ core..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

cmake -B build -DCMAKE_BUILD_TYPE=Release -Wno-dev -DCMAKE_POLICY_DEFAULT_CMP0177=NEW 2>&1 | tail -3
cmake --build build --parallel 2>&1 | tail -3
echo "✓ nullguard_core built"

# ── 4. Install Python package ─────────────────────────────────────────────
echo ""
echo "Installing Python package into virtual environment..."
# Install standard package so it's fully self-contained in the venv
"$PIP_BIN" install . --quiet
echo "✓ Python package installed"

# ── 5. Copy C++ extension to site-packages ────────────────────────────────
echo "Linking C++ extension to the virtual environment..."
SITE_PACKAGES=$("$PYTHON_BIN" -c "import sysconfig; print(sysconfig.get_path('platlib'))")
cp *.so "$SITE_PACKAGES/"
echo "✓ Copied nullguard_core extension"

# ── 6. Create Global CLI Symlink ──────────────────────────────────────────
echo ""
LOCAL_BIN="${HOME}/.local/bin"
mkdir -p "$LOCAL_BIN"

SYMLINK_PATH="${LOCAL_BIN}/nullguard"
ln -sf "$VENV_DIR/bin/nullguard" "$SYMLINK_PATH"

echo "✓ Created global symlink: $SYMLINK_PATH -> $VENV_DIR/bin/nullguard"

# Verify execution
if "$SYMLINK_PATH" --help &>/dev/null; then
    echo "✓ NullGuard CLI successfully verified."
else
    echo "✗ Failed to verify NullGuard CLI execution."
    exit 1
fi

if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo ""
    echo "⚠  WARNING: $LOCAL_BIN is not in your PATH."
    echo "   You must add it to your ~/.bashrc or ~/.zshrc:"
    echo '   export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "=== Installation Complete! ==="
echo "You can now run NullGuard from any terminal:"
echo "  nullguard start"
