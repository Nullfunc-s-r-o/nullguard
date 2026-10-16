# Copyright (C) 2026 Nullfunc s.r.o.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
nullguard/cli.py — Typer-based command-line interface.

Commands:
  nullguard start    Start the monitoring daemon in the background.
  nullguard stop     Stop the running daemon.
  nullguard ui       Open the Rich TUI (works with or without daemon).
  nullguard config   Edit config.yaml in $EDITOR, or run first-run wizard.
  nullguard status   Show daemon status and latest metrics.
"""
import os
import signal
import subprocess
import sys
import time
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

import yaml

from nullguard.shared import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    PID_FILE,
    init_db,
    load_config,
)

app = typer.Typer(
    name="nullguard",
    help=(
        "NullGuard — AI-powered log monitoring with a Textual TUI.\n\n"
        "Run [bold]nullguard ui[/bold] to open the dashboard, "
        "[bold]nullguard start[/bold] to launch the background daemon."
    ),
    rich_markup_mode="rich",
    no_args_is_help=False,
    invoke_without_command=True,
)

console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────────
def _read_pid() -> Optional[int]:
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _daemon_alive() -> bool:
    import fcntl
    try:
        with open(PID_FILE, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # We got the lock, meaning daemon is NOT running
                fcntl.flock(f, fcntl.LOCK_UN)
                return False
            except OSError:
                # Lock is held by another process
                return True
    except OSError:
        return False


def _resolve_paths(
    config: Optional[str],
    db: Optional[str],
) -> tuple[str, str]:
    return (
        config or os.environ.get("NULLGUARD_CONFIG", DEFAULT_CONFIG_PATH),
        db     or os.environ.get("NULLGUARD_DB",     DEFAULT_DB_PATH),
    )


# ── First-run wizard ─────────────────────────────────────────────────────────
def _run_wizard(config_path: str) -> None:
    console.print("\n[bold cyan]Welcome to NullGuard First-Run Setup![/bold cyan]")
    console.print("No [bold]config.yaml[/bold] was found. Let's create one.\n")

    ai_enabled = Confirm.ask("Enable AI Root Cause Analysis?", default=True)
    ai_model = "gpt-3.5-turbo"
    if ai_enabled:
        ai_model = Prompt.ask("LLM model to use", default="openrouter/google/gemma-3-27b-it:free")

    alert_enabled = Confirm.ask("Enable alerting (Telegram / Discord / Slack)?", default=False)
    urls = []
    if alert_enabled:
        console.print("[italic]Enter one Apprise URL per line. Leave blank to finish.[/italic]")
        while True:
            url = Prompt.ask("Apprise URL (blank to finish)")
            if not url.strip():
                break
            urls.append(url.strip())

    log_path = Prompt.ask("Primary log file to monitor", default="/var/log/syslog")

    cfg = {
        "ai_analysis": {
            "enabled": ai_enabled,
            "model": ai_model,
            "throttle_interval_seconds": 30,
            "throttle_burst": 3,
        },
        "alerting": {"enabled": alert_enabled, "urls": urls},
        "health_alerts": {
            "cooldown_seconds": 300,
            "sustained_cycles": 3,
            "thresholds": {"cpu": 85.0, "ram": 90.0, "disk": 95.0, "swap": 80.0, "load": 4.0},
        },
        "logs": [{"path": log_path, "preset": "default"}],
    }
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, sort_keys=False)

    # Fire a test alert if URLs were configured
    if urls:
        try:
            import apprise
            ap = apprise.Apprise()
            for u in urls:
                ap.add(u)
            console.print("\n[cyan]Sending test alert to configured channels...[/cyan]")
            ap.notify(
                title="NullGuard Setup Complete",
                body="**NullGuard installed.** You will receive incident alerts here.",
                body_format=apprise.NotifyFormat.MARKDOWN,
            )
            console.print("[bold green]Test alert dispatched![/bold green]")
        except Exception as exc:
            console.print(f"[yellow]Could not send test alert: {exc}[/yellow]")

    console.print(f"\n[bold green]Configuration saved to {config_path}[/bold green]\n")
    time.sleep(0.8)


# ── Commands ─────────────────────────────────────────────────────────────────
def version_callback(value: bool):
    if value:
        from nullguard import __version__
        console.print(f"NullGuard version: [bold green]{__version__}[/bold green]")
        raise typer.Exit()

@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Show the application version and exit."
    ),
):
    """Open the TUI when nullguard is run with no sub-command."""
    if ctx.invoked_subcommand is None:
        _cmd_ui()


@app.command("start")
def cmd_start(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    db:     Optional[str] = typer.Option(None, "--db",           help="Path to SQLite database"),
    foreground: bool = typer.Option(False, "--fg", help="Run in foreground (no detach)"),
):
    """Start the NullGuard monitoring daemon in the background."""
    config_path, db_path = _resolve_paths(config, db)

    if not os.path.exists(config_path):
        console.print(f"[yellow]No config found at {config_path} — running setup wizard.[/yellow]")
        _run_wizard(config_path)

    if _daemon_alive():
        console.print(f"[yellow]Daemon is already running (PID {_read_pid()}).[/yellow]")
        raise typer.Exit()

    if foreground:
        console.print("[green]Starting NullGuard daemon in foreground...[/green]")
        os.environ["NULLGUARD_CONFIG"] = config_path
        os.environ["NULLGUARD_DB"]     = db_path
        from nullguard.daemon import run_daemon
        run_daemon(config_path, db_path)
        return

    # Detach: launch a child process
    env = os.environ.copy()
    env["NULLGUARD_CONFIG"] = config_path
    env["NULLGUARD_DB"]     = db_path

    proc = subprocess.Popen(
        [sys.executable, "-m", "nullguard._daemon_entry"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(25):
        time.sleep(0.2)
        if _daemon_alive():
            console.print(f"[bold green]✓ NullGuard daemon started[/bold green]  (PID {_read_pid()})")
            console.print(f"  Watching: {config_path}  |  DB: {db_path}")
            console.print("  Run [bold]nullguard ui[/bold] to open the dashboard.")
            return
            
    console.print("[bold red]✗ Daemon failed to start.[/bold red] Check your config.")
    raise typer.Exit(1)


@app.command("stop")
def cmd_stop():
    """Stop the running NullGuard daemon."""
    pid = _read_pid()
    if not _daemon_alive():
        console.print("[yellow]No running daemon found.[/yellow]")
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        raise typer.Exit()

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.2)
            if not _daemon_alive():
                break
        else:
            os.kill(pid, signal.SIGKILL)

        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        console.print(f"[bold green]✓ Daemon stopped[/bold green]  (was PID {pid})")
    except Exception as exc:
        console.print(f"[red]Failed to stop daemon: {exc}[/red]")
        raise typer.Exit(1)


@app.command("ui")
def cmd_ui(
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Open the Textual TUI dashboard (reads live from daemon state)."""
    _cmd_ui(db)


def _cmd_ui(db: Optional[str] = None):
    _, db_path = _resolve_paths(None, db)
    if not _daemon_alive():
        console.print(
            "[yellow]Warning:[/yellow] Daemon is not running — "
            "TUI will show historical data only.\n"
            "Start it with: [bold]nullguard start[/bold]"
        )
        time.sleep(1.5)
    from nullguard.tui import run_tui
    run_tui(db_path)


@app.command("config")
def cmd_config(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
):
    """Edit config.yaml in your $EDITOR, or run the setup wizard if missing."""
    config_path, _ = _resolve_paths(config, None)

    if not os.path.exists(config_path):
        console.print(f"[yellow]No config found at {config_path}.[/yellow]")
        _run_wizard(config_path)
        return

    console.print(f"Opening [bold]{config_path}[/bold] in your terminal editor...")
    import click
    try:
        click.edit(filename=config_path)
    except (click.ClickException, Exception):
        console.print(
            f"[yellow]No terminal editor found (e.g. nano, vim). Please edit the file directly at: {config_path}[/yellow]"
        )
        console.print("[yellow]Or install an editor: sudo apt install -y nano[/yellow]")


@app.command("status")
def cmd_status(
    db: Optional[str] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Show daemon status and the latest system metrics snapshot."""
    _, db_path = _resolve_paths(None, db)
    pid  = _read_pid()
    alive = _daemon_alive()

    table = Table(title="NullGuard Status", show_header=False, box=None, padding=(0, 2))
    table.add_column("Key",   style="bold")
    table.add_column("Value")

    status_str = f"[green]Running[/green] (PID {pid})" if alive else "[red]Not Running[/red]"
    table.add_row("Daemon", status_str)
    table.add_row("PID file", PID_FILE)
    table.add_row("Database", db_path)

    if os.path.exists(db_path):
        try:
            conn = init_db(db_path)
            row = conn.execute(
                "SELECT ts, metrics_str FROM metrics_snapshot WHERE id=1"
            ).fetchone()
            if row:
                age = int(time.time() - row[0])
                table.add_row("Last metrics", f"{age}s ago")
                for line in row[1].split("\n"):
                    table.add_row("", line)
            count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            table.add_row("Total incidents", str(count))
            conn.close()
        except Exception as exc:
            table.add_row("DB error", str(exc))
    else:
        table.add_row("Database", "[yellow]Not found — daemon has not run yet.[/yellow]")

    console.print(table)
