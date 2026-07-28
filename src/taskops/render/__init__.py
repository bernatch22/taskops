"""Layer 4 — a contract in, a string out. No I/O, ever.

`tests/architecture` enforces the purity: nothing here may import storage, engine,
usecases, sqlite3 or subprocess. That is what lets one renderer serve the CLI, the MCP
reply and the studio's markdown export, and it is why a rendering bug is reproducible from
a literal dict.

Split by AUDIENCE rather than by data type — the board (state), results (what an action
did), reports (a time window), task and inbox (what an agent reads to work), session (what
a hook injects). Each one answers a different question, so each one orders its output
differently.
"""

from __future__ import annotations

from .board import render_board
from .day import render_day
from .dispatch import render_dispatch
from .inbox import render_inbox
from .log import render_log
from .recover import render_recover
from .reports import render_fleet, render_standup
from .results import (
    render_next,
    render_plan,
    render_search,
    render_update,
)
from .session import render_brief, render_verdict
from .task import render_claim, render_view

__all__ = ["render_view", "render_claim", "render_inbox", "render_board",
           "render_standup", "render_fleet", "render_plan", "render_next",
           "render_update", "render_search", "render_dispatch", "render_brief",
           "render_verdict", "render_recover", "render_log", "render_day"]
