"""The dossier as markdown: what closed, what is still moving, what was said.

Ordered by what a person reads first at the end of a day — the finished work, then the work
that is not finished, then the conversation, then who did it. A reader who stops after the
first section has still got the answer to "what shipped", which is the question.

ONE function for a day and for a month. A wider window changes exactly two things — the title
is a label rather than a date, and the closed cards get a heading per day — and nothing else,
so a range report is the report somebody already knows how to read.

Pure like every renderer here: this is reproducible from a literal dict, with no database and
no git in sight.
"""

from __future__ import annotations

from ..contracts import PeriodReport, Task
from ._closed_days import closed_section
from ._text import STATUS_MARK, bullet, table, truncate

__all__ = ["render_day"]


def render_day(day: PeriodReport) -> str:
    """The whole day. An empty day says so in one line rather than printing four empty
    headings — a report made of section titles reads as broken, not as quiet.

    Emptiness is judged on `actors`, which is rolled up from EVERY event in the window: a day
    whose only events were cards being created is a day something happened on, and testing
    the sections instead would have called it silent.
    """
    if not day["actors"]:
        quiet = ("on this day" if day["from_date"] == day["to_date"]
                 else "in this window")
        return f"# {day['label']}\n\nNothing happened {quiet}."
    parts = [f"# {day['label']} — {len(day['closed'])} closed · "
             f"{len(day['in_flight'])} in flight · {len(day['blocked'])} blocked · "
             f"{day['commits_total']} commit(s) · {len(day['actors'])} actor(s)", ""]
    return "\n".join(parts + closed_section(day) + _moving(day) + _talk(day) + _actors(day))


def _moving(day: PeriodReport) -> list[str]:
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


def _talk(day: PeriodReport) -> list[str]:
    """Every comment and message of the day, in the log's own order — a conversation read
    top-down. Truncated per line so one essay cannot push the rest of the day off screen."""
    if not day["conversations"]:
        return []
    lines = [f"**{e['actor']}** on {e['task']}: {truncate(str(e['body'].get('text', '')), 160)}"
             for e in day["conversations"]]
    return [f"## Conversaciones ({len(lines)})", "", "\n\n".join(lines), ""]


def _actors(day: PeriodReport) -> list[str]:
    if not day["actors"]:
        return []
    rows = [[roll["actor"], str(roll["tasks"]), str(roll["commits"]),
             str(roll["comments"]), str(roll["done"])] for roll in day["actors"]]
    return ["## Por actor", "",
            table(["actor", "tasks", "commits", "comments", "closed"], rows)]
