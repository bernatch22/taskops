"""The ORCHESTRATOR's half of the board, for a reader that did not ask: the
three groups where somebody must move and the mover is a `dev:`.

Sibling of `_mentions.py`, split for the same reason and under the same rule.
`board` already derives all of this — but `board` opens with `live.renew(actor)`,
which is right for a call an actor typed (that call IS the heartbeat) and
catastrophic for a hook: renewing on somebody's behalf keeps a dead worker's
card out of STALLED, and touches `presence` besides. That is a stored `doing`
grown back by the side door. So this is the same derivation with the heartbeat
removed, exactly as `mentions` is for the ✉ group.

    merge    done, not integrated yet  → taskops_merge task=…
    review   handed in, nobody on it   → taskops_review (review it yourself)
    stalled  owned, nobody running it  → taskops_assign (hand it over)

The board's own ranking, and only the three a `dev:` can act on. TAKE is not
here: ready work is a plan, not a thing going wrong. DOING is not here for the
same reason. Nothing is stored, nothing is decided — ids and a count, and the
human picks the call.

NOT filtered by milestone, unlike `board`: a card finished in another chapter
is just as invisible and just as unmerged, and the reader of this is the one
person responsible for every chapter at once.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts
from .. import _clock
from ..core import graph
from ..store.stores import Stores

GROUPS = ("merge", "review", "stalled")


def waiting(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    """MERGE / REVIEW / STALLED, board-wide, RENEWING NOTHING.

    `tests/test_claude.py::test_the_waiting_read_renews_nothing` is the proof,
    and it is the same test the `mentions` verb carries, for the same reason.
    """
    now = _clock.now()
    cards = stores.state()["cards"]
    live = _facts.holders(stores, now)
    checking = _facts.reviewing(stores, now)
    stood = _facts.standings(stores)
    out: dict[str, list[str]] = {name: [] for name in GROUPS}
    for card in sorted(cards.values(), key=lambda c: (c["priority"], c["created"])):
        shown = graph.derived(cards, card, live, checking, stood)
        if shown == "done":
            if not _facts.merged_into(stores.events(card["id"])):
                out["merge"].append(card["id"])
        elif shown in out:
            out[shown].append(card["id"])
    return {"actor": actor, "groups": out}
