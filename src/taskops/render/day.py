"""The daily dossier as markdown: what closed, what is still moving, what was said.

Ordered by what a person reads first at the end of a day — the finished work, then the work
that is not finished, then the conversation, then who did it. A reader who stops after the
first section has still got the answer to "what shipped today", which is the question.

Pure like every renderer here: this is reproducible from a literal dict, with no database and
no git in sight.
"""

from __future__ import annotations

from ..contracts import DayReport, Task
from ._dossier import card_block
from ._text import STATUS_MARK, bullet, table, truncate

__all__ = ["render_day"]


def render_day(day: DayReport) -> str:
    """The whole day. An empty day says so in one line rather than printing four empty
    headings — a report made of section titles reads as broken, not as quiet.

    Emptiness is judged on `actors`, which is rolled up from EVERY event in the window: a day
    whose only events were cards being created is a day something happened on, and testing
    the sections instead would have called it silent.
    """
    if not day["actors"]:
        return f"# {day['date']}\n\nNothing happened on this day."
    parts = [f"# {day['date']} — {len(day['closed'])} closed · "
             f"{len(day['in_flight'])} in flight · {len(day['blocked'])} blocked · "
             f"{day['commits_total']} commit(s) · {len(day['actors'])} actor(s)", ""]
    return "\n".join(parts + _closed(day) + _moving(day) + _talk(day) + _actors(day))


def _closed(day: DayReport) -> list[str]:
    if not day["closed"]:
        return ["## Cerrado", "", "Nothing closed on this day.", ""]
    blocks = ["\n".join(card_block(card, day["conversations"])) for card in day["closed"]]
    return [f"## Cerrado ({len(day['closed'])})", "", "\n\n".join(blocks), ""]


def _moving(day: DayReport) -> list[str]:
    """In flight and blocked in ONE section, marked by status.

    Two headings would imply they are different kinds of answer, and they are not: both are
    "started, not finished", and the glyph already says which.
    """
    rows = day["in_flight"] + day["blocked"]
    if not rows:
        return []
    return ["## En vuelo / bloqueado", "", bullet([_row(task) for task in rows]), ""]


def _row(task: Task) -> str:
    return f"{STATUS_MARK[task['status']]} {task['id']} — {truncate(task['title'], 70)}"


def _talk(day: DayReport) -> list[str]:
    """Every comment and message of the day, in the log's own order — a conversation read
    top-down. Truncated per line so one essay cannot push the rest of the day off screen."""
    if not day["conversations"]:
        return []
    lines = [f"**{e['actor']}** on {e['task']}: {truncate(str(e['body'].get('text', '')), 160)}"
             for e in day["conversations"]]
    return [f"## Conversaciones ({len(lines)})", "", "\n\n".join(lines), ""]


def _actors(day: DayReport) -> list[str]:
    if not day["actors"]:
        return []
    rows = [[roll["actor"], str(roll["tasks"]), str(roll["commits"]),
             str(roll["comments"]), str(roll["done"])] for roll in day["actors"]]
    return ["## Por actor", "",
            table(["actor", "tasks", "commits", "comments", "closed"], rows)]
