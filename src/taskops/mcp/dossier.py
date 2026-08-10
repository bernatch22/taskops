"""The card view: everything a worker needs, in the response it already asked for.

**The ORDER is the design.** An agent reads top-down and may stop early, so what
it must not miss comes first: what would make it collide with somebody, where
the last worker stopped, and what this card is PART OF — all above the spec. A
collision warning below a long spec is a section an agent skims past, and the
cost of missing it is two agents rewriting each other's work (v1, verbatim).

Nothing here truncates: not the spec, not the criteria, not the thread. A
summary is where context goes to die, and v1's hooks summarised.
"""

from __future__ import annotations

from typing import Any, cast

from . import before, render, thread
from .._json import as_rows, as_object, as_strings
from ..core.hours import human

MISSING_SPEC = "_(no spec — ask before guessing; a title is a label, not a brief)_"


def card_view(data: dict[str, Any], now: float) -> str:
    card = as_object(data.get("card"))
    out = _head(data, card, now)
    # Everything that changes what you do BEFORE you start, in `before.py` —
    # the order there IS the design, and test_mcp.py pins it.
    out += before.review(data)
    out += before.rules(data)
    out += before.collisions(data)
    out += before.elsewhere(data)
    out += before.resume(data)
    out += before.epic(data)
    out += ["## Spec", "", str(card.get("spec") or MISSING_SPEC), ""]
    out += _criteria(card)
    out += _graph(data)
    out += ["## History", "", *thread.lines(data.get("history"), now), ""]
    out += _commits(data)
    out += _world(data)
    return "\n".join(out)


def _head(data: dict[str, Any], card: dict[str, Any], now: float) -> list[str]:
    stone = as_object(data.get("milestone"))
    facts = [
        str(data.get("state")),
        f"priority {card.get('priority')}",
        _held(as_object(data.get("lease")), now),
    ]
    if card.get("labels"):
        facts.append(" ".join(f"#{label}" for label in as_strings(card.get("labels"))))
    spent = float(data.get("seconds") or 0)
    if spent >= 60:
        facts.append(f"{human(spent)} worked")
    return [
        f"# {card.get('id')} — {card.get('title')}",
        f"{render.BULLET} {stone.get('title', '(no milestone)')} — {stone.get('goal', '')}".rstrip(
            " —"
        ),
        " · ".join(facts),
        "",
    ]





def _criteria(card: dict[str, Any]) -> list[str]:
    """Right under the spec, because it is the other half of it: the spec says
    what to build, this says what will be checked."""
    criteria = as_strings(card.get("criteria"))
    if not criteria:
        return []
    return [
        "## Acceptance criteria",
        "",
        *[f"{n}. {line}" for n, line in enumerate(criteria, 1)],
        "",
        "_Closing says which of these you met and what proves it._",
        "",
    ]


def _graph(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    waiting = as_rows(data.get("blockers"))
    blocks = as_rows(data.get("blocks"))
    subtasks = as_rows(data.get("subtasks"))
    if waiting:
        out += ["## Waiting on", "", *_items(waiting), ""]
    if blocks:
        # A count, not a bare list: it is the argument for finishing this today.
        out += [f"## Blocking {len(blocks)} card(s)", "", *_items(blocks), ""]
    if subtasks:
        out += ["## Subtasks", "", *_items(subtasks), ""]
    return out


def _items(rows: list[dict[str, Any]]) -> list[str]:
    return [f"- {r.get('id')} ({r.get('status')}) — {r.get('title')}" for r in rows]


def _commits(data: dict[str, Any]) -> list[str]:
    """With their subjects, the files they touched and how much of each. A
    column of hashes says nothing about what was actually built (v1 shipped
    that, then fixed it), and a file name says nothing about the size of it."""
    commits = as_rows(data.get("commits"))
    merged = data.get("merged_into")
    if not commits and not merged:
        return []
    out = ["## Commits", ""]
    for commit in commits:
        out.append(f"- {sized_commit(commit)}")
    if not commits:
        out.append("- (none bound yet — `done` needs one, or no_code=true)")
    if merged:
        out += ["", f"_Integrated into {merged}._"]
    return [*out, ""]


def sized_commit(commit: dict[str, Any]) -> str:
    """One commit line: `sha  subject  (file +3-1, …)`.

    Shared with `activity.py`'s chapter story rather than written twice — a
    commit that reads one way in a card view and another in a milestone-wide
    read is two vocabularies for one fact.
    """
    files = as_strings(commit.get("files"))
    sized = [_sized(name, commit.get("numstat")) for name in files]
    tail = f"  ({', '.join(sized)})" if files else ""
    return f"{str(commit.get('sha', ''))[:8]}  {commit.get('subject', '')}{tail}"


def _sized(name: str, numstat: Any) -> str:
    """`src/x.py +3-1`, `logo.png bin`, or just the name on an event written
    before commits carried counts — absent is absent, never `+0-0`."""
    counts = as_object(numstat)
    if name not in counts:
        return name
    pair = counts[name]
    if pair is None:
        return f"{name} bin"
    if not isinstance(pair, list):
        return name
    numbers = [
        n for n in cast("list[Any]", pair) if isinstance(n, int) and not isinstance(n, bool)
    ]
    if len(numbers) != 2:
        return name
    return f"{name} +{numbers[0]}-{numbers[1]}"


def _world(data: dict[str, Any]) -> list[str]:
    return [
        "## Your world",
        "",
        f"worktree: `{data.get('worktree')}`   branch: `{data.get('branch')}`",
        "",
        "Commit in there — the `Task:` trailer is stamped for you. Never `git switch`,",
        "never merge, never push to main. Stuck or out of context →",
        '`taskops_update status=released note="got as far as X"`.',
        "",
        render.pulse(data),
    ]


def _held(lease: dict[str, Any], now: float) -> str:
    if not lease:
        return "no live holder"
    left = max(float(lease.get("expires", now)) - now, 0)
    return f"held by {lease.get('actor')} · lease {human(left) or 'under a minute'} left"
