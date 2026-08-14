"""update — comment, close, hand back, drop, edit, or declare a dependency.

One verb for every way a card changes after it exists, because the alternative
is what v1 became: fourteen closing rules spread over six modules, and the one
that recorded the result was forgotten in exactly one of two entry points.

`status=released` is the honest exit: it hands the card back with a note that
the next worker is shown verbatim. Silence is the only outcome that is refused.

`comment=… mentions=[…]` addresses that comment to somebody: they see it in the
pulse line of their very next call, whatever they call, and it clears itself
the moment they touch the card. There is no verb to mark it read.

A CLOSED card can still be commented on — no guard below, and never one
(2026-08-14: reported as a refusal, not reproduced): the log is append-only, so
a postscript on shipped work is how it stays honest. What it does NOT do is
deliver — `_facts.pending_mentions` skips closed cards, so a `mentions=` written
after the close pages nobody, silently. Deliberate, argued at that site.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context
from .. import _clock
from ..core import graph, machine
from .._errors import Refused, NotFound, BadRequest
from ..core.event import make
from ..core.types import PROJECT, EDITABLE, LIST_FIELDS, Card, Event, role_of
from ..store.stores import Stores

# The plain fields; `after`, `milestone` and `assignee` have their own paths.
FIELDS = tuple(f for f in EDITABLE if f not in ("after", "milestone", "assignee"))


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    if not args.get("task") and args.get("milestone"):
        return _milestone(stores, actor, args, now)

    card = _facts.find(stores, _args.ident(args, "task"))
    comment = _args.text(args, "comment", default="")
    status = _args.text(args, "status", default="")
    events: list[Event] = []

    if comment and not status:
        # With a status, the comment IS the note/reason and travels inside that
        # event. Writing both put the same sentence in the thread twice.
        events.append(make(card["id"], actor, "comment", _comment(comment, args), now))
    elif args.get("mentions"):
        raise BadRequest(
            'mentions= rides on a comment: taskops_update task=… comment="…" mentions=[…]. '
            "With status=, the note IS the status event, so the address would be dropped."
        )
    events.extend(_edits(stores, card, actor, args, now))
    if status:
        events.extend(_transition(stores, card, actor, status, comment, args, now))
    if not events:
        raise BadRequest(
            "update needs something to say: comment=…, status=…, after=…, or a field to edit"
        )
    seq = stores.write(events)
    stores.live.renew(actor, now)
    fresh = _facts.find(stores, card["id"])
    return {
        "card": fresh,
        # With the review facts, or handing a card IN would answer "doing" —
        # the one call whose whole point was to stop working on it.
        "state": graph.derived(
            stores.state()["cards"],
            fresh,
            _facts.holders(stores, now),
            _facts.reviewing(stores, now),
            _facts.standings(stores),
        ),
        "seq": seq,
        "pulse": _context.pulse(stores, actor, now, fresh["milestone"]),
    }


def _comment(text: str, args: _args.Args) -> dict[str, Any]:
    """The comment body, plus who it is addressed to.

    `mentions` is an EXTRA key on a kind that already exists: `make()` keeps
    extras intact, so no new kind, no replay change, and no second place where
    "somebody must read this" could be recorded. Each address goes through the
    actor grammar's own validator — an address nobody can ever match is a
    mention that stays pending forever, so a typo is refused at the write.
    """
    body: dict[str, Any] = {"text": text}
    mentions = _args.strings(args, "mentions")
    for who in mentions:
        role_of(who)
    if mentions:
        body["mentions"] = mentions
    return body


def _edits(stores: Stores, card: Card, actor: str, args: _args.Args, now: float) -> list[Event]:
    events: list[Event] = []
    for field in FIELDS:
        if field not in args:
            continue
        value: Any = (
            _args.number(args, field, default=2, low=0, high=3)
            if field == "priority"
            else _args.flag(args, field)
            if field == "review"
            else _args.strings(args, field)
            if field in LIST_FIELDS
            else _args.text(args, field)
        )
        events.append(make(card["id"], actor, "edited", {"field": field, "to": value}, now))
    if args.get("after"):
        after = _args.ident(args, "after")
        graph.check_dep(stores.state()["cards"], card["id"], after)
        merged = sorted({*card["after"], after})
        events.append(make(card["id"], actor, "edited", {"field": "after", "to": merged}, now))
    if args.get("milestone"):
        stone = _args.text(args, "milestone")
        if stone not in stores.state()["milestones"]:
            raise NotFound(f"milestone {stone} does not exist")
        events.append(make(card["id"], actor, "edited", {"field": "milestone", "to": stone}, now))
    return events


def _transition(
    stores: Stores,
    card: Card,
    actor: str,
    status: str,
    comment: str,
    args: _args.Args,
    now: float,
) -> list[Event]:
    facts = _facts.facts(stores, card, now)
    if status == "review":
        # Handing in, not a stored status — the same shape as `released`. The
        # worker keeps its lease on purpose: it stays reachable for a verdict.
        if not card.get("review"):
            raise Refused(
                f"{card['id']} does not require review — close it: "
                f'taskops_update task={card["id"]} status=done note="…"'
            )
        machine.check_release(card, facts, actor, comment)  # same rules: yours, and never silent
        return [make(card["id"], actor, "submitted", {"note": comment}, now)]
    if status == "released":
        machine.check_release(card, facts, actor, comment)
        stores.live.release(card["id"], actor)
        return [make(card["id"], actor, "released", {"note": comment}, now)]

    no_code = _args.flag(args, "no_code")
    machine.check_transition(
        card, facts, actor, status, reason=comment, no_code=no_code, has_comment=bool(comment)
    )
    body: dict[str, Any] = {"to": status}
    if comment:
        body["reason"] = comment
    if no_code:
        body["no_code"] = True
    stores.live.release(card["id"], actor)  # closing or reopening ends the claim
    return [make(card["id"], actor, "status", body, now)]


def _milestone(stores: Stores, actor: str, args: _args.Args, now: float) -> dict[str, Any]:
    """Close or retitle a chapter. The branch never moves — it was stored at birth."""
    ident = _args.text(args, "milestone")
    stone = stores.state()["milestones"].get(ident)
    if stone is None:
        raise NotFound(f"milestone {ident} does not exist")
    body: dict[str, Any] = {"id": ident}
    status = _args.text(args, "status", default="")
    if status:
        if status not in ("open", "done", "dropped"):
            raise BadRequest("a milestone is open, done or dropped")
        body.update({"op": "status", "to": status})
    else:
        body["op"] = "edit"
        for field in ("title", "goal"):
            if field in args:
                body[field] = _args.text(args, field)
        if "rules" in args:
            body["rules"] = _args.strings(args, "rules")  # the whole list, never appended to
        if "criteria" in args:
            body["criteria"] = _args.strings(args, "criteria")  # same shape as rules
        if "reviews" in args:
            body["reviews"] = _args.flag(args, "reviews")
        if len(body) == 2:
            raise BadRequest(
                "nothing to change: pass status=, title=, goal=, rules=, criteria= or reviews="
            )
    seq = stores.write([make(PROJECT, actor, "milestone", body, now)])
    stores.live.renew(actor, now)
    return {
        "milestone": stores.state()["milestones"][ident],
        "seq": seq,
        "pulse": _context.pulse(stores, actor, now, ident),
    }
