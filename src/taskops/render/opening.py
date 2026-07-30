"""The first thing a session reads, and the only text in this package written to assign a ROLE.

Every other renderer answers a question somebody asked. This one arrives before the question,
so its order is an argument: **who you are, then what the project has decided, then what is
waiting.** A session told the state before the role does the state itself — which is precisely
what happened when the opening ended with "Run taskops_next to claim one", and two developers
watched their agents finish the work and leave the cards dead.

Short on purpose. It is paid for by every session, whether or not anybody reads it.
"""

from __future__ import annotations

from typing import Any

from ._text import truncate
from .attention import HEADINGS
from .context import render_context

__all__ = ["render_opening", "ROLE"]

ROLE = (
    "You are the ORCHESTRATOR of this board. You do not implement: you dispatch "
    "`taskops-worker` sub-agents for the work and `taskops-verifier` sub-agents for the "
    "reviews, and you decide what moves. A card you work yourself is a card nobody is "
    "keeping the plan for."
)
"""Stated as a fact rather than asked for as a favour, because SessionStart fires for the MAIN
conversation ONLY — sub-agents never see it — so the event is the proof of which one this is."""


def render_opening(view: dict[str, Any]) -> str:
    """`Opening` -> the injection. Never empty: the role is worth stating on a quiet board."""
    lines = [f"taskops — {ROLE}", f"You are `{view['actor']}` in this project.", ""]
    lines += ["## The project", render_context(view["context"]), ""]
    lines += _waiting(view["waiting"])
    if view["held"]:
        lines += ["", f"You still hold {len(view['held'])} card(s) from a previous session: "
                      + ", ".join(lease["task"] for lease in view["held"])
                      + " — close or release them."]
    if view["messages"]:
        lines += ["", f"{len(view['messages'])} message(s) waiting — `taskops_ask` reads them."]
    return "\n".join(lines)


def _waiting(waiting: list[dict[str, Any]]) -> list[str]:
    """The board's open questions, grouped by the MOVE each one needs.

    Grouped and not listed, for the same reason `render_attention` groups: a reader who has to
    decide a verb per row is a reader doing the sweep's job by hand.
    """
    if not waiting:
        return ["## Waiting on a decision", "Nothing — every open card is being worked on.",
                "Ask for `taskops_report kind=attention` again before you assume that holds."]
    lines = ["## Waiting on a decision (this is where you start)"]
    for move in dict.fromkeys(item["move"] for item in waiting):
        lines.append(f"{HEADINGS[move]}")
        lines += [f"  {item['task']['id']}  {truncate(item['task']['title'], 60)}"
                  for item in waiting if item["move"] == move]
    return lines
