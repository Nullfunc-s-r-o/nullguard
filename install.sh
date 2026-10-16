#!/usr/bin/env bash
# install.sh — Robust, self-healing bootstrap installer for NullGuard.
# Run this script to automatically build, install, and globally link NullGuard.
set -euo pipefail

echo "=== NullGuard Automated Installer ==="
echo ""

# ── 1. Check Python & System Prerequisites ────────────────────────────────

# 1.1 Python binary check
if ! command -v python3 &>/dev/null; then
    echo "✗ Python 3 is not installed."
    echo "  On Debian/Ubuntu, install with:"
    echo "    sudo apt update && sudo apt install -y python3 python3-venv python3-dev"
    exit 1
fi

# 1.2 Python version requirement (3.12+)
if ! python3 -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
    CURRENT_PY=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
    echo "✗ Python 3.12+ is required (found Python $CURRENT_PY)."
    echo "  Please install Python 3.12 or newer."
    exit 1
fi
echo "✓ Python $(python3 --version | awk '{print $2}') detected"

# 1.3 Python venv module check (Issue 1: Ubuntu strips venv/ensurepip)
if ! python3 -c "import venv" 2>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3")
    echo "✗ Python 'venv' module is missing (commonly stripped in Debian/Ubuntu packages)."
    echo "  Please install it using:"
    echo "    sudo apt update && sudo apt install -y python${PY_VER}-venv (or sudo apt install -y python3-venv)"
    exit 1
fi
echo "✓ Python venv module available"

# 1.4 Python development C-headers check (Issue 3: Python.h needed for pybind11)
if ! python3 -c "import sysconfig, os; exit(0 if os.path.exists(os.path.join(sysconfig.get_path('include'), 'Python.h')) else 1)" 2>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3")
    echo "✗ Python development headers ('Python.h') not found."
    echo "  The C++20 core (pybind11) requires Python C-headers to compile."
    echo "  Please install them using:"
    echo "    sudo apt update && sudo apt install -y python${PY_VER}-dev (or sudo apt install -y python3-dev)"
    exit 1
fi
echo "✓ Python development headers present"

# 1.5 Build tools check (Issue 4: cmake and g++)
MISSING_TOOLS=()
for tool in cmake g++; do
    if ! command -v "$tool" &>/dev/null; then
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo "✗ Missing required build tool(s): ${MISSING_TOOLS[*]}"
    echo "  Please install build dependencies using:"
    echo "    sudo apt update && sudo apt install -y build-essential cmake"
    exit 1
fi
echo "✓ Build tools present (cmake, g++)"

# ── 2. Setup Directories & Self-Healing Virtual Environment ───────────────
INSTALL_DIR="${HOME}/.nullguard"
VENV_DIR="${INSTALL_DIR}/venv"

echo ""
echo "Setting up NullGuard at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Issue 2: Handle corrupted or incomplete virtual environment
if [ -d "$VENV_DIR" ]; then
    if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/pip" ] || ! "$VENV_DIR/bin/python" -c "import sys" 2>/dev/null; then
        echo "⚠ Detected corrupted or incomplete virtual environment at $VENV_DIR."
        echo "  Automatically cleaning up and recreating environment..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Using existing virtual environment at $VENV_DIR..."
fi

PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

if [ ! -x "$PYTHON_BIN" ] || [ ! -x "$PIP_BIN" ]; then
    echo "✗ Virtual environment creation failed: $PIP_BIN is not executable."
    echo "  Please remove $VENV_DIR and ensure python3-venv is properly installed."
    exit 1
fi

# Ensure pip is up to date inside the venv
"$PIP_BIN" install --upgrade pip --quiet
echo "✓ Virtual environment initialized"

# ── 3. Build C++ Core ─────────────────────────────────────────────────────
echo ""
echo "Building C++ core (pybind11)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

cmake -B build -DCMAKE_BUILD_TYPE=Release -Wno-dev -DCMAKE_POLICY_DEFAULT_CMP0177=NEW 2>&1 | tail -3
cmake --build build --parallel 2>&1 | tail -3
echo "✓ nullguard_core built successfully"

# ── 4. Install Python package ─────────────────────────────────────────────
echo ""
echo "Installing Python package into virtual environment..."
"$PIP_BIN" install . --quiet
echo "✓ Python package installed"

# ── 5. Copy C++ extension to site-packages ────────────────────────────────
echo "Linking C++ extension to virtual environment..."
SITE_PACKAGES=$("$PYTHON_BIN" -c "import sysconfig; print(sysconfig.get_path('platlib'))")

SO_COPIED=false
shopt -s nullglob
for so in "${SCRIPT_DIR}"/nullguard_core*.so "${SCRIPT_DIR}"/build/nullguard_core*.so; do
    if [ -f "$so" ]; then
        cp "$so" "$SITE_PACKAGES/"
        SO_COPIED=true
    fi
done
shopt -u nullglob

if [ "$SO_COPIED" = false ]; then
    echo "✗ Failed to locate built nullguard_core shared object (.so)."
    exit 1
fi
echo "✓ Copied nullguard_core extension to $SITE_PACKAGES"

# ── 6. Create Global CLI Symlink ──────────────────────────────────────────
echo ""
LOCAL_BIN="${HOME}/.local/bin"
mkdir -p "$LOCAL_BIN"

SYMLINK_PATH="${LOCAL_BIN}/nullguard"
ln -sf "$VENV_DIR/bin/nullguard" "$SYMLINK_PATH"
echo "✓ Created global symlink: $SYMLINK_PATH -> $VENV_DIR/bin/nullguard"

# Verify execution via symlink
if "$SYMLINK_PATH" --help &>/dev/null; then
    echo "✓ NullGuard CLI successfully verified."
else
    echo "✗ Failed to verify NullGuard CLI execution via $SYMLINK_PATH."
    exit 1
fi

# ── 7. Check $PATH Configuration (Issue 5) ────────────────────────────────
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo ""
    echo "⚠  WARNING: $LOCAL_BIN is not currently in your \$PATH."

    # Detect shell configuration file
    SHELL_RC=""
    if [[ "${SHELL:-}" == *"zsh"* ]]; then
        SHELL_RC="$HOME/.zshrc"
    elif [[ "${SHELL:-}" == *"bash"* ]]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.profile" ]; then
        SHELL_RC="$HOME/.profile"
    fi

    ALREADY_CONFIGURED=false
    if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
        if grep -qsF '.local/bin' "$SHELL_RC"; then
            ALREADY_CONFIGURED=true
        fi
    fi

    if [ "$ALREADY_CONFIGURED" = true ]; then
        echo "   $LOCAL_BIN is already configured in $SHELL_RC, but not active in this session."
        echo "   To apply immediately, run:"
        echo "     source $SHELL_RC"
    else
        PROMPTED=false
        # Prompt interactively if running in a TTY and not in CI
        if [ -t 0 ] && [ -c /dev/tty ] && [ -z "${CI:-}" ] && [ -n "$SHELL_RC" ]; then
            echo ""
            ADD_PATH_CHOICE="n"
            if read -r -p "   Would you like to append 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to $SHELL_RC? [Y/n] " input_choice </dev/tty; then
                ADD_PATH_CHOICE="${input_choice:-Y}"
            fi
            if [[ "$ADD_PATH_CHOICE" =~ ^[Yy]$ ]]; then
                echo "" >> "$SHELL_RC"
                echo '# Added by NullGuard installer' >> "$SHELL_RC"
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
                echo "✓ Appended export PATH to $SHELL_RC."
                echo "   Run 'source $SHELL_RC' or start a new terminal session to use 'nullguard' globally."
                PROMPTED=true
            fi
        fi

        if [ "$PROMPTED" = false ]; then
            echo "   To run 'nullguard' globally from any terminal, add it to your shell configuration:"
            if [ -n "$SHELL_RC" ]; then
                echo "     echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> $SHELL_RC"
                echo "     source $SHELL_RC"
            else
                echo "     echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
                echo "     source ~/.bashrc"
            fi
        fi
    fi
fi

echo ""
echo "=== Installation Complete! ==="
echo "You can now run NullGuard from any terminal:"
echo "  nullguard start   # Start daemon in background"
echo "  nullguard ui      # Open Textual monitoring dashboard"
echo "  nullguard status  # Inspect daemon state"
