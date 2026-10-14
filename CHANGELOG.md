# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
