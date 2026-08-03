"""What one row of the server's board list says — the shape `/api/projects` hands the browser.

A use case and not three lines inside the endpoint, because two of the three facts on a row come
from the DISK and a transport may not read it: the GitHub link lives in the board's directory,
and when it last moved is the log's mtime. `root._projects` used to reach for `storage.LOG_FILE`
directly, which the architecture test caught immediately and correctly.

Every field here is chosen for what it COSTS. A count of open cards is the obvious next one and
is deliberately absent: it means opening every board's sqlite to draw a front page, and this is
the page that must still answer when a board's cache is the thing that broke. `stat` and a
one-line read scale with the number of boards and with nothing else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..storage import LOG_FILE
from ._ghlink import read_link

__all__ = ["rows_for"]


def rows_for(home: Path, names: list[str]) -> list[dict[str, Any]]:
    """One row per board the caller's session opens. The PATHS are built here, so no client
    ever assembles a URL out of a name and a hostname it guessed at."""
    return [{"name": name, "path": f"/{name}/",
             # The link cannot be read by the client: it lives on the SERVER, and a board is
             # routinely bound to a repository that is not the checkout's `origin` — which is
             # exactly how a project hosted anywhere else gets a real access list.
             "github": read_link(home / name),
             "updated": _moved(home / name)} for name in names]


def _moved(board: Path) -> float:
    """When this board last recorded anything, as a unix time, or 0.

    The MTIME of the append-only log, not a query. "Which of these is alive" is the question a
    list of boards is read to answer, and this is the whole of it — one `stat`, no store opened,
    no cache consulted, nothing that can be stale in a way the log is not.
    """
    try:
        return (board / LOG_FILE).stat().st_mtime
    except OSError:
        return 0.0
