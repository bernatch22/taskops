"""The chapter's story, rendered — and the one line a filed report answers with.

`dossier.py` is one card for the agent that will WORK it, so it opens with what
must not be missed and never truncates. This is N cards for the agent that has
to DECIDE something about all of them, so it is a table read top-down: one
block per card, the same facts in the same order, dense enough that twenty-two
of them are still one screen of reading.

Both renderers live here because both are this chapter's surface: `story()`
reads what happened, `filed()` confirms what was written about it.

No diffs, by the chapter's rule — a commit line is `sha subject (files sized)`,
which is a MEASURE. The agent that wants the patch has the branch and the sha.
"""

from __future__ import annotations

from typing import Any

from . import before, render, thread, dossier
from .._json import as_rows, as_object
from ..core.hours import human


def story(data: dict[str, Any], now: float) -> str:
    out = _head(data)
    out += before.rules(data)
    out += _reports(data, now)
    for card in as_rows(data.get("cards")):
        out += _card(card, now)
    out.append(render.pulse(data))
    return "\n".join(out)


def filed(data: dict[str, Any]) -> str:
    """A report is a POINTER, so the confirmation is the pointer read back: what
    was registered, where the bytes are, and at which commit. `recorded: false`
    is not a failure — the same path at the same sha was already on the board,
    and saying so is how a retry after a dropped connection stays quiet."""
    row = as_object(data.get("report"))
    known = "" if data.get("recorded") else " (already filed — nothing written)"
    return (
        f"◆ {row.get('title')}{known}\n"
        f"{row.get('path')} @ {str(row.get('sha'))[:8]} · {row.get('milestone')}\n"
        "It is listed on the chapter from now on — the board holds the path and the sha, "
        "never the bytes: every reader renders it from its own clone."
    )


def _head(data: dict[str, Any]) -> list[str]:
    stone = as_object(data.get("milestone"))
    shown, total = len(as_rows(data.get("cards"))), data.get("cards_total")
    facts = [
        f"{shown} of {total} cards" if shown != total else f"{total} cards",
        f"depth {data.get('depth')}",
        f"seq {data.get('seq')}",
    ]
    if data.get("since"):
        # What the cursor MEANT, not just its value: an empty list under a
        # `since=` is "nothing moved", and a reader has to be able to tell that
        # from "this chapter is empty".
        facts.insert(1, f"moved since seq {data.get('since')}")
    title = f"{render.BULLET} {stone.get('title')} — {stone.get('goal', '')}".rstrip(" —")
    return [title if stone else f"{render.BULLET} activity", " · ".join(facts), ""]


def _reports(data: dict[str, Any], now: float) -> list[str]:
    """What has been WRITTEN about this chapter — the narrations, by reference.
    Above the cards on purpose: a report is somebody's finished reading of the
    same work, and an agent about to re-derive it should see that first."""
    rows = as_rows(data.get("reports"))
    total = data.get("reports_total")
    if not rows:
        return []
    shown = [
        f"- {r.get('title')} — `{r.get('path')}` @ {str(r.get('sha'))[:8]} "
        f"({r.get('by')}, {render.ago(now - float(r.get('ts') or now))})"
        for r in rows
    ]
    head = f"## Reports ({len(rows)} of {total})" if len(rows) != total else "## Reports"
    return [head, "", *shown, ""]


def _card(card: dict[str, Any], now: float) -> list[str]:
    out = [f"### {card.get('id')}  {card.get('title')}", "", " · ".join(_facts(card)), ""]
    out += _commits(card)
    stood = as_object(card.get("standing"))
    if stood:
        # The verdict and its words, verbatim — the same rule as the dossier:
        # a summarised verdict is one the worker rebuilds against.
        out += [f"review: {stood.get('verdict') or 'submitted'} — {stood.get('note') or ''}", ""]
    if card.get("resume"):
        out += [f"released: {card['resume']}", ""]
    if card.get("spec"):
        out += ["```", str(card["spec"]), "```", ""]
    events = as_rows(card.get("thread"))
    if events:
        out += [*thread.lines(events, now), ""]
    return out


def _facts(card: dict[str, Any]) -> list[str]:
    facts = [str(card.get("state")), f"priority {card.get('priority')}"]
    who = card.get("holder") or card.get("assignee")
    if who:
        facts.append(f"{'held by' if card.get('holder') else 'assigned to'} {who}")
    spent = float(card.get("seconds") or 0)
    if spent >= 60:
        facts.append(f"{human(spent)} worked")
    quiet = card.get("quiet_for")
    if isinstance(quiet, (int, float)) and quiet >= 60:
        facts.append(f"quiet {human(float(quiet))}")
    facts.append(f"branch {card.get('branch')}")
    if card.get("merged_into"):
        facts.append(f"→ {card['merged_into']}")
    if card.get("after"):
        facts.append(f"after {', '.join(str(x) for x in card['after'] if x)}")
    # The conversation is a COUNT here, and the call that opens it. At
    # depth=headline that count is the only trace of it, on purpose
    # (`verbs/activity.py::THREAD_HEADLINE`), so it must name the way in.
    total = card.get("thread_total")
    if isinstance(total, int) and total > len(as_rows(card.get("thread"))):
        facts.append(f"{total} events (depth=full)")
    return facts


def _commits(card: dict[str, Any]) -> list[str]:
    rows = as_rows(card.get("commits"))
    if not rows:
        return []
    return [f"- {dossier.sized_commit(commit)}" for commit in rows] + [""]
