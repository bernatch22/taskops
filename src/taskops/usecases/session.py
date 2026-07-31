"""A session opening and closing — and how a message reaches another agent.

Claude Code cannot be pushed to mid-turn: a session only ever "listens" when a hook
fires. That is the constraint the whole delivery design follows from, and it is worth
stating plainly rather than pretending otherwise.

```
SessionStart  -> brief()     the agent starts knowing its tasks and its messages
PostToolUse   -> inbox()     anything that arrived since lands in its next tool call
Stop          -> checkout()  its work becomes a comment on the task, unprompted
```

So "real time" here means: within one tool call of the sender writing it, which for a
working agent is seconds. The human-facing real time is the studio, which sees the
event the moment it is committed.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from .._clock import now
from ..contracts import Event, Inbox, Lease
from ..engine import record
from ..storage import Store
from ._project import caller, heartbeat, project
from ._routing import read_remote_first
from .chat import CHAT_TASK
from .view import inbox_for

__all__ = ["brief", "inbox", "checkout", "track", "Brief"]


class Brief:
    """What a session needs to know before its first prompt."""

    def __init__(self, *, actor: str, session: str, held: list[Lease],
                 messages: list[Event], ready: int) -> None:
        self.actor = actor
        self.session = session
        self.held = held
        self.messages = messages
        self.ready = ready


def brief(start: Path | str, *, session: str = "", actor: str = "") -> Brief:
    """The SessionStart read: who am I, what do I hold, who spoke to me.

    Leases held by this SESSION are re-associated on resume: Claude Code re-runs
    SessionStart with `source=resume`, and without this an agent that resumed would
    look like a new actor holding nothing while its claims sat there.
    """
    with project(start) as store:
        who = caller(store, actor)["id"]
        # The ONE call that carries a session id, and therefore the only one that can say this
        # dev is here rather than passing through. Everything downstream — routing, the team
        # brief — reads that distinction.
        heartbeat(store, who, session=session)
        held = store.leases.of_actor(who, now())
        if session:
            _adopt(store, held, session)
        return Brief(actor=who, session=session, held=held,
                     messages=inbox_for(store, who)["messages"],
                     ready=len(store.tasks.with_status(("ready",))))


def _adopt(store: Store, held: list[Lease], session: str) -> None:
    """Point this actor's leases at the session that is now running them.

    A resumed session gets a NEW id, so the lease's old one names a process that is gone
    — and the live board would show a claim whose transcript nobody can open.
    """
    for lease in held:
        if lease["session"] != session:
            store.leases.set_session(task_id=lease["task"], session=session)


def inbox(start: Path | str, *, actor: str = "") -> Inbox:
    """The PostToolUse read: messages this actor has not seen, marked delivered.

    Cheap on purpose — one indexed query and usually zero rows. It runs after every
    tool call an agent makes, so anything expensive here is a tax on all of its work.

    ROUTED, like every other read, and it was the last one that was not — which made
    agent-to-agent messaging silently local-only: a mention written by one developer landed in
    the server's log, and the developer it named read their own clone and found nothing. It is
    also a WRITE disguised as a read (delivery is marked), so the local fallback would hand the
    same message out twice on two machines.
    """
    if (answer := read_remote_first(start, "inbox", {"actor": actor})) is not None:
        return cast("Inbox", answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        return inbox_for(store, who)


def track(start: Path | str, *, summary: str, task: str = "", actor: str = "",
          session: str = "") -> Event | None:
    """The heartbeat with content: what tool touched what file, for the live board.

    It also STAMPS the session id onto the actor's leases, and that half is what makes a conversation
    findable. A dispatched worker is easy — it runs in a per-card worktree, so its transcript has a
    directory of its own. A card worked on interactively has neither, and every `claimed` event in a
    real project turned out to carry an empty `session`, because nothing was passing one: the tool
    accepts it and no caller supplied it. This hook receives it on every tool call, so stamping it
    here costs nothing and closes the gap.

    Local-only (`LOCAL_ONLY_KINDS`), so it never reaches the committed log.

    Without a card it is filed under the SENTINEL, not dropped. It used to be dropped, and the
    reasoning was sound until the board grew a chat: an ORCHESTRATOR holds no card — it plans,
    delegates and answers — so every one of its tool calls was discarded, and the sidebar's
    activity strip was empty for exactly the actor somebody opened the sidebar to watch. The
    original worry stands and the sentinel answers it better than the drop did: the event is
    attributable (to its actor), it is local-only so it never reaches anybody's diff, and the
    row it costs is in the cache taskops rebuilds from scratch on demand.
    """
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        held = store.leases.of_actor(who, now())
        if session:
            _stamp(store, held, session)
        target = task or (held[0]["task"] if len(held) == 1 else "") or CHAT_TASK
        return record(store, task=target, actor=who, kind="activity",
                      body={"summary": summary, "session": session})


def _stamp(store: Store, held: list[Lease], session: str) -> None:
    """Record which session is working each held card. Cheap, idempotent, and only writes on change."""
    for lease in held:
        if lease["session"] != session:
            store.leases.set_session(task_id=lease["task"], session=session)


def checkout(start: Path | str, *, summary: str, session: str = "",
             actor: str = "") -> list[Event]:
    """The Stop read: the session's own account of itself, on every task it holds.

    An auto-standup, and the reason a task's thread is worth reading at 9am: an agent
    that was killed mid-thought still leaves what it had. Leases are deliberately NOT
    released — a session ending is not the same as work being handed back, and Claude
    Code ends a session every time a developer closes a terminal.
    """
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        return [record(store, task=lease["task"], actor=who, kind="comment",
                       body={"text": summary, "session": session, "auto": True})
                for lease in store.leases.of_actor(who, now())]
