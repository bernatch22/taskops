"""What Claude Code's bottom bar shows — the ONE read in this package that is allowed to be stale.

Every other read here either goes to the server or says loudly that it could not. This one does
neither, and both halves of that are deliberate:

- **It never touches the network.** Claude Code re-runs a status line on a 300 ms debounce, on
  every tool call and every message. An HTTP round trip on that cadence would put a request per
  keystroke-burst on a shared board and hang the bar whenever the box was slow — a footer that
  freezes is worse than a footer that is a second behind.
- **It never writes.** No `heartbeat`, no `unblock`, no lease renewal. `attention` does all
  three and is right to: it runs once a turn and its caller is about to act. A bar runs
  hundreds of times and its reader is typing. A projection that wrote would make MERELY LOOKING
  at the screen an event on an append-only log.

So it reads one local sqlite and says `local: false` when that sqlite is a replica, which is
the renderer's cue to mark the bar as a cache rather than the truth.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from ..contracts.bar import Bar, Holding
from ..engine.attention import waiting_on
from ..storage import Store
from ._contextviews import chapters
from ._project import caller, project
from .remote import read_remote
from .view import inbox_for

__all__ = ["statusline"]


def statusline(start: Path | str, *, actor: str = "") -> Bar:
    """The bottom bar, from this machine's cache. Reads only, and never off this disk."""
    shared = read_remote(start)
    with project(start) as store:
        who = caller(store, actor)["id"]
        # `unblock()` is skipped, unlike every other reader of `waiting_on`. It is a write, and
        # the cost of leaving it out is that a card freed by a dependency closing shows up in
        # the bar one real command late — which the very next taskops call fixes anyway.
        counted: dict[str, int] = {}
        for item in waiting_on(store, actor=who):
            counted[item["move"]] = counted.get(item["move"], 0) + 1
        # The CHAPTER, not an objective: an objective belongs to one dev and the bar belongs to
        # the screen. With several active it says the oldest and counts the rest — the row has one
        # slot and the one a session is most likely to be closing is the one it opened first.
        open_now = chapters(store).active
        said = open_now[0]["text"] if open_now else ""
        if len(open_now) > 1:
            said += f" +{len(open_now) - 1}"
        return Bar(milestone=said,
                   board=store.root.name, local=shared is None,
                   holding=_holding(store, who), waiting=counted,
                   # `mark=False`: delivery is a fact about an AGENT having read something,
                   # and a bar counting a message must never be what asserts it was read.
                   mail=len(inbox_for(store, who, mark=False)["messages"]))


def _holding(store: Store, who: str) -> list[Holding]:
    """The cards this actor has a LIVE lease on — what they are working on this minute.

    Live and not `assigned`: a card assigned to an agent that is not running is a fact about
    the board, which is what `waiting` counts. The bar's first segment answers a narrower
    question — what is under this person's hands right now — and a dead assignment is not it.
    """
    found = []
    for lease in store.leases.of_actor(who, now()):
        task = store.tasks.get(lease["task"])
        if task is not None:
            found.append(Holding(id=task["id"], title=task["title"], status=task["status"]))
    return found
