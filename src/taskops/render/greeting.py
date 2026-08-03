"""The one line a PERSON sees when a session opens — plain English, and the only thing taskops
says to their screen.

Everything else the `SessionStart` hook produces goes to the model: `additionalContext` is
wrapped in a system reminder and never shown, and plain stdout is hidden too. So until this
existed a session opened, the agent silently received the whole board, and the human watching
had no way to tell taskops had run at all.

**It is written for somebody who does not know the vocabulary.** Three shapes were shown to a
real reader before this one: a four-section block that arrived as a run-on paragraph, a run of
`label: value` segments that read as a config dump, and a terse sentence that still said
"5 card(s) need dispatch" — jargon, and the reader said so in those words. What the board calls
a `move` is a schedule state; what this line owes the reader is what it MEANS for them, so
`SAYS` translates every one of them and the sentence opens by naming the thing that is running.

Nothing here is an instruction to the model: it never reads this. It is a status line in prose.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

__all__ = ["render_greeting"]

BOLD, DIM, OFF = "\x1b[1m", "\x1b[2m", "\x1b[0m"
"""Bold on the name and the counts, dim on the tail. Two escapes and no library: taskops has no
runtime dependencies, and a colour scheme is not the thing to spend the first one on."""

GOAL, MINE, FACES = 54, 34, 2

SAYS = {"dispatch": "ready to hand to an agent",
        "verify": "waiting for somebody to review",
        "resume": "assigned to an agent that is not running",
        "specless": "ready but with no spec written",
        "land": "closed but never merged into the trunk",
        "stalled": "blocked, and only a person can unblock them"}
"""Every `move` the sweep can name, in words a reader who has never used taskops understands.
An ALLOW-list: an unknown move says "waiting" rather than leaking a schedule state onto a
screen. This mapping is the whole reason the line got rewritten a fourth time."""


def render_greeting(view: dict[str, Any]) -> str:
    """The `systemMessage` for an opening, or "" to stay quiet in a project without a board."""
    if not view.get("actor"):
        return ""
    rest = " ".join(part for part in (_north(view), _waiting(view), _moved(view)) if part)
    # SHARED or not, in the opening clause, because it changes what everything after it means:
    # on a shared board "5 ready to hand out" is five the whole team can see, and on a local one
    # it is five nobody else knows about. Read from `shared` and NOT from "is there a URL": a
    # local project has one too now — the hook starts its board — so the URL stopped saying it.
    board = str(view.get("board") or "")
    here = (f"{BOLD}taskops{OFF} is tracking this project "
            f"{'with your team' if view.get('shared') else 'on this machine only'}")
    # The address WITHOUT its credential: this prints into a scrollback and into whatever gets
    # screen-shared next. A local project offers none, because a `taskops ui` nobody started is
    # an address that refuses to connect, which is worse than no address at all.
    where = f" {DIM}Board: {board}{OFF}" if board else ""  # local or remote; never a token
    return f"{here}{f' — {rest}' if rest else '. Nothing is waiting on you.'}{where}"


def _north(view: dict[str, Any]) -> str:
    """What the team is for and what this reader is on — the two facts a slice always carries.

    Left out at first, on the argument that the model has it and whoever wrote it remembers.
    One real session killed that: you open a project you have not touched in a week.
    """
    seen: dict[str, Any] = view.get("context") or {}
    goal, mine = seen.get("objective"), seen.get("yours")
    said = f"the team is working towards {BOLD}{_fact(goal, GOAL)}{OFF}" if goal else ""
    if mine:
        said += f"{', and ' if said else ''}you are on {_fact(mine, MINE)}"
    return f"{said}." if said else ""


def _fact(fact: dict[str, Any], width: int) -> str:
    """One stated fact, cut to `width`, with its horizon as `MM-DD` — the year is this year,
    and a sentence has no room for it."""
    horizon = str(fact.get("horizon") or "")
    return f"{_short(fact['text'], width)}{f' (by {horizon[5:] or horizon})' if horizon else ''}"


def _waiting(view: dict[str, Any]) -> str:
    """What the board is asking of this reader, counted and then EXPLAINED.

    Grouped by what the move means rather than listed per card, so nine cards cost the same
    width as one — the property that keeps this printable on a real board.
    """
    counted = Counter(SAYS.get(str(item.get("move", "")), "waiting on somebody")
                      for item in view.get("waiting") or [])
    clauses = [f"{BOLD}{n}{OFF} {said}" for said, n in counted.items()]
    if held := view.get("held"):
        clauses.append(f"you are still holding {BOLD}{len(held)}{OFF}")
    if unread := view.get("messages"):
        clauses.append(f"{BOLD}{len(unread)}{OFF} unread message(s) for you")
    return f"Right now: {_and(clauses)}." if clauses else ""


def _moved(view: dict[str, Any]) -> str:
    """The last thing each of the last two PEOPLE did, in words.

    Per person and not per event: the question a first screen answers is "what changed while I
    was away", and nine commits by one worker answer it worse than two names do.
    """
    mine, seen, out = _dev(str(view.get("actor", ""))), set(), []
    for event in reversed(view.get("recent") or []):
        who, said = _dev(str(event.get("actor", ""))), _said(event)
        if not who or not said or who in seen:
            continue
        seen.add(who)
        out.append(f"{'you' if who == mine else who} {said}")
        if len(out) == FACES:
            break
    return f"{DIM}Since yesterday, {_and(out)}.{OFF}" if out else ""


def _said(event: dict[str, Any]) -> str:
    """One event as a PHRASE. An ALLOW-list, not a filter of the noisy kinds: a teammate on a
    newer taskops writes kinds this version has never heard of, and a deny-list's failure mode
    is a first screen filling with something nobody chose to put there."""
    kind, body = str(event.get("kind", "")), event.get("body") or {}
    # WHOLE, never abbreviated. A taskops id is `tk-` and six hex — nine characters — so the
    # obvious `[:8]` shaves the last digit off and prints a handle that resolves to nothing.
    task = str(event.get("task", ""))
    said = {"status": lambda: f"moved {task} to {body.get('to', '?')}",
            "claimed": lambda: f"picked up {task}",
            "commit": lambda: f"committed on {task}",
            "released": lambda: f"handed {task} back",
            "created": lambda: f"planned {_short(str(body.get('title', '')), MINE)}",
            "comment": lambda: f"commented on {task}",
            "message": lambda: f"wrote about {task}"}.get(kind)
    return said() if said else ""


def _and(parts: list[str]) -> str:
    """`a, b and c` — the line is a sentence, and a sentence does not end on a comma."""
    return " and ".join(filter(None, [", ".join(parts[:-1]), parts[-1]])) if parts else ""


def _dev(actor: str) -> str:
    kind, _, rest = actor.strip().partition(":")
    return rest.partition("/")[0] if kind in ("dev", "agent") else ""


def _short(text: str, width: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= width else clean[: width - 1].rstrip() + "…"
