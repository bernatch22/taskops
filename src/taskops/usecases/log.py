"""`taskops log <task>` — what the agent actually said while working on a card.

The card already knows enough to find it without any new bookkeeping: `dispatch` puts every worker in
`<repo>/.taskops/trees/<id>/`, and Claude Code names a transcript directory after the working directory
it ran in. So the lookup is a path computation, and it works on transcripts written before taskops knew
it would ever read them — the axion-v3 workers' conversations were recoverable after the fact.

Two directories are searched, in this order:

1. **the card's worktree** — one directory per card, so everything in it belongs to this card
2. **the repository itself** — shared by every session anybody ran there, so it needs a filter

For (2) there are two ways to prove an entry belongs, and the path computation alone is not enough. A
dispatched agent makes a branch, so `gitBranch` identifies it. A person who claimed a card in their own
terminal usually stays on `main`, and every one of their entries would be discarded — so the card also
remembers WHICH sessions worked it, and a transcript named by a recorded session id is read whole.

Nothing is copied into the event log. A transcript is 200 KB for 40 turns, `events.jsonl` is committed,
and the value of that file is that a human can read its diff. The consequence is stated plainly in the
contract: a transcript is LOCAL, and a teammate who pulls gets the card and the commits but not this.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import LogEntry, SessionLog
from ..engine import branch_for
from ..engine._entries import flatten
from ..engine.transcript import directories_for, home, read_entries
from ..engine.worker import worktree_for
from ..storage import Store
from ._project import project

__all__ = ["session_log", "MAX_ENTRIES"]

MAX_ENTRIES = 400
"""Entries kept, newest last. A long session runs to thousands, and a viewer wants the shape of the
work plus how it ended — so when it truncates, it keeps the END and says so."""


def session_log(start: Path | str, task_id: str, *, limit: int = MAX_ENTRIES) -> SessionLog:
    """The conversation for one card, oldest first."""
    with project(start) as store:
        task = store.tasks.need(task_id)
        branch = branch_for(task)
        tree = worktree_for(store.root, task)
        places = directories_for(store.root, tree)
        if not places:
            return _empty(task_id, _nowhere(store, tree))
        entries = _gather(places, tree, branch, _recorded(store, task_id))
        if not entries:
            return _empty(task_id, _silent(store, task_id, places))
        return _bounded(task_id, entries, ", ".join(str(p) for p in places), limit)


def _recorded(store: Store, task_id: str) -> tuple[str, ...]:
    """The session ids known to have worked this card — from its live lease and from its own history.

    The lease is the current holder; the events are every past one, which matters because a card that
    was released and re-claimed has more than one conversation and both are worth reading.
    """
    held = store.leases.get(task_id)
    found = [held["session"]] if held else []
    found += [str(event["body"].get("session", ""))
              for event in store.events.of_task(task_id)]
    return tuple(dict.fromkeys(name for name in found if name))


def _gather(places: list[Path], tree: Path, branch: str,
            sessions: tuple[str, ...]) -> list[LogEntry]:
    """Read every place, flatten every line, then order by time.

    Sorted at the END rather than per file: two sessions on one card can overlap, and a viewer showing
    them concatenated would imply an order that did not happen.
    """
    out: list[LogEntry] = []
    for place in places:
        # The worktree's directory holds only this card's sessions, so it needs no filter. The
        # repository's is shared, so an entry has to prove it belongs by naming the card's branch.
        wanted = "" if place.name.endswith(tree.name) else branch
        for raw in read_entries(place, branch=wanted, sessions=sessions):
            out += flatten(raw)
    return sorted(out, key=lambda entry: entry["ts"])


def _bounded(task_id: str, entries: list[LogEntry], source: str,
             limit: int) -> SessionLog:
    """Keep the LAST `limit` entries, and say when that happened.

    The end, not the beginning: a person opening a card's log is usually asking how it went, and the
    answer is in the last few turns. Silence about the truncation would be a lie about the ending.
    """
    kept = entries[-limit:] if len(entries) > limit else entries
    return SessionLog(task=task_id, sessions=_sessions(kept), entries=kept,
                      source=source, truncated=len(entries) > limit)


def _sessions(entries: list[LogEntry]) -> list[str]:
    """The session ids present, in the order they first appear. More than one is normal — a card can be
    released and picked up again, and each attempt is its own session."""
    return list(dict.fromkeys(entry["session"] for entry in entries if entry["session"]))


def _empty(task_id: str, why: str) -> SessionLog:
    return SessionLog(task=task_id, sessions=[], entries=[], source=why, truncated=False)


def _silent(store: Store, task_id: str, places: list[Path]) -> str:
    """The directory exists and holds nothing for this card. Say which of the two reasons it is.

    An empty pane that only prints a path reads as a broken viewer — it was reported as one. The
    difference that matters to the reader: nobody ever worked this card in a Claude Code session (there
    is nothing to show, and that is fine), versus somebody did but the entries cannot be attributed,
    which happens for interactive work done before the card started recording its sessions.
    """
    looked = ", ".join(str(place) for place in places)
    if _recorded(store, task_id):
        return (f"a session is recorded for this card but none of its entries were found in {looked}. "
                f"The transcript may have been written under a different Claude Code home.")
    return ("no Claude Code session is recorded against this card, so there is no conversation to "
            f"show. Sessions are recorded from the claim onwards; searched {looked}.")


def _nowhere(store: Store, tree: Path) -> str:
    """Why there is nothing, specifically enough to act on.

    A viewer that shows an empty pane cannot distinguish "this agent said nothing" from "taskops looked
    in the wrong place", and the second has a fix — which is usually `$CLAUDE_CONFIG_DIR`, because a
    second Claude Code home is exactly how the first version of this found nothing at all.
    """
    return (f"no transcript directory for this card. Looked under {home() / 'projects'} for "
            f"{tree} and {store.root}. If Claude Code stores its config elsewhere, "
            f"$CLAUDE_CONFIG_DIR is what points here.")
