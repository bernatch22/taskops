"""card — one card in full, or a search across titles and specs."""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context
from .. import _clock
from ..core import graph
from .._errors import BadRequest
from ..store.stores import Stores


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    stores.live.renew(actor, now)
    query = _args.text(args, "query", default="")
    if query:
        return {"query": query, "matches": _search(stores, query, now)}
    task = _args.ident(args, "task", default="")
    if not task:
        raise BadRequest("taskops_card takes task=<tk-…> or query=<text>")
    return _context.dossier(stores, actor, _facts.find(stores, task), now)


def _search(stores: Stores, query: str, now: float) -> list[dict[str, Any]]:
    """Titles and specs — the two places a human wrote what the card is about.
    Comments are history, not identity; searching them buries the signal."""
    needle = query.lower()
    cards = stores.state()["cards"]
    live = _facts.holders(stores, now)
    checking, stood = _facts.reviewing(stores, now), _facts.standings(stores)
    hits: list[dict[str, Any]] = []
    for card in cards.values():
        where = (
            "title"
            if needle in card["title"].lower()
            else "spec"
            if needle in card["spec"].lower()
            else ""
        )
        if not where:
            continue
        hits.append(
            {
                "id": card["id"],
                "title": card["title"],
                "state": graph.derived(cards, card, live, checking, stood),
                "assignee": card["assignee"],
                "holder": stores.live.holder(card["id"], now),
                "matched": where,
            }
        )
    return sorted(hits, key=lambda h: h["id"])
