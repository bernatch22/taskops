"""The cards that reached `done`, assembled with their commits and their sizes.

Split from `day` because it is the expensive half: every closed card needs its whole history
read back, and all of their commits need git. Keeping it here is what lets `day` stay a
description of the window rather than a description of a card.

The batching is the point. One `numstats` call covers every commit of every card closed that
day, so a report of twenty cards is one subprocess — not one per card, which is how a daily
report turns into a spinning terminal on a busy project.
"""

from __future__ import annotations

from typing import cast

from ..contracts import ClosedCard, CommitStat, Event, Task
from ..storage import Store
from .diffstat import numstats

__all__ = ["closed_cards"]


def closed_cards(store: Store, dones: list[Event]) -> list[ClosedCard]:
    """One card per `done` event, oldest close first. Cards this clone does not have are
    dropped — an event can name a task that is still in a teammate's log."""
    histories = {done["task"]: store.events.of_task(done["task"]) for done in dones}
    stats = numstats(store.root, [str(event["body"].get("sha", ""))
                                  for history in histories.values() for event in history
                                  if event["kind"] == "commit"])
    out: list[ClosedCard] = []
    for done in dones:
        task = store.tasks.get(done["task"])
        if task is not None:
            out.append(_card(task, done, histories[done["task"]], stats))
    return out


def _card(task: Task, done: Event, history: list[Event],
          stats: dict[str, tuple[int, int]]) -> ClosedCard:
    """`claimed_ts` is the LAST claim before the close, not the first.

    A card released once and picked up again by somebody else was not being worked on in
    between, and measuring from the first claim would report a two-hour task as two days.
    """
    claims = [e["ts"] for e in history
              if e["kind"] == "claimed" and e["ts"] <= done["ts"]]
    return ClosedCard(task=task, actor=done["actor"], done_ts=done["ts"],
                      claimed_ts=max(claims) if claims else done["ts"],
                      commits=[_stat(e, stats) for e in history if e["kind"] == "commit"])


def _stat(event: Event, stats: dict[str, tuple[int, int]]) -> CommitStat:
    """A `commit` event plus what git says it weighed.

    Coerced field by field, like `usecases.view._commit`: the body is an open dict written by
    whatever taskops version ingested it, and a newer one may not have said `files` at all.
    """
    body = event["body"]
    raw: object = body.get("files")
    files = cast("list[object]", raw) if isinstance(raw, list) else []
    sha = str(body.get("sha", ""))
    adds, dels = stats.get(sha, (0, 0))
    return CommitStat(sha=sha, subject=str(body.get("subject", "")),
                      files=[str(path) for path in files], actor=event["actor"],
                      ts=event["ts"], additions=adds, deletions=dels)
