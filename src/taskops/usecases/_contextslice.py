"""Choosing what is in force, and which of it applies to one card. The slice IS the point.

Handing a worker the whole context book reproduces the problem the context layer exists to
solve — past ~150-200 standing instructions compliance decays, so a book that grows makes
every agent slightly worse. A slice is a card plus exactly the facts that bear on it.

**Two dimensions of scope, one rule each.** `labels`/`files` narrow by SUBJECT: a decision about
the database does not reach a card about the parser. `owner` narrows by PERSON: a fact somebody
stated for themselves reaches their sessions and nobody else's. A fact may carry both, and one
carrying neither is the project's and reaches everything.

What the second protects is SIZE. Three developers each stating an objective must not make every
worker read four — everybody reads the project's and their own, so a slice grows by ONE whatever
the size of the team. That is why `owner` is a filter and not a label.

Pure: facts in, facts out, no store. That is what makes the rules below testable from literals —
every project invariant survives the filter, and a tie between two machines resolves the same
way on both.
"""

from __future__ import annotations

from ..contracts import Task
from ..contracts.context import ContextSlice, Fact

__all__ = ["in_force", "for_task", "winner", "dev_of"]


def in_force(live: list[Fact], *, mine: str = "") -> ContextSlice:
    """Everything standing, as `mine` may read it. `mine` is a DEV name, "" for the overview.

    With no `mine` this is the OVERVIEW — every objective, everybody's facts — which is what
    `context show` and the board want: who is on what, when you are deciding who to hand a card
    to. With one, it is a person's own page and nobody else's private note is in it.
    """
    ours = [f for f in live if _for_me(f, mine)]
    goals = _by_owner([f for f in ours if f["sort"] == "objective"])
    return ContextSlice(objective=goals.get(""),
                        yours=goals.get(mine) if mine else None,
                        objectives=[goals[owner] for owner in sorted(goals)],
                        invariants=[f for f in ours if f["sort"] == "invariant"],
                        decisions=[f for f in ours if f["sort"] == "decision"],
                        notes=[f for f in ours if f["sort"] == "note"])


def for_task(live: list[Fact], task: Task) -> ContextSlice:
    """The slice for one card: the project's facts plus its HOLDER's, narrowed by subject.

    Invariants are not filtered by labels, and that is the load-bearing asymmetry. A decision
    that does not reach a card costs a re-litigation; an invariant that does not reach it costs
    the breakage it existed to prevent — so subject narrows decisions and never invariants.
    """
    whole = in_force(live, mine=dev_of(task["assignee"]))
    whole["decisions"] = [d for d in whole["decisions"] if _applies(d, task)]
    return whole


def _for_me(fact: Fact, mine: str) -> bool:
    """A fact with no owner is the project's and reaches everybody; one with an owner reaches
    that dev alone. `mine` of "" is the OVERVIEW and sees everything, because "who is on what"
    is the question it exists to answer."""
    owner = dev_of(fact["owner"])
    return not owner or not mine or owner == mine


def _by_owner(objectives: list[Fact]) -> dict[str, Fact]:
    """The latest objective for each owner, keyed by DEV — `""` for the project's own."""
    picked = {who: winner([f for f in objectives if dev_of(f["owner"]) == who])
              for who in {dev_of(f["owner"]) for f in objectives}}
    return {who: found for who, found in picked.items() if found is not None}


def dev_of(actor: str) -> str:
    """The person behind an actor id, or "" for anything else.

    `agent:ana/w1` answers `ana`, so a worker reads what the person who spawned it set — an
    agent and its developer are one person with two hands, which is the comparison
    `reviewer: peer` already makes. Never raises: an owner typed by hand on another machine
    must not make a slice unreadable.
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


def _applies(fact: Fact, task: Task) -> bool:
    """Unscoped facts reach everything; scoped ones reach what they overlap."""
    if not fact["labels"] and not fact["files"]:
        return True
    if set(fact["labels"]) & set(task["labels"]):
        return True
    return any(_touches(theirs, mine) for theirs in fact["files"] for mine in task["files"])


def _touches(one: str, other: str) -> bool:
    """Path overlap, either direction: a decision about `src/taskops/storage/` applies to a
    card editing one file in it, and a decision about that file applies to a card that owns
    the directory. String prefixes and not `Path.is_relative_to`, because these are repo
    paths written by hand and normalising them would invent a filesystem that may not exist.
    """
    left, right = one.rstrip("/"), other.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")
