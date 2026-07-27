"""Layer 2 — the database, and the only package that writes SQL.

`sync` is exported alongside `Store` because the two are one story: the SQLite file
is a cache of the committed log, and `sync` is what makes that true in both
directions.
"""

from __future__ import annotations

from .locate import DB_FILE, GUIDE_FILE, LOG_FILE, PROJECT_DIR, find_root, resolve_root
from .store import BUSY_TIMEOUT, Store
from .sync import export_events, import_events, rebuild

__all__ = [
    "Store",
    "BUSY_TIMEOUT",
    "PROJECT_DIR",
    "DB_FILE",
    "LOG_FILE",
    "GUIDE_FILE",
    "find_root",
    "resolve_root",
    "export_events",
    "import_events",
    "rebuild",
]
