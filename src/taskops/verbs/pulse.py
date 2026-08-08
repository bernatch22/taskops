"""board — the one read that says what the board is waiting for, and `mentions`,
its ✉ half alone, for the delivery hook.

Grouped by the move each card needs, in the order to act:

    MERGE    done, not integrated yet     → taskops_merge
    MENTIONS addressed to YOU, unanswered → read the card and answer on it
    STALLED  owned, nobody running it     → taskops_assign (hand it to somebody)
    TAKE     ready                        → taskops_assign
    DOING    somebody holds the lease     → nothing
    BLOCKED  waiting on a dependency      → close the blocker

Every one of those six is DERIVED — from the graph, from who holds a live
lease, and (for MENTIONS) from who has not spoken on a thread since being
named. Nothing here writes, and there is no repair verb, because there is
nothing to repair: a worker that stops renewing leaves DOING on its own and its
card shows up under STALLED with the move written next to it.

MENTIONS is ranked above STALLED because a card going quiet can wait a turn and
a question addressed to you by name usually cannot. It is the only group that
differs per reader: the orchestrator sees what was addressed to `dev:<name>`,
each worker what was addressed to its own `agent:<dev>/<name>`.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, report, _context, _mentions
from .. import _clock
from ..core import graph
from ..core.types import Card
from ..store.stores import Stores

DONE_SHOWN = 20
"""How many closed cards ride along when NO chapter is in scope. The cap is the
whole reason `done` can be in this payload at all: every other group is bounded
by how much work is in flight, and closed work only ever grows."""

DONE_FOCUSED = 200
"""And how many when a chapter IS in scope. Different because the thing being
bounded is different: with no chapter, `done` is the board's entire history and
grows forever; with one, it is that chapter's closed cards, and a chapter is a
finite planned unit that somebody sat down and wrote. Reviewing a landed chapter
is exactly when a reader wants ALL of them — this project's own chapters closed
14 and 22 cards, and `20 of 22` is a screen that cannot answer "what shipped".
It is still a ceiling and not `None`: a pathological chapter must not be able to
make this read unbounded, and `done_total` stays the honest count behind either
cap."""



def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    stores.live.renew(actor, now)
    state = stores.state()
    cards = state["cards"]
    live = _facts.holders(stores, now)
    stone = _facts.in_scope(stores, _args.text(args, "milestone", default=""))
    mine = [c for c in cards.values() if not stone or c["milestone"] == stone["id"]]

    # The whole review lease, not just the name: a `reviewing` row has to say
    # how much of THAT lease is left, and the work lease's `since` can only
    # bound it from below (`_row`'s `since` note). Same query either way.
    live_reviews = _facts.review_leases(stores, now)
    checking = {task: lease.actor for task, lease in live_reviews.items()}
    stood = _facts.standings(stores)
    # REVIEW above STALLED: finished work nobody is checking is more blocking
    # than work nobody has started. CHANGES right after it — the fix is usually
    # seconds of an agent's time and it unblocks a merge.
    groups: dict[str, list[dict[str, Any]]] = {
        "merge": [],
        "mentions": _mentions.rows(stores, actor),
        "review": [],
        "changes": [],
        "stalled": [],
        "take": [],
        "doing": [],
        "reviewing": [],
        "blocked": [],
        # LAST, and it is not a move the board is waiting for: it is the only
        # place finished work is visible at all. A merged card used to be
        # dropped from this payload entirely, so a chapter's whole history
        # existed in the log and on no screen. Capped and newest-first: a
        # chapter is bounded, a board is not, and an uncapped tail would grow
        # this read forever.
        "done": [],
    }
    for card in sorted(mine, key=lambda c: (c["priority"], c["created"])):
        shown = graph.derived(cards, card, live, checking, stood)
        row = _row(stores, card, now, live)
        if shown == "done":
            if not _facts.merged_into(stores.events(card["id"])):
                groups["merge"].append(row)
            else:
                groups["done"].append(row)
        elif shown == "blocked":
            groups["blocked"].append(row | {"waiting_on": graph.blockers(cards, card["id"])})
        elif shown in ("review", "changes"):
            # The reason, not just the id: the submit note (review) or the
            # reviewer's words (changes), like a MENTIONS row carries the text.
            note = stood[card["id"]].note if shown == "changes" else ""
            groups[shown].append(row | {"text": note, "holder": checking.get(card["id"])})
        elif shown == "reviewing":
            # `review_since` is the REVIEW lease's own acquisition, and it is a
            # second key rather than a better `since` because the two are
            # different leases on the same card: `since` stays the work lease's,
            # held by the worker who may still be alive beside the verifier.
            # Conflating them is what made the countdown a floor that read 0
            # under a live lease.
            #
            # `quiet_for` on this row has the SAME split and is deliberately
            # left alone: `_row` fills it from the work lease, so a card handed
            # in an hour ago with a verifier actively on it arrives saying
            # `quiet_for = 3600`. That is not wrong — the WORKER has been quiet
            # for an hour — it is only unreadable next to a `holder` that was
            # overwritten with the verifier. A reader that wants the verifier's
            # timing now has it exactly, here, and does not have to reinterpret
            # a number that belongs to the other lease. Redefining `quiet_for`
            # per group would make one key mean two things, which is the shape
            # of the bug this key exists to end.
            lease = live_reviews.get(card["id"])
            groups["reviewing"].append(
                row
                | {
                    "holder": checking.get(card["id"]),
                    "review_since": lease.acquired if lease else None,
                }
            )
        elif shown == "ready":
            groups["take"].append(row)
        elif shown in groups:
            groups[shown].append(row)

    # Newest first, and only the tail: the other groups are sorted by what to do
    # next, but nobody acts on a closed card — what a reader wants is what just
    # landed. `done_total` is the honest count behind the cap, so a screen can
    # say "20 of 63" instead of implying the chapter closed twenty cards.
    done_total = len(groups["done"])
    cap = DONE_FOCUSED if stone else DONE_SHOWN
    groups["done"] = sorted(groups["done"], key=lambda r: r["since"], reverse=True)[:cap]

    chapters, landed_total = _facts.chapters(stores)

    window = _args.text(args, "window", default="")
    return {
        "done_total": done_total,
        # Where this repo lives on the web, or absent — `verbs/project.py`.
        # A board that never recorded one sends nothing, and every consumer
        # falls back to plain text: no origin, no links, no noise.
        "repo": state["project"].get("remote"),
        "milestone": stone,
        # The open chapters AND the recent landed ones. Sending only the open
        # ones was correct while `open` was the only status a chapter ever had;
        # the day `landed` became real (`core/replay.py::_milestone`) two
        # finished chapters — 36 cards, their goals, rules and threads — existed
        # in the log and on no screen. That is `groups.done`'s bug one level up,
        # and it is fixed the same way: capped, newest first, with the total.
        "milestones": chapters,
        "landed_total": landed_total,
        "groups": groups,
        "team": _team(stores, now),
        "hours": _hours(stores, args, now, window) if window else None,
        "seq": stores.head(),
        "pulse": _context.pulse(stores, actor, now, stone["id"] if stone else ""),
    }


def _row(stores: Stores, card: Card, now: float, live: dict[str, str]) -> dict[str, Any]:
    """One line of the board. `quiet_for` is what makes STALLED actionable: it
    says how long since the owner last said anything, not a guess about why."""
    holder = live.get(card["id"])
    lease = stores.live.lease(card["id"], now) if holder else None
    return {
        "id": card["id"],
        "title": card["title"],
        "priority": card["priority"],
        "assignee": card["assignee"],
        "holder": holder,
        "since": lease["acquired"] if lease else card["updated"],
        "quiet_for": None if holder else now - card["updated"],
        "files": card["files"],
        "labels": card["labels"],
    }


def _team(stores: Stores, now: float) -> list[dict[str, Any]]:
    return [
        {"actor": actor, "seen": seen, "ago": now - seen}
        for actor, seen in stores.live.present(now - 24 * 3600)
    ]


def _hours(stores: Stores, args: _args.Args, now: float, window: str) -> dict[str, Any]:
    """`window="7d"` folds the report into the same read — one call, one picture."""
    tz = _args.text(args, "tz", default="UTC") or "UTC"
    return report.summary(stores, now, report.days(window), tz)
