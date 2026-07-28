"""Layer 4 — a contract in, a string out. No I/O, ever.

`tests/architecture` enforces the purity: nothing here may import storage, engine,
usecases, sqlite3 or subprocess. That is what lets one renderer serve the CLI, the MCP
reply and the web UI's markdown export, and it is why a rendering bug is reproducible from
a literal dict.

Split by AUDIENCE rather than by data type — the board (state), results (what an action
did), reports (a time window), task and inbox (what an agent reads to work), session (what
a hook injects). Each one answers a different question, so each one orders its output
differently.
"""

from __future__ import annotations

from .ansi import Ink
from .board import render_board
from .context import render_context
from .day import render_day
from .dispatch import render_dispatch
from .inbox import render_inbox
from .log import render_log
from .prompt import PORCELAIN_VERSION, render_porcelain, render_prompt
from .recover import render_recover
from .report import NARRATION, PENDING, is_pending, narrated, render_report
from .reports import render_fleet, render_standup
from .results import (
    render_capture,
    render_edit,
    render_next,
    render_plan,
    render_search,
    render_update,
)
from .session import render_brief, render_verdict
from .status import render_status
from .task import render_claim, render_view
from .tasklist import render_tasklist

__all__ = ["render_view", "render_claim", "render_context", "render_inbox", "render_board",
           "render_standup", "render_fleet", "render_plan", "render_next", "render_capture",
           "render_update", "render_search", "render_edit", "render_dispatch", "render_brief",
           "render_verdict", "render_recover", "render_log", "render_day",
           "render_tasklist", "render_report", "render_status", "render_prompt", "render_porcelain", "PORCELAIN_VERSION", "narrated", "is_pending", "NARRATION", "PENDING", "Ink"]
