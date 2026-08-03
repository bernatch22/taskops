"""Choosing what is in force, and which of it applies to one card. The slice IS the point.

Handing a worker the whole context book reproduces the problem the context layer exists to
solve — past ~150-200 standing instructions compliance decays, so a book that grows makes
every agent slightly worse. A slice is a card plus exactly the facts that bear on it.

**THREE dimensions of scope, one rule each.** `labels`/`files` narrow by SUBJECT: a decision about
the database does not reach a card about the parser. `owner` narrows by PERSON: a fact somebody
stated for themselves reaches their sessions and nobody else's. And `milestone` narrows by
CHAPTER: a fact belongs to the one open when it was written, and leaves every slice when that
chapter is reached.

The three protect different things, and the last two protect SIZE from the two directions it
grows. `owner` stops it growing with the TEAM — everybody reads the project's facts and their own,
so a slice grows by one whether three people are on the board or thirty. `milestone` stops it
growing with the YEAR: a decision taken in March is no longer injected in December, and nobody had
to retire it by hand.

Several chapters are active at once, so "the chapter" is not a property of the board. It is a
property of the READER: a card belongs to exactly one, and that is the one whose facts it gets.

Pure: facts in, facts out, no store. That is what makes the rules below testable from literals —
every project-wide fact survives the filter, and a tie between two machines resolves the same
way on both.
"""

from __future__ import annotations

from ..contracts import Task
from ..contracts.context import Fact
from ..contracts.slice import Chapters, ContextSlice
from ._whose import by_owner, dev_of, for_me

__all__ = ["in_force", "for_task"]


def in_force(live: list[Fact], chapters: Chapters, *, mine: str = "") -> ContextSlice:
    """Everything standing, as `mine` may read it. `mine` is a DEV name, "" for the overview.

    With no `mine` this is the OVERVIEW — every objective, everybody's facts — which is what
    `context show` and the board want: who is on what, when you are deciding who to hand a card
    to. With one, it is a person's own page and nobody else's private note is in it.

    A fact of a CLOSED chapter is in neither: it left the slice when that chapter was reached,
    which is the whole point of attaching it to one. `context log` and an explicit `milestone=<id>`
    read are where it stays visible.
    """
    ids = {m["id"] for m in chapters.active}
    ours = [f for f in live if for_me(f, mine) and _standing(f, ids)]
    project = [f for f in ours if f["level"] == "project"]
    chapter = [f for f in ours if f["level"] != "project"]
    goals = by_owner([f for f in chapter if f["sort"] == "objective"])
    return ContextSlice(
        milestone=None, active=chapters.active, counts=chapters.counts,
        planned=chapters.planned,
        project_rules=[f for f in project if f["sort"] == "rule"],
        project_decisions=[f for f in project if f["sort"] == "decision"],
        rules=[f for f in chapter if f["sort"] == "rule"],
        decisions=[f for f in chapter if f["sort"] == "decision"],
        notes=[f for f in chapter if f["sort"] == "note"],
        yours=goals.get(mine) if mine else None,
        objectives=[goals[owner] for owner in sorted(goals)])


def _standing(fact: Fact, active: set[str]) -> bool:
    """Is this fact still in force? Project-level always; chapter-level only while its chapter is.

    A fact with no `milestone` and `level="milestone"` cannot happen going forward — `state`
    resolves the chapter at write time — but it CAN arrive from a board written before milestones
    existed. Those read as standing, the same rule the `invariant` mapping keeps: a board's facts
    may not vanish because a version changed.
    """
    if fact["level"] == "project" or not fact["milestone"]:
        return True
    return fact["milestone"] in active


def for_task(live: list[Fact], task: Task, chapters: Chapters, *,
             entered_review_by: str = "") -> ContextSlice:
    """The slice for one card: the project's facts plus its AUTHOR's, narrowed by subject.

    Subject narrows DECISIONS, and there is nothing left it does not narrow. There used to be:
    `invariant` was a sort that skipped this filter, so a rule reached every card whatever its
    labels said. The sort is gone (see `contracts.context.Sort` for why), and the consequence is
    the one thing this removal cost — a rule that must reach every card is now a decision with NO
    `labels` and NO `files`, and scoping it narrows it silently. `_applies` is the whole of it.

    `entered_review_by` is who HANDED THE CARD OVER, and it wins over `assignee` because in the
    one case a slice is read by somebody other than the worker — a verifier reading a card in
    review — `assignee` no longer names the author: routing borrows that field to name the
    chosen REVIEWER, so the verifier was handed its own objective and never the author's, which
    is the one it needs to judge the work against. Empty for a card that is not sitting in a
    review, so every other flow keeps reading the holder's.

    It is a PARAMETER and not a lookup because that answer lives in the event log, and this
    module stays pure: facts in, facts out, no store. The caller resolves it — `_facts.
    entered_review_by`, the same derivation the closing guards use, so the author of a card is
    one answer here and not two able to disagree.

    The slice still grows by ONE. Project plus one person, never plus the verifier as well: the
    size property is what the owner filter exists for, and a review is the moment the person
    whose objective matters is the author rather than the reader.
    """
    whole = in_force(live, chapters, mine=dev_of(entered_review_by) or dev_of(task["assignee"]))
    mine = task["milestone"]
    # ONE chapter — its own. Several are active, and handing a worker all of them would put the
    # bound back where it was before: on the board rather than on the reader.
    whole["milestone"] = next((m for m in chapters.active if m["id"] == mine), None)
    whole["active"] = []
    for key in ("rules", "decisions", "notes", "objectives"):
        whole[key] = [f for f in whole[key] if not f["milestone"] or f["milestone"] == mine]
    # Subject narrows decisions and notes, and NOT rules: a decision that misses a card costs a
    # re-litigation, a rule that misses one costs the breakage it existed to prevent. Notes were
    # not narrowed until 0.5.0, so a note scoped to `[importador]` was reaching cards about the
    # parser — the scope somebody bothered to write meant nothing.
    whole["decisions"] = [d for d in whole["decisions"] if _applies(d, task)]
    whole["notes"] = [n for n in whole["notes"] if _applies(n, task)]
    whole["project_decisions"] = [d for d in whole["project_decisions"] if _applies(d, task)]
    return whole


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
