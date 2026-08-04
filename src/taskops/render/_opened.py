"""The `## Abierto` section — what this window PLANNED, and what it is waiting on.

The section that did not exist. A window whose whole content was four specs and a dependency
chain printed `0 closed · 0 in flight · 0 blocked` and three empty headings, because nothing
rendered `backlog` or `ready`. Everything below is about making that window legible.

The DAG is the point, not decoration. On a planning day the only questions worth answering are
"which of these can somebody start right now" and "what is waiting on what", and a list of
titles answers neither. So every card says either that it is ready, or exactly what it waits
for — and, in the written rendering, what was ASKED, quoted whole.
"""

from __future__ import annotations

from ..contracts import OpenedCard, PeriodReport, Task
from ._text import STATUS_MARK, bullet, truncate
from ._verbatim import Detail, spec_block

__all__ = ["opened_section", "moving_section"]

READY = "listo para empezar"
"""What an empty `waiting_on` is printed as. Saying it OUT LOUD rather than leaving the line
off: a card with no dependency line and a card whose dependencies nobody computed look
identical, and "what can I pick up" is the question this section exists to answer."""


def opened_section(day: PeriodReport, detail: Detail = "brief") -> list[str]:
    """Cards created in this window, with their edges. Absent when the window created none."""
    if not day["opened"]:
        return []
    blocks = ["\n".join(_card(card, detail)) for card in day["opened"]]
    return [f"## Abierto ({len(blocks)})", "", "\n\n".join(blocks), ""]


def _card(card: OpenedCard, detail: Detail) -> list[str]:
    task = card["task"]
    waits = f"  espera a: {', '.join(card['waiting_on'])}" if card["waiting_on"] else f"  {READY}"
    lines = [f"{STATUS_MARK[task['status']]} **{task['id']}** — {truncate(task['title'], 70)}",
             f"  {task['status']} · priority {task['priority']}{_tags(task)}", waits]
    if card["blocking"]:
        lines.append(f"  bloquea a: {', '.join(card['blocking'])}")
    return lines + spec_block(task, detail)


def _tags(task: Task) -> str:
    """Labels and files, when there are any. The files are what an agent picking the card up
    collides on, so they belong beside it rather than one `ask` away."""
    parts = [", ".join(task["labels"]), ", ".join(task["files"])]
    return "".join(f" · {part}" for part in parts if part)


def moving_section(day: PeriodReport) -> list[str]:
    """Every card the window HAD open and did not create, marked by its status today.

    One section and not three, ordered blocked -> working -> unstarted: they are all "open,
    not new", the glyph already says which, and the order puts the row that needs a human at
    the top. `waiting` is the half that used to be dropped on the floor.

    "Had open" and not "is open": which of the three lists a card is in comes from the status it
    held when the window CLOSED, so a card claimed on Tuesday and finished on Thursday stays in
    Tuesday's dossier instead of vanishing from it. The glyph is still today's status — the same
    convention `## Abierto` uses — so a `✓` here reads "was in flight that day, since finished".
    """
    rows = day["blocked"] + day["in_flight"] + day["waiting"]
    if not rows:
        return []
    return ["## Sigue abierto", "",
            bullet([f"{STATUS_MARK[t['status']]} {t['id']} — {truncate(t['title'], 70)}"
                    for t in rows]), ""]
