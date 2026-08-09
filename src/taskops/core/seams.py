"""seams — which ready cards name the same CONCEPT, from the specs alone.

THE COST. This project's most repeated failure is two workers building the same
thing at the same time: two `ago()`, three `initials()` (docs/fan-out.md), two
`src/taskops/gitwork/remote.py` — same path, complementary halves — "because
both their specs said check `git remote get-url origin`" (ARCHITECTURE.md §16),
two smoke sections both numbered §9, two `const reviewed` in one scope.
fan-out.md's conclusion is a sentence in `mcp/server.py::INSTRUCTIONS` — a
CONCEPT named by two cards is a seam, land it serialized FIRST — and twice in
one week it was not remembered, because nothing on the board computed it.

`verbs/_context.py::collisions` already warns on overlapping declared FILES,
but per-take, one card at a time, AFTER the dispatch. The moment that decides
parallelism is earlier: the orchestrator looking at the ready column.

THE GRAMMAR, and why it is this narrow. `terms()` reads PROSE — the spec the
planner wrote — and never the repository: "taskops never parses source code" is
fan-out.md's other conclusion and it does not move. Two shapes count:

* a BACKTICKED span that is more than one bare word — `git remote get-url
  origin` (whitespace) or `live.renew` (a joiner). A lone `` `done` `` is
  dropped: half the specs on this board backtick it.
* an IDENTIFIER: a token joined by `::`, `.`, `/` or `_` — `panels.ts::WorktreeRow`,
  `verbs/pulse.py::run`, `store/cache.py`, `done_total`.

`-` is NOT a joiner, so "post-mortem" and "read-only" are prose. Everything
shorter than MIN_LENGTH is dropped, everything is lowercased, and ORDINARY
PROSE YIELDS NOTHING — "the board refuses" is the empty set. That is the whole
design constraint: the wave is advice, and one false hold teaches an
orchestrator to stop reading it. A missed seam costs a duplicated helper; a
false hold costs the feature.

Pure (layer 1): no I/O, no clock, no store. `wave()` is the partition the board
publishes — greedy, in the ready column's own priority order, and deliberately
not optimal: the exact answer is NP-shaped and this one is ADVICE, never a lock.
Nothing here is stored; it is recomputed on every read of the board.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from .types import Card

MIN_LENGTH = 4
"""Below this a "concept" is a preposition. `git`, `ago`, `ms` are noise."""

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_CANDIDATE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]*[A-Za-z0-9_]")
_JOINER = re.compile(r"::|[./_]")


def terms(spec: str) -> frozenset[str]:
    """The concept-bearing tokens of one spec. Ordinary prose yields nothing."""
    found: set[str] = set()
    for span in _BACKTICKED.findall(spec):
        phrase = " ".join(span.split()).lower()
        if len(phrase) >= MIN_LENGTH and (" " in phrase or _JOINER.search(phrase)):
            found.add(phrase)
    for token in _CANDIDATE.findall(spec):
        if len(token) >= MIN_LENGTH and _JOINER.search(token):
            found.add(token.lower())
    return frozenset(found)


def overlaps(cards: dict[str, str]) -> list[tuple[str, str, frozenset[str]]]:
    """Every pair of the given `{id: spec}` that names a concept in common.

    Pairs sharing nothing are dropped rather than sent with an empty set: the
    caller wants the seams, and a list of every pair on the board is the noise
    this module exists to avoid.
    """
    extracted = {ident: terms(spec) for ident, spec in cards.items()}
    idents = sorted(cards)
    out: list[tuple[str, str, frozenset[str]]] = []
    for position, one in enumerate(idents):
        for other in idents[position + 1 :]:
            shared = extracted[one] & extracted[other]
            if shared:
                out.append((one, other, shared))
    return out


def wave(cards: dict[str, Card], ready: Sequence[str]) -> dict[str, Any] | None:
    """The dispatch-safe set among `ready`, and WHY each of the rest waits.

    Greedy in the order given (the board's own priority order): a card joins
    `safe` when it shares neither a declared file nor a spec term with anything
    already in it, and otherwise lands in `held` naming the FIRST card it clashes
    with and the exact overlap. `None` when there is nothing to decide — one
    ready card cannot collide with itself, and a board with none spends nothing.
    """
    if len(ready) < 2:
        return None
    theirs = {i: terms(cards[i]["spec"]) for i in ready if i in cards}
    safe: list[str] = []
    held: list[dict[str, Any]] = []
    for ident in ready:
        card = cards.get(ident)
        if card is None:
            continue
        why = _clash(cards, theirs, safe, ident, card)
        if why is None:
            safe.append(ident)
        else:
            held.append({"id": ident, "title": card["title"], "why": why})
    return {"safe": safe, "held": held}


def _clash(
    cards: dict[str, Card],
    theirs: dict[str, frozenset[str]],
    safe: Sequence[str],
    ident: str,
    card: Card,
) -> dict[str, Any] | None:
    """FILES before TERMS: a shared file is a fact the planner declared, a shared
    term is an inference from prose. When both hold, the reader gets the fact."""
    for chosen in safe:
        files = sorted(set(card["files"]) & set(cards[chosen]["files"]))
        if files:
            return {"with": chosen, "files": files}
        shared = sorted(theirs[ident] & theirs[chosen])
        if shared:
            return {"with": chosen, "terms": shared}
    return None
