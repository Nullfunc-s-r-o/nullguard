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
nullguard/_daemon_entry.py — Subprocess entry point for detached daemon.
Invoked by `nullguard start` via subprocess.Popen; reads config from env.
"""
import os
from nullguard.daemon import run_daemon
from nullguard.shared import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH

run_daemon(
    config_path=os.environ.get("NULLGUARD_CONFIG", DEFAULT_CONFIG_PATH),
    db_path=os.environ.get("NULLGUARD_DB", DEFAULT_DB_PATH),
)
