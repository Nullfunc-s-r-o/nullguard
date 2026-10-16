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
nullguard/daemon.py — Background monitoring engine.

Responsible for:
  - Tailing log files via the C++ LogWatcher
  - Collecting OS metrics via the C++ SystemMonitor
  - Running incident window aggregation
  - Calling LiteLLM for RCA
  - Dispatching Apprise alerts
  - Writing all state to SQLite (read by tui.py)

Does NOT import Rich or touch the terminal in any way.
"""
import os
import signal
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import apprise

try:
    import nullguard_core
except ImportError:
    print("[NullGuard daemon] nullguard_core not found. Build the C++ extension first.")
    sys.exit(1)

from nullguard.shared import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_SMART_REGEX,
    LLMThrottle,
    SystemHealthMonitor,
    build_metrics_str,
    get_log_hash,
    init_db,
    insert_incident,
    load_config,
    get_last_position,
    save_last_position,
    save_metrics_snapshot,
    update_incident_analysis,
)


# ── Incident Window ─────────────────────────────────────────────────────────
class IncidentWindow:
    def __init__(self, path: str):
        self.path = path
        self.events: Dict[str, Dict[str, Any]] = {}
        self.start_time = time.time()
        self.last_event_time = self.start_time

    def add_event(self, event: str, h: str) -> None:
        if h in self.events:
            self.events[h]["count"] += 1
        else:
            self.events[h] = {"text": event, "count": 1}
        self.last_event_time = time.time()


# ── Apprise helper ──────────────────────────────────────────────────────────
def _dispatch_apprise(ap_obj: Any, path: str, summary: str,
                      metrics: str, analysis: str, count: int) -> None:
    try:
        host = socket.gethostname()
        body = (
            f"**Incident Detected on {host}**\n\n"
            f"- **File:** {path}\n"
            f"- **Events Count:** {count}\n\n"
            f"**Logs:**\n"
            f"```text\n{summary}\n```\n\n"
            f"**Hardware Snapshot:**\n"
            f"```text\n{metrics}\n```\n\n"
            f"**LLM RCA & Mitigation:**\n"
            f"{analysis}"
        )
        ap_obj.notify(
            title=f"🚨 [{host}] NullGuard Incident: {path}",
            body=body,
            body_format=apprise.NotifyFormat.MARKDOWN,
        )
    except Exception:
        pass


# ── Incident processor (background thread) ──────────────────────────────────
def _process_incident(
    conn,
    incident: IncidentWindow,
    metrics_str: str,
    model: str,
    ai_enabled: bool,
    ap_obj: Optional[Any],
    throttle: Optional[LLMThrottle],
) -> None:
    lines = []
    total = 0
    for data in incident.events.values():
        c = data["count"]
        total += c
        lines.append(f" - {data['text']}" + (f" (Repeated {c}x)" if c > 1 else ""))
    summary = "\n".join(lines)

    # Write incident row immediately — analysis will be updated in-place
    incident_id = insert_incident(conn, incident.path, summary, metrics_str, total)

    # Determine if LLM call is allowed
    throttled = ai_enabled and throttle and not throttle.acquire()
    if throttled:
        analysis = "LLM throttled — rate limit active. Alert dispatched without RCA."
        update_incident_analysis(conn, incident_id, analysis)
        if ap_obj:
            _dispatch_apprise(ap_obj, incident.path, summary, metrics_str, analysis, total)
        return

    if not ai_enabled:
        analysis = "AI Analysis Disabled."
        update_incident_analysis(conn, incident_id, analysis)
        if ap_obj:
            _dispatch_apprise(ap_obj, incident.path, summary, metrics_str, analysis, total)
        return

    prompt = (
        f"Hardware Snapshot:\n{metrics_str}\n\n"
        f"Incident in {incident.path} ({total} events):\n{summary}\n\n"
        "Provide a concise 1-2 sentence root cause analysis and mitigation advice."
    )
    analysis = "Analysis Failed."
    try:
        api_keys = ["OPENAI_API_KEY", "LITELLM_API_KEY", "GEMINI_API_KEY",
                    "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"]
        if not any(os.environ.get(k) for k in api_keys):
            analysis = "Skipped: No API key found in environment."
        else:
            import litellm
            litellm.suppress_debug_info = True
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = response.choices[0].message.content.strip()
    except Exception as exc:
        analysis = f"LLM Error: {exc}"
    finally:
        update_incident_analysis(conn, incident_id, analysis)
        if ap_obj:
            _dispatch_apprise(ap_obj, incident.path, summary, metrics_str, analysis, total)


# ── Docker helper ───────────────────────────────────────────────────────────
def _docker_stats():
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list(all=True)
        running = sum(1 for c in containers if c.status == "running")
        return running, len(containers)
    except Exception:
        return -1, -1


# ── Main daemon loop ─────────────────────────────────────────────────────────
def run_daemon(
    config_path: str = DEFAULT_CONFIG_PATH,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """
    The core monitoring loop. Runs forever until SIGTERM / SIGINT.
    Writes all state to SQLite — the TUI reads from there.
    """
    # PID Locking
    import fcntl
    from nullguard.shared import PID_FILE
    
    pid_fd = open(PID_FILE, "w")
    try:
        fcntl.flock(pid_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Cannot acquire lock, daemon is already running
        print("[NullGuard daemon] Failed to acquire lock on PID file. Is another daemon running?")
        sys.exit(1)
        
    pid_fd.write(str(os.getpid()))
    pid_fd.flush()

    config = load_config(config_path)

    ai_cfg = config.get("ai_analysis", {})
    ai_enabled: bool = ai_cfg.get("enabled", False)
    ai_model: str    = ai_cfg.get("model", "gpt-3.5-turbo")
    throttle = LLMThrottle(
        min_interval=float(ai_cfg.get("throttle_interval_seconds", 30)),
        burst=int(ai_cfg.get("throttle_burst", 3)),
    )

    alert_cfg = config.get("alerting", {})
    ap_obj = None
    if alert_cfg.get("enabled") and apprise:
        ap_obj = apprise.Apprise()
        for url in alert_cfg.get("urls", []):
            ap_obj.add(url)

    health_cfg = config.get("health_alerts", {})
    health_monitor = SystemHealthMonitor(
        thresholds={k: float(v) for k, v in health_cfg.get("thresholds", {}).items()},
        cooldown_seconds=float(health_cfg.get("cooldown_seconds", 300)),
        sustained_cycles=int(health_cfg.get("sustained_cycles", 3)),
        sustained_seconds=float(health_cfg.get("sustained_seconds", 0.0)),
        min_load_5m=float(health_cfg["min_load_5m"]) if "min_load_5m" in health_cfg else None,
    )

    conn = init_db(db_path)
    sys_monitor = nullguard_core.SystemMonitor()

    # Build log watchers
    targets = []
    for log_cfg in config.get("logs", []):
        path = log_cfg.get("path")
        if not path:
            continue
        regex = DEFAULT_SMART_REGEX if log_cfg.get("preset") == "default" \
                else log_cfg.get("regex", DEFAULT_SMART_REGEX)
        if not os.path.exists(path):
            open(path, "a").close()
        pos = get_last_position(conn, path)
        targets.append((path, nullguard_core.LogWatcher(path, regex, pos)))

    active_incidents: Dict[str, IncidentWindow] = {}
    stop_event = threading.Event()

    def _handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    next_poll = time.time()

    while not stop_event.is_set():
        now = time.time()
        if now >= next_poll:
            next_poll = now + 1.0

            # ── Metrics ──────────────────────────────────────────────────
            metrics = sys_monitor.get_metrics()
            d_run, d_tot = _docker_stats()
            metrics_str = build_metrics_str(metrics, d_run, d_tot)
            save_metrics_snapshot(conn, metrics, metrics_str, d_run, d_tot)
            health_monitor.check(metrics, ap_obj, metrics_str)

            # ── Log polling ───────────────────────────────────────────────
            for path, watcher in targets:
                events = watcher.poll()
                if events:
                    if path not in active_incidents:
                        active_incidents[path] = IncidentWindow(path)
                    for event in events:
                        active_incidents[path].add_event(event, get_log_hash(event))
                save_last_position(conn, path, watcher.get_position())

            # ── Close expired incident windows ────────────────────────────
            current = time.time()
            for path, inc in list(active_incidents.items()):
                if current - inc.last_event_time >= 3.0 or current - inc.start_time >= 15.0:
                    del active_incidents[path]
                    threading.Thread(
                        target=_process_incident,
                        args=(conn, inc, metrics_str, ai_model, ai_enabled, ap_obj, throttle),
                        daemon=True,
                    ).start()

        time.sleep(0.1)

    conn.close()
