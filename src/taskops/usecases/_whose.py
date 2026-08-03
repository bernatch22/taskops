"""Whose fact is this, and which of two is current. The PERSON dimension of a slice.

Split out of `_contextslice` when it filled up, and the line is the dimension: that module decides
what is in force and what one card is about, these four decide who a fact belongs to. The split is
also why `_joins` and `_statusfacts` stop importing a slice builder to ask one question about an
actor id — they were reaching through the wrong module for the right function.

Pure and total. Nothing here opens a store or raises: an owner typed by hand on another machine
must not be able to make a slice unreadable.
"""

from __future__ import annotations

from ..contracts.context import Fact

__all__ = ["dev_of", "winner", "for_me", "by_owner"]


def dev_of(actor: str) -> str:
    """The person behind an actor id, or "" for anything else.

    `agent:ana/w1` answers `ana`, so a worker reads what the person who spawned it set — an
    agent and its developer are one person with two hands, which is the comparison
    `reviewer: peer` already makes.
    """
    kind, _, rest = actor.strip().partition(":")
    if kind == "dev" and rest and "/" not in rest:
        return rest
    return rest.partition("/")[0] if kind == "agent" and "/" in rest else ""


def winner(objectives: list[Fact]) -> Fact | None:
    """The current objective: the latest by `(ts, id)`.

    The tiebreak is the point, not the decoration. Two machines adding an objective offline
    can produce the same timestamp, and `id` is the CONTENT hash — identical on both — so
    both clones elect the same winner without talking. Comparing on arrival order instead
    would give each machine its own answer, which is a split brain nobody would notice.
    """
    return max(objectives, key=lambda f: (f["ts"], f["id"]), default=None)


def for_me(fact: Fact, mine: str) -> bool:
    """A fact with no owner is the project's and reaches everybody; one with an owner reaches
    that dev alone. `mine` of "" is the OVERVIEW and sees everything, because "who is on what"
    is the question it exists to answer."""
    owner = dev_of(fact["owner"])
    return not owner or not mine or owner == mine


def by_owner(objectives: list[Fact]) -> dict[str, Fact]:
    """The latest objective for each owner, keyed by DEV — `""` for the project's own."""
    picked = {who: winner([f for f in objectives if dev_of(f["owner"]) == who])
              for who in {dev_of(f["owner"]) for f in objectives}}
    return {who: found for who, found in picked.items() if found is not None}
