"""What a HOOK prints. A different audience from everything else in `render/`.

These two outputs are not read by a person choosing what to do next — they are injected
into a session's context by SessionStart, or shown to an agent as the reason its commit
was denied. So they are short, they lead with the action, and they never include anything
the agent cannot act on. A brief that pastes a whole board costs every session the tokens
to read a board it did not ask for.
"""

from __future__ import annotations

from typing import Protocol

from ..contracts import Event, Lease
from ._text import ago, bullet, truncate

__all__ = ["render_brief", "render_verdict"]


class BriefLike(Protocol):
    """What `render_brief` needs, structurally.

    A Protocol so `render/` never imports `usecases.Brief` — that would point layer 4 at
    layer 5 and break the rule that keeps rendering testable from literals. The FIELDS are
    real contracts, though: `Lease` and `Event` live in layer 1, so typing them properly
    costs nothing and a loose `dict[str, object]` here was hiding real key errors.
    """

    actor: str
    held: list[Lease]
    messages: list[Event]
    ready: int


class VerdictLike(Protocol):
    allowed: bool
    reason: str
    task: str


def render_brief(brief: BriefLike) -> str:
    """The SessionStart injection: who you are, what you hold, who spoke to you.

    Returns "" when there is nothing at all — no tasks, no messages. A session that is
    told "you are dev:berna and you hold nothing" has paid tokens to learn nothing, and a
    hook that prints nothing is a hook that costs nothing.
    """
    parts: list[str] = []
    if brief.held:
        parts += [f"You ({brief.actor}) hold {len(brief.held)} task(s):",
                  bullet([f"{lease['task']}"
                          + (f" on `{lease['branch']}`" if lease["branch"] else
                             " — no branch yet")
                          for lease in brief.held])]
    if brief.messages:
        parts += ["", f"📬 {len(brief.messages)} message(s):",
                  bullet([f"{m['actor']} on {m['task']} ({ago(m['ts'])}): "
                          f"{truncate(str(m['body'].get('text', '')), 100)}"
                          for m in brief.messages])]
    if not parts and brief.ready:
        return f"taskops: {brief.ready} task(s) ready. Run taskops_next to claim one."
    if not parts:
        return ""
    return "taskops — " + "\n".join(parts)


def render_verdict(verdict: VerdictLike) -> str:
    """The commit guard's answer, as the agent reads it in a denial.

    Only the reason. The agent asked to commit and was refused, so the one useful thing is
    what to do instead — anything else buries it.
    """
    if verdict.allowed:
        return ""
    return f"taskops: commit blocked — {verdict.reason}"
