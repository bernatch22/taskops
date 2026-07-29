"""One task, rendered for the agent about to work on it.

The ORDER is the design. An agent reads top-down and may stop early, so what it must not
miss comes first: what this is, then what would make it collide with somebody, then the
spec, then the conversation. A collision warning below a long spec is a section an agent
skims past — and the cost of missing it is two agents rewriting each other's work.
"""

from __future__ import annotations

from ..contracts import Claim, Task, TaskView
from ._sections import commits_section, thread_section
from ._text import STATUS_MARK, bullet, truncate
from .inbox import render_inbox

__all__ = ["render_view", "render_claim"]


def render_claim(claim: Claim) -> str:
    """A fresh claim: the exact branch command, the inbox, then the task."""
    task = claim["view"]["task"]
    head = [f"# {task['id']} — {task['title']}", "",
            "Claimed. Create the branch and work there:", "",
            f"    git switch -c {claim['branch']}", ""]
    messages = render_inbox(claim["inbox"])
    return "\n".join(head + ([messages, ""] if messages else [])) \
        + render_view(claim["view"])


def render_view(view: TaskView) -> str:
    """The task in full. Used by `ask`, and by `next` under the claim header."""
    task = view["task"]
    parts = [f"## {STATUS_MARK.get(task['status'], '?')} {task['status']} · "
             f"priority {task['priority']}" + _reviewer_line(task) + _lease_line(view), ""]
    parts += _collisions(view)
    parts += ["### Spec", "", task["spec"] or "_(no spec — ask before guessing)_", ""]
    parts += _graph(view)
    parts += thread_section(view["thread"])
    parts += commits_section(view)
    return "\n".join(parts)


def _reviewer_line(task: Task) -> str:
    """On the FIRST line, beside the status. Who may close this card changes what an agent does
    when it finishes — a reviewer buried under the spec is one it reads after being refused."""
    return f" · reviewer {task['reviewer']}" if task.get("reviewer") else ""


def _lease_line(view: TaskView) -> str:
    lease = view["lease"]
    if lease is None:
        return ""
    where = f" on `{lease['branch']}`" if lease["branch"] else ""
    return f" · held by {lease['actor']}{where}"


def _collisions(view: TaskView) -> list[str]:
    """Who else is in these files, and what to do about it.

    The one section that changes what an agent does BEFORE it starts. It ends with the
    action rather than the observation: told only that somebody else is in the file, an
    agent proceeds anyway.
    """
    others = view["neighbours"]
    if not others:
        return []
    lines = [f"{o['id']} ({o['status']}, {o['created_by']}) — {truncate(o['title'], 50)}"
             for o in others]
    return ["### ⚠ Also touching these files", "", bullet(lines), "",
            "_Message them with taskops_update mentions=… before editing shared files._",
            ""]


def _graph(view: TaskView) -> list[str]:
    """Both directions of the DAG, plus the subtasks.

    "Blocking N" is stated as a count in the heading on purpose: it is the argument for
    finishing this today rather than tomorrow, and a number reads as urgency where a
    bare list reads as trivia.
    """
    out: list[str] = []
    if view["blocked_by"]:
        out += ["### Waiting on", "",
                bullet([f"{t['id']} ({t['status']}) — {truncate(t['title'], 60)}"
                        for t in view["blocked_by"]]), ""]
    if view["blocks"]:
        out += [f"### Blocking {len(view['blocks'])} task(s)", "",
                bullet([f"{t['id']} — {truncate(t['title'], 60)}"
                        for t in view["blocks"]]), ""]
    if view["children"]:
        out += ["### Subtasks", "",
                bullet([f"{STATUS_MARK.get(t['status'], '?')} {t['id']} — "
                        f"{truncate(t['title'], 60)}" for t in view["children"]]), ""]
    return out
