"""What changed while you were away, as a phrase per PERSON. The greeting's second clause.

Split out of `greeting.py` on its budget, and the seam is real: that module composes a sentence
about the board's STATE, this one reads the event log and turns kinds into English. The two halves
break for different reasons — one when the board grows a new `move`, the other when it grows a new
event kind — and both are ALLOW-lists for that reason.
"""

from __future__ import annotations

from typing import Any

__all__ = ["moved"]

DIM, OFF = "\x1b[2m", "\x1b[0m"
FACES, WIDTH = 2, 34
"""Two people, because the question a first screen answers is "what changed while I was away", and
nine commits by one worker answer it worse than two names do."""


def moved(view: dict[str, Any]) -> str:
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
            "created": lambda: f"planned {_short(str(body.get('title', '')), WIDTH)}",
            "comment": lambda: f"commented on {task}",
            "message": lambda: f"wrote about {task}"}.get(kind)
    return said() if said else ""


def _and(parts: list[str]) -> str:
    """`a, b and c` — the greeting's own joiner, kept here because both halves need it and a
    comma-joined list of clauses reads as a config dump, which is what this replaced."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _short(text: str, width: int) -> str:
    said = " ".join(text.split())
    return said if len(said) <= width else said[:width - 1].rstrip() + "…"


def _dev(actor: str) -> str:
    """The PERSON behind an actor id. `agent:ana/w1` is ana with another pair of hands, and a
    greeting that named the hand would say `agent:ana/w1 picked up tk-…` to ana herself."""
    kind, _, rest = actor.partition(":")
    return rest.partition("/")[0] if kind in ("dev", "agent") else ""
