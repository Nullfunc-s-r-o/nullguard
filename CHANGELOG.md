# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-10-16

### Fixed
- **Unified Installer Prerequisite Collection (`install.sh`)**:
  - Replaced sequential fail-fast checks with comprehensive dependency accumulation across `cmake`, `g++`, `git`, `curl`, `python3-venv`, and `python3-dev`.
  - Installer now prints a single consolidated diagnostic summary and provides a complete, one-line `sudo apt install -y <all_missing_packages>` command instead of requiring multiple rerun cycles.
- **Fast Venv Creation & Self-Healing (`install.sh`)**:
  - Accelerated venv bootstrap using `python3 -m venv --without-pip` paired with streaming `get-pip.py` download, bypassing the slow `ensurepip` wheel extraction bottleneck on container/WSL file systems.
  - Retained self-healing recovery to automatically clean up and recreate the venv if binary executables (`python`, `pip`) are corrupted or missing.
- **System Health Alert Debouncing & Sustained Thresholds (`SystemHealthMonitor`)**:
  - Implemented consecutive breach count debouncing (`sustained_cycles`, default: `3`) and sustained duration checking (`sustained_seconds`) to eliminate false-positive alerts on momentary single-cycle spikes (e.g. cron job bursts).
  - Added optional 5-minute load average correlation (`min_load_5m`) for CPU alerts to distinguish transient single-thread bursts from true sustained multi-core exhaustion.
  - Automatically resets debounce counters and duration timers as soon as metrics recover below threshold.
  - Added support for `"load_5m"` and `"load_15m"` metric threshold configuration.
  - Enriched Markdown alert notifications with sustained breach duration and 5-minute load average context.
- **CMake & FetchContent Cache Relocation Self-Healing (`install.sh`)**:
  - Automatically detects relocated or mismatched `CMakeCache.txt` (e.g. when mounting local project directories into Docker containers at `/app`), cleanly purging the entire `build/` directory and root `.so` artifacts to ensure `FetchContent` (`build/_deps`) downloads and compiles `pybind11` cleanly for the current environment.
  - Adds self-healing fallback retry with full directory purge if CMake configuration fails.
- **Root/Privileged Global Symlink (`install.sh`)**:
  - Automatically installs the global symlink directly to `/usr/local/bin/nullguard` when running with write permissions (e.g. root/sudo in Docker containers), bypassing `$PATH` warnings and `.bashrc` modifications for immediate out-of-the-box execution.
  - Cleanly falls back to `~/.local/bin/nullguard` with the interactive `.bashrc` prompt for unprivileged user environments.
- **Graceful CLI Editor Fallback (`nullguard config`)**:
  - Wrapped `click.edit()` in exception handling to catch missing terminal editors (`nano`, `vim`) in minimal container environments without dumping raw tracebacks, displaying actionable direct-edit paths and installation advice.

## [1.0.1] - 2026-10-16

### Fixed
- **Installer Resilience & Self-Healing (`install.sh`)**:
  - Added early pre-flight check for Python `venv` module to cleanly notify and guide users on minimal Debian/Ubuntu environments where `python3-venv` is stripped.
  - Implemented automatic self-healing recovery for incomplete or corrupted virtual environments (`~/.nullguard/venv`), validating binary executability and cleanly rebuilding if broken.
  - Added pre-flight check for Python C-headers (`Python.h`) to catch missing `python3-dev` prior to CMake/pybind11 compilation.
  - Added build tool validation for `cmake` and `g++`, providing the exact `build-essential cmake` installation command if absent.
  - Improved `$PATH` resolution: detects user shell configuration (`~/.zshrc`, `~/.bashrc`, `~/.profile`), avoids duplicate PATH exports, and offers an interactive `[Y/n]` prompt to automatically configure `~/.local/bin`.

## [1.0.0] - 2026-10-14

### Added
- **High-Performance C++ Core (`nullguard_core`)**:
  - High-speed streaming log filtering via `LogWatcher` using `std::regex` with case-insensitive `(?i)` flag support.
  - Native Linux OS hardware metrics collection via `SystemMonitor` (`/proc/stat`, `/proc/meminfo`, `/proc/*/stat`, `getloadavg()`, `std::filesystem::space()`).
  - Pybind11 Python bindings for seamless zero-overhead integration.
- **Smart Sliding-Window Log Aggregation**:
  - 3-second sliding window buffering to capture burst errors into cohesive incidents.
  - SHA256 message normalization and deduplication stripping ephemeral timestamps, UUIDs, memory addresses, and numeric IDs.
  - Hard timeout safeguards preventing indefinite window stalls.
- **AI-Powered Root Cause Analysis (RCA)**:
  - Universal multi-model LLM integration via `LiteLLM` (OpenAI, Anthropic Claude, Google Gemini, OpenRouter, and local models).
  - Background asynchronous RCA generation with non-blocking incident dispatch.
- **Universal Multi-Channel Alerting**:
  - Multi-destination incident and health alerting via `Apprise` (Telegram, Slack, Discord, email, webhooks, and 80+ providers).
  - Professional, clean DevOps Markdown alert formatting (`body_format=apprise.NotifyFormat.MARKDOWN`) with monospaced system snapshots and fenced raw logs.
  - Automated threshold-based system health alerting with configurable per-metric thresholds, 2-decimal precision, and alert cooldowns.
  - Hostname injection (`socket.gethostname()`) for multi-server fleet clarity.
- **Reactive Terminal User Interface (TUI)**:
  - Modern reactive TUI built on `Textual` (`textual.app.App`) with zero screen tearing and native mouse support.
  - Sticky, docked top OS metrics panel permanently visible during vertical scroll.
  - Scrollable incident list with focusable cards, keyboard navigation (`[J]`/`[K]`, arrows, `PgUp`/`PgDn`), and mouse wheel scrolling.
  - Prettified line numbers (`  1 │ `) for aggregated log traces.
  - Instant OS clipboard integration (`[Y]` Yank hotkey via `pyperclip`) to copy focused incident traces.
  - View controls: `[P]` Pause/Resume live updates, `[T]` Toggle Compact/Expanded layout, `[C]` Clear feed, and `[Q]` Quit.
- **Robust Daemon & Process Management**:
  - Global CLI powered by `Typer` (`nullguard start`, `stop`, `status`, `ui`, `config`).
  - Strict OS-level file locking (`fcntl.flock`) on daemon PID file to eliminate race conditions and orphaned processes.
  - Detached daemon architecture reading and writing via SQLite in Write-Ahead Logging (WAL) mode.
  - Position persistence in SQLite ensuring no lost or duplicate incident alerts across daemon restarts.
- **Deployment & Packaging**:
  - Standalone automated installer script (`install.sh`) setting up an isolated virtual environment and global symlinks.
  - Multi-stage `Dockerfile` and `docker-compose.yml` for containerized host monitoring (`pid: "host"`).
  - Docker daemon integration monitoring container counts via `/var/run/docker.sock`.
  - Comprehensive configuration via `config.yaml` with interactive first-run setup wizard.
