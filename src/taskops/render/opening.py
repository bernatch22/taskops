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
    lines += _settings(view.get("policies") or [])
    lines += _team(view.get("team") or {})
    lines += _waiting(view["waiting"])
    if view["held"]:
        lines += ["", f"You still hold {len(view['held'])} card(s) from a previous session: "
                      + ", ".join(lease["task"] for lease in view["held"])
                      + " — close or release them."]
    if view["messages"]:
        lines += ["", f"{len(view['messages'])} message(s) waiting — `taskops_ask` reads them."]
    return "\n".join(lines)


def _settings(policies: list[dict[str, Any]]) -> list[str]:
    """The values the engine OBEYS, apart from the prose it weighs. Two lists and not one on
    purpose: a decision is something to take into account, a policy is something that will refuse
    you — and they read identically until one of them refuses, which is exactly how a policy came
    to be hidden inside a decision in the first place."""
    if not policies:
        return []
    said = [f"- `{p['name']}: {p['value']}`" for p in policies]
    return ["## Settings the engine enforces (not advice)", *said, ""]


def _team(team: dict[str, Any]) -> list[str]:
    """Who else is here, and what they have their hands on — before the work list, on purpose.

    A session that reads "what is waiting" first starts choosing; a session that reads who else
    is connected first chooses differently. That ordering is the whole value: the collisions
    this brief exists to stop (one card implemented twice, one review started by two devs) all
    happened between sessions that could each see the board perfectly and each other not at all.

    Silent when nobody else is connected. A heading over an empty list would say "you are alone"
    every time somebody works alone, which is most of the time, on every session.
    """
    others = team.get("others") or []
    if not others:
        return []
    lines = ["## Who else is on this board right now"]
    for mate in others:
        held = mate.get("holding") or []
        # The titles, not just the ids: "tk-4f21a0" tells a reader nothing about whether their
        # next card overlaps with it, which is the only question this paragraph is answering.
        doing = "; ".join(f"{card} {truncate(title, 40)}" for card, title in held) if held \
            else "free — nothing claimed"
        lines.append(f"  {mate['dev']} ({_ago(float(mate.get('idle', 0)))}): {doing}")
    lines.append("Do not dispatch onto what they are holding, and do not review what is theirs.")
    return [*lines, ""]


def _ago(idle: float) -> str:
    return "active now" if idle < 90 else f"quiet {int(idle // 60)}m"


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
