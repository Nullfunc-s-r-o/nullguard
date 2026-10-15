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
nullguard/tui.py — Textual-based terminal dashboard (read-only, detached from daemon).

Reads live state from SQLite (written by daemon.py) and renders it using Textual.
Provides focusable incident widgets, smooth flicker-free scrolling, native mouse support,
and one-touch log copying to clipboard via [Y].
"""
import os
import sqlite3
import time
from typing import Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, ListItem, ListView, Static

from nullguard.shared import DEFAULT_DB_PATH, init_db


def format_numbered_logs(summary: str) -> Text:
    """Prepend neatly formatted line numbers (e.g., '  1 │ ') to log lines."""
    lines = summary.split("\n")
    total = len(lines)
    pad_width = max(len(str(total)), 3)
    text = Text()
    for idx, line in enumerate(lines, start=1):
        prefix = f"{idx:>{pad_width}} │ "
        text.append(prefix, style="dim cyan")
        text.append(line, style="white")
        if idx < total:
            text.append("\n")
    return text


class IncidentItem(ListItem):
    """A focusable incident widget containing aggregated logs, snapshot, and RCA."""

    can_focus = True

    BINDINGS = [
        Binding("y", "copy_logs", "Copy Logs", priority=True),
    ]

    def __init__(self, row: tuple, compact: bool = False):
        super().__init__()
        # row: (id, ts, path, summary, metrics_str, analysis, event_count)
        self.incident_id = row[0]
        self.ts = time.strftime("%H:%M:%S", time.localtime(row[1]))
        self.path = row[2]
        self.summary = row[3]
        self.metrics_str = row[4]
        self.analysis = row[5]
        self.count = row[6]
        self.compact = compact

    def compose(self) -> ComposeResult:
        yield Static(self._render_content(), id=f"content-{self.incident_id}", classes="incident-content")

    def _render_content(self) -> Text:
        header_text = f"[{self.ts}] [{self.path}]".replace("[", r"\[")
        header = f"{header_text} [bold red]Incident #{self.incident_id}: {self.count} events[/bold red]"

        if self.compact:
            first_line = self.summary.split("\n")[0][:80]
            rca_snippet = self.analysis[:80]
            return (
                Text.from_markup(f"{header}  [bold]→[/bold] ")
                + Text(first_line)
                + Text.from_markup("  [bold magenta]RCA:[/bold magenta] ")
                + Text(rca_snippet)
            )

        res = Text.from_markup(f"{header}\n\n[bold yellow]Aggregated Logs:[/bold yellow]\n")
        res += format_numbered_logs(self.summary)
        res += Text.from_markup(f"\n\n[bold green]Hardware Snapshot:[/bold green]\n") + Text(self.metrics_str)
        res += Text.from_markup(f"\n\n[bold magenta]LLM Root Cause & Mitigation:[/bold magenta]\n") + Text(self.analysis)
        return res

    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        content_widget = self.query_one(f"#content-{self.incident_id}", Static)
        content_widget.update(self._render_content())

    def update_analysis(self, new_analysis: str) -> None:
        self.analysis = new_analysis
        content_widget = self.query_one(f"#content-{self.incident_id}", Static)
        content_widget.update(self._render_content())

    def on_click(self) -> None:
        self.focus()

    def action_copy_logs(self) -> None:
        self.app.action_copy_incident()


class NullGuardApp(App):
    """Textual TUI for NullGuard monitoring dashboard."""

    TITLE = "NullGuard Observability"
    SUB_TITLE = "Real-time AI Log Intelligence"

    CSS = """
    Screen {
        background: $background;
        overflow: hidden;
    }

    Header {
        dock: top;
    }

    #metrics-panel {
        height: 5;
        border: round green;
        background: $surface;
        padding: 0 1;
        content-align: center middle;
    }

    #incidents-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        text-style: bold;
        padding: 0 1;
        margin-top: 1;
    }

    #incidents-container {
        height: 1fr;
        overflow-y: auto;
    }

    #incidents-list {
        height: 100%;
        border: round $primary;
        padding: 0 1;
        scrollbar-size: 1 1;
        overflow-y: auto;
    }

    IncidentItem {
        padding: 1;
        margin: 0 0 1 0;
        border: round $primary;
        background: $surface;
        height: auto;
    }

    IncidentItem:focus, IncidentItem.-highlighted {
        border: double cyan;
        background: $boost;
    }

    #empty-item {
        padding: 1 2;
        border: none;
        background: transparent;
        color: $text-muted;
    }

    Footer {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("y", "copy_incident", "Copy Logs", priority=True),
        Binding("p", "toggle_pause", "Pause Live"),
        Binding("c", "clear_incidents", "Clear Feed"),
        Binding("t", "toggle_compact", "Compact/Expanded"),
        Binding("j", "cursor_down", "Next Incident", show=False),
        Binding("k", "cursor_up", "Prev Incident", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        super().__init__()
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.paused = False
        self.compact = False
        self._seen_ids: set[int] = set()
        self.has_placeholder = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Daemon starting — waiting for first metrics snapshot...", id="metrics-panel")
        yield Static(" Incident Feed  (Click or use ↑/↓ to focus incident, [Y] to copy logs)", id="incidents-header")
        with Container(id="incidents-container"):
            yield ListView(id="incidents-list")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.conn = init_db(self.db_path)
        except Exception as exc:
            self.notify(f"Could not connect to database: {exc}", severity="error")

        self.update_from_db()
        self.set_interval(0.5, self.update_from_db)

    def on_unmount(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, IncidentItem):
            event.item.focus()

    def action_cursor_down(self) -> None:
        lv = self.query_one("#incidents-list", ListView)
        if lv:
            lv.action_cursor_down()

    def action_cursor_up(self) -> None:
        lv = self.query_one("#incidents-list", ListView)
        if lv:
            lv.action_cursor_up()

    def action_copy_incident(self) -> None:
        target = self.focused
        if not isinstance(target, IncidentItem):
            lv = self.query_one("#incidents-list", ListView)
            if lv and isinstance(lv.highlighted_child, IncidentItem):
                target = lv.highlighted_child
            else:
                target = None

        if target:
            try:
                import pyperclip
                pyperclip.copy(target.summary)
                self.notify(f"Copied logs for Incident #{target.incident_id} to clipboard!", title="[Y] Copied")
            except Exception as exc:
                self.notify(f"Copy failed: {exc}", severity="error")
        else:
            self.notify("No incident selected to copy.", severity="warning")

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        status = "Paused" if self.paused else "Resumed"
        self.notify(f"Live feed {status.lower()}.")
        header = self.query_one("#incidents-header", Static)
        if header:
            badge = "[bold yellow][PAUSED][/bold yellow] " if self.paused else ""
            header.update(f" {badge}Incident Feed  (Click or use ↑/↓ to focus incident, [Y] to copy logs)")

    def action_clear_incidents(self) -> None:
        lv = self.query_one("#incidents-list", ListView)
        if lv:
            lv.clear()
            self._seen_ids.clear()
            lv.append(ListItem(Static("No incidents yet — daemon is watching your logs.", classes="empty-msg"), id="empty-item"))
            self.has_placeholder = True
        self.notify("Incident feed cleared.")

    def action_toggle_compact(self) -> None:
        self.compact = not self.compact
        for item in self.query(IncidentItem):
            item.set_compact(self.compact)
        mode = "Compact" if self.compact else "Expanded"
        self.notify(f"View mode: {mode}")

    def update_from_db(self) -> None:
        if not self.conn:
            return

        # 1. Update OS Metrics
        try:
            row = self.conn.execute(
                "SELECT ts, metrics_str FROM metrics_snapshot WHERE id=1"
            ).fetchone()
            if row:
                age = time.time() - row[0]
                offline = age > 10
                metrics_text = row[1]
                if offline:
                    prefix = Text.from_markup("[bold red][DAEMON OFFLINE][/bold red] (metrics delayed > 10s)\n")
                else:
                    prefix = Text.from_markup("[bold green][DAEMON ACTIVE][/bold green]\n")
                status_text = prefix + Text(metrics_text)
            else:
                status_text = Text.from_markup("[bold red][DAEMON OFFLINE][/bold red]\nWaiting for first metrics snapshot from daemon...")
        except Exception as exc:
            status_text = Text.from_markup(f"[bold yellow]Metrics query error:[/bold yellow] {exc}")

        try:
            metrics_panel = self.query_one("#metrics-panel", Static)
            if metrics_panel:
                metrics_panel.update(status_text)
        except Exception:
            pass

        # 2. Update Incidents
        if self.paused:
            return

        try:
            rows = self.conn.execute(
                "SELECT id, ts, path, summary, metrics_str, analysis, event_count "
                "FROM incidents ORDER BY id DESC LIMIT 50"
            ).fetchall()
        except Exception:
            return

        try:
            lv = self.query_one("#incidents-list", ListView)
        except Exception:
            return

        if not rows and not self._seen_ids and not self.has_placeholder:
            lv.append(ListItem(Static("No incidents yet — daemon is watching your logs.", classes="empty-msg"), id="empty-item"))
            self.has_placeholder = True
            return

        if rows and self.has_placeholder:
            lv.clear()
            self.has_placeholder = False

        new_items = []
        for r in reversed(rows):
            incident_id = r[0]
            if incident_id not in self._seen_ids:
                self._seen_ids.add(incident_id)
                new_items.append(IncidentItem(r, compact=self.compact))

        for item in new_items:
            lv.append(item)

        # Update in-place analysis for cards still showing ⏳
        for item in lv.query(IncidentItem):
            if "⏳" in item.analysis or "Analyzing" in item.analysis:
                try:
                    updated = self.conn.execute(
                        "SELECT analysis FROM incidents WHERE id=?", (item.incident_id,)
                    ).fetchone()
                    if updated and updated[0] != item.analysis:
                        item.update_analysis(updated[0])
                except Exception:
                    pass


def run_tui(db_path: str = DEFAULT_DB_PATH) -> None:
    """Launch the Textual TUI dashboard. Safe to run while daemon is active."""
    if not os.path.exists(db_path):
        from rich.console import Console
        Console().print(
            f"[yellow]State database not found at {db_path}.[/yellow]\n"
            "Start the daemon first with: [bold]nullguard start[/bold]"
        )
        return

    app = NullGuardApp(db_path=db_path)
    app.run()
