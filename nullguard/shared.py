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
nullguard/shared.py — Shared constants, DB helpers, config loader, and utility classes.
Imported by both daemon.py and tui.py so nothing is duplicated.
"""
import apprise
import hashlib
import os
import re
import socket
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, Optional

import yaml

# ── Paths ──────────────────────────────────────────────────────────────────
NULLGUARD_DIR = os.path.expanduser("~/.nullguard")
os.makedirs(NULLGUARD_DIR, exist_ok=True)

DEFAULT_CONFIG_PATH = os.environ.get("NULLGUARD_CONFIG", os.path.join(NULLGUARD_DIR, "config.yaml"))
DEFAULT_DB_PATH     = os.environ.get("NULLGUARD_DB",     os.path.join(NULLGUARD_DIR, "nullguard_state.db"))
PID_FILE            = os.environ.get("NULLGUARD_PID",    os.path.join(NULLGUARD_DIR, "nullguard.pid"))

DEFAULT_SMART_REGEX = (
    r"(?i)\b(error|err|crit|critical|fatal|panic|exception|traceback|"
    r"fail|failed|warn|warning|alert|emerg)\b"
)

# ── Database ────────────────────────────────────────────────────────────────
def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    Open (or create) the SQLite state database.
    Uses WAL mode so the TUI can read while the daemon writes concurrently.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS log_state (
            path     TEXT PRIMARY KEY,
            position INTEGER
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          REAL    NOT NULL,
            path        TEXT    NOT NULL,
            summary     TEXT    NOT NULL,
            metrics_str TEXT    NOT NULL,
            analysis    TEXT    NOT NULL DEFAULT '⏳ Analyzing...',
            event_count INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS metrics_snapshot (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            ts              REAL,
            cpu             REAL,
            ram             REAL,
            disk_used       REAL,
            disk_total      REAL,
            swap            REAL,
            load_1m         REAL,
            load_5m         REAL,
            load_15m        REAL,
            total_processes INTEGER,
            zombie_processes INTEGER,
            containers_run  INTEGER,
            containers_total INTEGER,
            metrics_str     TEXT
        );
    """)
    conn.commit()
    return conn


def get_last_position(conn: sqlite3.Connection, path: str) -> int:
    row = conn.execute("SELECT position FROM log_state WHERE path=?", (path,)).fetchone()
    return row[0] if row else 0


def save_last_position(conn: sqlite3.Connection, path: str, position: int) -> None:
    conn.execute(
        "INSERT INTO log_state (path, position) VALUES (?,?) "
        "ON CONFLICT(path) DO UPDATE SET position=excluded.position",
        (path, position),
    )
    conn.commit()


def save_metrics_snapshot(conn: sqlite3.Connection, metrics: Dict[str, float],
                           metrics_str: str, docker_run: int, docker_total: int) -> None:
    conn.execute("""
        INSERT INTO metrics_snapshot
            (id,ts,cpu,ram,disk_used,disk_total,swap,load_1m,load_5m,load_15m,
             total_processes,zombie_processes,containers_run,containers_total,metrics_str)
        VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            ts=excluded.ts, cpu=excluded.cpu, ram=excluded.ram,
            disk_used=excluded.disk_used, disk_total=excluded.disk_total,
            swap=excluded.swap, load_1m=excluded.load_1m, load_5m=excluded.load_5m,
            load_15m=excluded.load_15m, total_processes=excluded.total_processes,
            zombie_processes=excluded.zombie_processes,
            containers_run=excluded.containers_run,
            containers_total=excluded.containers_total,
            metrics_str=excluded.metrics_str
    """, (
        time.time(),
        metrics.get("cpu_usage_percent", 0),
        metrics.get("ram_usage_percent", 0),
        metrics.get("disk_used_percent", 0),
        metrics.get("disk_total_gb", 0),
        metrics.get("swap_used_percent", 0),
        metrics.get("load_1m", 0),
        metrics.get("load_5m", 0),
        metrics.get("load_15m", 0),
        int(metrics.get("total_processes", 0)),
        int(metrics.get("zombie_processes", 0)),
        docker_run,
        docker_total,
        metrics_str,
    ))
    conn.commit()


def insert_incident(conn: sqlite3.Connection, path: str, summary: str,
                    metrics_str: str, count: int) -> int:
    cur = conn.execute(
        "INSERT INTO incidents (ts,path,summary,metrics_str,event_count) VALUES (?,?,?,?,?)",
        (time.time(), path, summary, metrics_str, count),
    )
    conn.commit()
    return cur.lastrowid


def update_incident_analysis(conn: sqlite3.Connection, incident_id: int, analysis: str) -> None:
    conn.execute("UPDATE incidents SET analysis=? WHERE id=?", (analysis, incident_id))
    conn.commit()


# ── Config ──────────────────────────────────────────────────────────────────
def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load and return config.yaml. Does NOT run the wizard — that lives in cli.py."""
    if not os.path.exists(config_path):
        print(f"[NullGuard] config not found at {config_path}. Run `nullguard config` to set it up.")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


# ── Utilities ───────────────────────────────────────────────────────────────
def get_log_hash(event: str) -> str:
    """SHA256 of a normalized log line — strips ephemeral data for deduplication."""
    s = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", "", event)
    s = re.sub(r"[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}", "", s)
    s = re.sub(r"0x[a-fA-F0-9]+", "", s)
    s = re.sub(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}", "", s)
    s = re.sub(r"\b\d+\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return hashlib.sha256(s.encode()).hexdigest()


def build_metrics_str(metrics: Dict[str, float], docker_run: int, docker_total: int) -> str:
    docker_str = f"{docker_run}/{docker_total}" if docker_total >= 0 else "N/A"
    return (
        f"CPU: {metrics.get('cpu_usage_percent',0):.1f}% | "
        f"RAM: {metrics.get('ram_usage_percent',0):.1f}% | "
        f"Containers: {docker_str} | "
        f"Zombies: {int(metrics.get('zombie_processes',0))} | "
        f"Tasks: {int(metrics.get('total_processes',0))}\n"
        f"DISK: {metrics.get('disk_used_percent',0):.1f}% of "
        f"{metrics.get('disk_total_gb',0):.1f}GB | "
        f"LOAD: {metrics.get('load_1m',0):.2f}, "
        f"{metrics.get('load_5m',0):.2f}, "
        f"{metrics.get('load_15m',0):.2f} | "
        f"SWAP: {metrics.get('swap_used_percent',0):.1f}%"
    )


class LLMThrottle:
    """Thread-safe token-bucket rate limiter for LLM API calls."""

    def __init__(self, min_interval: float = 30.0, burst: int = 3):
        self.min_interval = min_interval
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed / self.min_interval)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class SystemHealthMonitor:
    """Fires Apprise alerts when OS metrics exceed user-configured thresholds for a sustained duration."""

    CHECKS = {
        "cpu":      ("cpu_usage_percent", "CPU Usage",        "%", 1),
        "ram":      ("ram_usage_percent", "RAM Usage",        "%", 1),
        "disk":     ("disk_used_percent", "Disk Usage",       "%", 1),
        "swap":     ("swap_used_percent", "Swap Usage",       "%", 1),
        "load":     ("load_1m",           "Load Average 1m",  "",  2),
        "load_1m":  ("load_1m",           "Load Average 1m",  "",  2),
        "load_5m":  ("load_5m",           "Load Average 5m",  "",  2),
        "load_15m": ("load_15m",          "Load Average 15m", "",  2),
    }

    def __init__(
        self,
        thresholds: Dict[str, float],
        cooldown_seconds: float = 300,
        sustained_cycles: int = 3,
        sustained_seconds: float = 0.0,
        min_load_5m: Optional[float] = None,
    ):
        self.thresholds = thresholds
        self.cooldown = cooldown_seconds
        self.sustained_cycles = max(1, sustained_cycles)
        self.sustained_seconds = sustained_seconds
        self.min_load_5m = min_load_5m
        self._last_alert: Dict[str, float] = {}
        self._breach_counts: Dict[str, int] = {}
        self._breach_start: Dict[str, float] = {}
        self._firing: set = set()

    def check(self, metrics: Dict[str, float], ap_obj: Any, metrics_str: str) -> None:
        if not ap_obj or not self.thresholds:
            return
        now = time.time()
        for key, threshold in self.thresholds.items():
            if key not in self.CHECKS:
                continue
            metrics_key, label, unit, precision = self.CHECKS[key]
            value = metrics.get(metrics_key, 0.0)

            # Check if value exceeds configured threshold
            is_breached = value >= threshold

            # Optional: correlate 5-minute Load Average with CPU to determine genuine system stress
            if is_breached and key == "cpu" and self.min_load_5m is not None:
                load_5m = metrics.get("load_5m", 0.0)
                if load_5m < self.min_load_5m:
                    is_breached = False

            if is_breached:
                # Track start time and consecutive breaches for debouncing
                if self._breach_start.get(key) is None or self._breach_counts.get(key, 0) == 0:
                    self._breach_start[key] = now

                self._breach_counts[key] = self._breach_counts.get(key, 0) + 1
                duration = now - self._breach_start[key]

                # Ensure metric stays breached for sustained window before alerting
                cycles_met = self._breach_counts[key] >= self.sustained_cycles
                seconds_met = duration >= self.sustained_seconds if self.sustained_seconds > 0 else True

                if cycles_met and seconds_met:
                    if now - self._last_alert.get(key, 0.0) >= self.cooldown:
                        self._last_alert[key] = now
                        self._firing.add(key)

                        sustained_desc = f"{self._breach_counts[key]} cycles"
                        if duration >= 1.0:
                            sustained_desc += f" (~{duration:.0f}s)"

                        extra_info: Dict[str, str] = {}
                        if key == "cpu":
                            extra_info["5m Load Average"] = f"{metrics.get('load_5m', 0.0):.2f}"

                        threading.Thread(
                            target=self._send_alert,
                            args=(
                                ap_obj, label, value, threshold, unit, precision,
                                metrics_str, None, sustained_desc, extra_info
                            ),
                            daemon=True,
                        ).start()
            else:
                # Metric returned to normal: reset debounce tracking
                self._breach_counts[key] = 0
                self._breach_start[key] = None
                self._firing.discard(key)

    @staticmethod
    def _send_alert(ap_obj: Any, label: str, value: float,
                    threshold: float, unit: str, precision: int,
                    metrics_str: str,
                    hostname: Optional[str] = None,
                    sustained_desc: Optional[str] = None,
                    extra_info: Optional[Dict[str, str]] = None) -> None:
        try:
            host = hostname or socket.gethostname()
            curr_str = f"{value:.{precision}f}{unit}"
            thresh_str = f"{threshold:.{precision}f}{unit}"

            lines = [
                f"**System Health Alert: High {label}**\n",
                f"- **Host:** {host}",
                f"- **Metric:** {label}",
                f"- **Current Value:** **{curr_str}**",
                f"- **Threshold:** **{thresh_str}**",
            ]
            if sustained_desc:
                lines.append(f"- **Sustained Duration:** **{sustained_desc}**")
            if extra_info:
                for k, v in extra_info.items():
                    lines.append(f"- **{k}:** {v}")
            lines.extend([
                "- **Status:** Threshold Exceeded",
                "",
                "**System Snapshot:**",
                f"```text\n{metrics_str}\n```",
            ])
            body = "\n".join(lines)
            ap_obj.notify(
                title=f"⚠️ [{host}] NullGuard: High {label}",
                body=body,
                body_format=apprise.NotifyFormat.MARKDOWN,
            )
        except Exception:
            pass
