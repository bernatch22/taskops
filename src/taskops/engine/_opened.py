"""The cards a window OPENED — planned work, with the edges that say what can start.

Split from `day` for the same reason `_closed` is: assembling a card needs the graph, and the
module that describes a window should not also know how the `deps` table is read from both
ends.

This exists because a freshly planned project reported nothing at all. `in_flight` covers
`claimed`/`in_progress`/`review` and `blocked` covers `blocked`, so `backlog` and `ready` —
which is ALL planned-but-unstarted work — belonged to no section, and a day spent writing four
specs rendered as `0 closed · 0 in flight · 0 blocked` over three empty headings. The same
class of bug as a finished project answering `tasks list` with silence: a filter that describes
some states, and everything else falling through it.
"""

from __future__ import annotations

from collections.abc import Collection

from ..contracts import Event, OpenedCard, Task
from ..storage import Store

__all__ = ["opened_cards", "still_open"]


def opened_cards(store: Store, events: list[Event]) -> list[OpenedCard]:
    """One card per `created` event in the window, oldest first.

    Created AND closed INSIDE the window is dropped: `closed` already tells that card's whole
    story with its commits and its conversation, and listing it here too would invite a reader
    to count it twice. A card this clone does not have is dropped as well, like everywhere else
    — an event can name a task that still lives in a teammate's log.

    **Closed LATER is not closed here.** This filtered on the card's status AS OF NOW, so a
    card planned on Tuesday and finished on Thursday vanished from Tuesday's dossier — it was
    no longer open, and Tuesday's `closed` never held it either, because it closed on Thursday.
    Regenerating an OLD day therefore reported less than the same day generated at the time, and
    the loss was silent and permanent: 2026-07-30 on the axion board went from `5 opened` to
    `3` to `2` on three successive regenerations as its cards closed, one line of the day's
    planning disappearing per close. A window is a claim about the past, so the only status this
    may read is what the window itself did — which is the set of `done` events inside it, the
    same set `closed_cards` renders from.

    The card is still printed with its status TODAY, and that is deliberate: a `✓ done` under
    `## Abierto` says "planned that day, since finished", which is a fact the reader wants, and
    the section it sits in already says what the window did. Two facts side by side, not one
    guess — so this holds for every section, and `_asof` is used for MEMBERSHIP only.

    (The original reason given here was that an as-of status could not be rebuilt at all,
    because `scheduler.unblock` moved cards between `backlog` and `ready` without recording an
    event. It records now, so that half is no longer true and the convention stands on the
    argument above instead. `_asof` documents what is still unrecoverable.)
    """
    closed_here = {event["task"] for event in events if event["kind"] == "done"}
    out: list[OpenedCard] = []
    for event in events:
        task = store.tasks.get(event["task"]) if event["kind"] == "created" else None
        if task is not None and task["id"] not in closed_here:
            out.append(OpenedCard(task=task,
                                  waiting_on=store.deps.open_blockers_of(task["id"]),
                                  blocking=store.deps.dependents_of(task["id"])))
    return out


def still_open(touched: list[Task], opened: list[OpenedCard], held: dict[str, str],
               statuses: Collection[str]) -> list[Task]:
    """Cards the window HELD in one of `statuses` and did not create. The three moving sections.

    ONE function for `in_flight`, `blocked` and `waiting` because the rule that decides all three
    is one rule, and it was only obeyed by one of them. The exclusion of the window's own new
    cards lived here (as `waiting_tasks`) while `in_flight` and `blocked` filtered `touched`
    directly — so a card planned AND claimed on the same day was printed under `## Abierto` and
    again under `## Sigue abierto`, reading as two cards to anybody scanning. `render/day` states
    "EVERY open card lands in exactly one section" as an invariant; this is what makes it true.

    `held` is what each card's status WAS when the window closed (`_asof.statuses_at`), and it is
    a required argument rather than a default: the whole defect this fixes is a projection that
    read the present, and a parameter that quietly falls back to it is the same bug with a longer
    signature. Note that both UNSTARTED statuses land in one section, which is why the era of
    unrecorded `unblock` moves cannot put a card in the WRONG section — only under the wrong
    glyph. See `_asof` for that boundary in full.
    """
    new = {card["task"]["id"] for card in opened}
    return [t for t in touched if held.get(t["id"]) in statuses and t["id"] not in new]
