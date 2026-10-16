#!/usr/bin/env bash
# install.sh — Robust, self-healing bootstrap installer for NullGuard.
# Run this script to automatically build, install, and globally link NullGuard.
set -euo pipefail

echo "=== NullGuard Automated Installer ==="
echo ""

# ── 1. Check System Prerequisites & Dependencies ──────────────────────────
MISSING_PACKAGES=()
MISSING_DESCRIPTIONS=()

# 1.1 Check cmake
if ! command -v cmake &>/dev/null; then
    MISSING_PACKAGES+=("cmake")
    MISSING_DESCRIPTIONS+=("cmake (C++ build configuration tool)")
fi

# 1.2 Check g++
if ! command -v g++ &>/dev/null; then
    MISSING_PACKAGES+=("g++")
    MISSING_DESCRIPTIONS+=("g++ (C++ compiler)")
fi

# 1.3 Check git (required for CMake FetchContent)
if ! command -v git &>/dev/null; then
    MISSING_PACKAGES+=("git")
    MISSING_DESCRIPTIONS+=("git (version control for CMake FetchContent)")
fi

# 1.4 Check curl (required for pip bootstrap and downloads)
if ! command -v curl &>/dev/null; then
    MISSING_PACKAGES+=("curl")
    MISSING_DESCRIPTIONS+=("curl (HTTP client for pip bootstrap)")
fi

# 1.5 Check Python 3 interpreter and packages
if ! command -v python3 &>/dev/null; then
    MISSING_PACKAGES+=("python3" "python3-venv" "python3-dev")
    MISSING_DESCRIPTIONS+=("python3 (Python 3 interpreter)" "python3-venv (Python virtual environment module)" "python3-dev (Python development headers)")
else
    # Check python3-venv module
    if ! python3 -c "import venv" 2>/dev/null; then
        MISSING_PACKAGES+=("python3-venv")
        MISSING_DESCRIPTIONS+=("python3-venv (Python virtual environment module)")
    fi

    # Check python3-dev headers (Python.h needed for pybind11)
    if ! python3 -c "import sysconfig, os; exit(0 if os.path.exists(os.path.join(sysconfig.get_path('include'), 'Python.h')) else 1)" 2>/dev/null; then
        MISSING_PACKAGES+=("python3-dev")
        MISSING_DESCRIPTIONS+=("python3-dev (Python development C-headers for pybind11)")
    fi
fi

# If any dependencies are missing, print a single combined error message
if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo "✗ Missing required system dependencies:"
    for desc in "${MISSING_DESCRIPTIONS[@]}"; do
        echo "  - $desc"
    done
    echo ""
    echo "Install all missing packages by running:"
    echo "  sudo apt update && sudo apt install -y ${MISSING_PACKAGES[*]}"
    echo ""
    exit 1
fi

# 1.6 Verify Python version requirement (3.12+)
if ! python3 -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
    CURRENT_PY=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
    echo "✗ Python 3.12+ is required (found Python $CURRENT_PY)."
    echo "  Please install Python 3.12 or newer."
    exit 1
fi
echo "✓ System prerequisites satisfied (Python $(python3 --version | awk '{print $2}'), venv, dev headers, cmake, g++, git, curl)"

# ── 2. Setup Directories & Self-Healing Virtual Environment ───────────────
INSTALL_DIR="${HOME}/.nullguard"
VENV_DIR="${INSTALL_DIR}/venv"

echo ""
echo "Setting up NullGuard at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Handle corrupted or incomplete virtual environment
if [ -d "$VENV_DIR" ]; then
    if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/pip" ] || ! "$VENV_DIR/bin/python" -c "import sys" 2>/dev/null; then
        echo "⚠ Detected corrupted or incomplete virtual environment at $VENV_DIR."
        echo "  Automatically cleaning up and recreating environment..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR (fast mode without ensurepip)..."
    python3 -m venv --without-pip "$VENV_DIR"
    echo "Bootstrapping latest pip via get-pip.py..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | "$VENV_DIR/bin/python"
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
echo "✓ Virtual environment initialized"

# ── 3. Build C++ Core ─────────────────────────────────────────────────────
echo ""
echo "Building C++ core (pybind11)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Clean up stale or relocated CMake cache if directory moved (e.g. mounted in Docker)
if [ -d "build" ] && [ ! -f "build/CMakeCache.txt" ]; then
    echo "⚠ Detected incomplete build directory without CMakeCache.txt."
    echo "  Resetting build directory..."
    rm -rf build
    rm -f "${SCRIPT_DIR}"/nullguard_core*.so
elif [ -f "build/CMakeCache.txt" ]; then
    CACHE_SRC=$(grep -E "^CMAKE_HOME_DIRECTORY:INTERNAL=" build/CMakeCache.txt 2>/dev/null | cut -d= -f2 || true)
    CACHE_DIR=$(grep -E "^CMAKE_CACHEFILE_DIR:INTERNAL=" build/CMakeCache.txt 2>/dev/null | cut -d= -f2 || true)
    if [ -z "$CACHE_SRC" ] || [ -z "$CACHE_DIR" ] || [ "$CACHE_SRC" != "$SCRIPT_DIR" ] || [ "$CACHE_DIR" != "${SCRIPT_DIR}/build" ]; then
        echo "⚠ Detected relocated or mismatched CMake cache ($CACHE_SRC -> $SCRIPT_DIR)."
        echo "  Resetting build directory and stale artifacts for clean rebuild..."
        rm -rf build
        rm -f "${SCRIPT_DIR}"/nullguard_core*.so
    fi
fi

# Clean previous extension artifacts in root to prevent ABI/Python version mismatches
rm -f "${SCRIPT_DIR}"/nullguard_core*.so

# Configure with self-healing fallback if configuration fails
if ! cmake -B build -DCMAKE_BUILD_TYPE=Release -Wno-dev -DCMAKE_POLICY_DEFAULT_CMP0177=NEW; then
    echo "⚠ CMake configuration failed. Retrying with a clean build directory..."
    rm -rf build
    rm -f "${SCRIPT_DIR}"/nullguard_core*.so
    cmake -B build -DCMAKE_BUILD_TYPE=Release -Wno-dev -DCMAKE_POLICY_DEFAULT_CMP0177=NEW
fi

cmake --build build --parallel
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
GLOBAL_BIN="/usr/local/bin"
FALLBACK_BIN="${HOME}/.local/bin"

if [ -w "$GLOBAL_BIN" ] 2>/dev/null || { [ ! -e "$GLOBAL_BIN" ] && [ -w "/usr/local" ] 2>/dev/null; }; then
    TARGET_BIN="$GLOBAL_BIN"
    IS_SYSTEM_WIDE=true
else
    TARGET_BIN="$FALLBACK_BIN"
    IS_SYSTEM_WIDE=false
fi

mkdir -p "$TARGET_BIN"

SYMLINK_PATH="${TARGET_BIN}/nullguard"
ln -sf "$VENV_DIR/bin/nullguard" "$SYMLINK_PATH"
echo "✓ Created global symlink: $SYMLINK_PATH -> $VENV_DIR/bin/nullguard"

# Verify execution via symlink
if "$SYMLINK_PATH" --help &>/dev/null; then
    echo "✓ NullGuard CLI successfully verified."
else
    echo "✗ Failed to verify NullGuard CLI execution via $SYMLINK_PATH."
    exit 1
fi

# ── 7. Check $PATH Configuration (Fallback for ~/.local/bin) ──────────────
if [ "$IS_SYSTEM_WIDE" = false ] && [[ ":$PATH:" != *":$TARGET_BIN:"* ]]; then
    echo ""
    echo "⚠  WARNING: $TARGET_BIN is not currently in your \$PATH."

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
        echo "   $TARGET_BIN is already configured in $SHELL_RC, but not active in this session."
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
