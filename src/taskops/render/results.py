"""What an ACTION returns — a plan, a claim, an update.

Different from a board: the reader just did something and needs to know what happened and
what to do next, so every one of these ends with the consequence rather than a summary.
"""

from __future__ import annotations

from ..contracts import NextResult, PlanResult, Task, UpdateResult
from ._text import bullet, table, truncate
from .task import render_claim

__all__ = ["render_plan", "render_next", "render_update", "render_search"]


def render_plan(result: PlanResult) -> str:
    """The ids created, in the order the caller listed them.

    In ORDER because the caller has its own plan in mind and needs to map ids onto it;
    sorting by priority here would silently break that correspondence.
    """
    rows = [[task["id"], truncate(task["title"], 50), str(task["priority"]),
             ", ".join(d["task"] for d in result["deps"]
                       if d["blocks"] == task["id"]) or "—"]
            for task in result["created"]]
    return "\n".join([f"# planned {len(result['created'])} task(s)", "",
                      table(["id", "title", "pri", "after"], rows), "",
                      _readiness(result)])


def _readiness(result: PlanResult) -> str:
    """The one line worth reading twice.

    A plan where NOTHING is ready is almost always a mistake in the `after` references —
    a cycle, or an index off by one — and it is invisible until the first `next` returns
    nothing. Saying it here turns a puzzle twenty minutes later into a sentence now.
    """
    if result["unblocked"]:
        return f"{len(result['unblocked'])} ready to start now"
    return ("⚠ NOTHING is ready — every task waits on another. Check the `after` "
            "references for a cycle or an off-by-one index")


def render_next(result: NextResult) -> str:
    """A claim, or the reason there is none — never a bare "nothing available"."""
    if result["claim"] is not None:
        return render_claim(result["claim"])
    return "\n".join(["# nothing to claim", "", result["reason"], "",
                      f"_{result['ready']} ready · {result['working']} in flight · "
                      f"{result['blocked']} waiting_"])


def render_search(tasks: list[Task], query: str) -> str:
    """Search results, or a sentence saying nothing matched.

    A sentence rather than an empty list: an agent shown nothing cannot tell a failed search
    from a genuinely empty project, and it will retry the same query. Ends by naming the
    next call, because a list of ids without one invites the agent to guess at the tool.
    """
    if not tasks:
        return (f"nothing matches `{query}` — check the board with taskops_report, or plan "
                f"the work if it does not exist yet")
    lines = [f"- {t['id']} ({t['status']}) — {truncate(t['title'], 60)}" for t in tasks]
    return "\n".join([f"{len(tasks)} task(s) matching `{query}`:", "", *lines, "",
                      "Read one in full with taskops_ask task=<id>."])


def render_update(result: UpdateResult) -> str:
    """The new status, and what it set free.

    The unblocked list is the point: an agent that just closed a task learns what it
    handed to the fleet, which is the difference between finishing work and finishing
    work somebody can pick up.
    """
    parts = [f"{result['task']['id']} → {result['task']['status']}"]
    if result["unblocked"]:
        parts += ["", f"Unblocked {len(result['unblocked'])} task(s):",
                  bullet([f"{t['id']} — {truncate(t['title'], 60)}"
                          for t in result["unblocked"]])]
    if result["notified"]:
        parts += ["", f"Notified: {', '.join(result['notified'])}"]
    return "\n".join(parts)
