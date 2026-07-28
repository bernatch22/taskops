"""The dossier as markdown: what closed, what was planned, what is still moving, what was said.

Ordered by what a person reads first at the end of a day — the finished work, then the work
that was planned, then the work that is neither, then the conversation, then who did it. A
reader who stops after the first section has still got the answer to "what shipped", which is
usually the question — and on a day that shipped nothing, `## Abierto` is right underneath.

EVERY open card lands in exactly one section. `in_flight` and `blocked` used to be the only
ones drawn, so `ready` and `backlog` — all planned-but-unstarted work — were rendered nowhere
and a freshly planned project reported that nothing had happened at all.

ONE function for a day and for a month. A wider window changes exactly two things — the title
is a label rather than a date, and the closed cards get a heading per day — and nothing else,
so a range report is the report somebody already knows how to read.

Pure like every renderer here: this is reproducible from a literal dict, with no database and
no git in sight.
"""

from __future__ import annotations

from ..contracts import Event, PeriodReport
from ._closed_days import closed_section
from ._opened import moving_section, opened_section
from ._text import table, truncate
from ._verbatim import Detail

__all__ = ["render_day"]

TALK_LINE = 160
"""Characters of a comment the TERMINAL prints. `full` prints all of it — the conversation is
where the reasoning is, and 160 characters of it is a hint that something was said."""


def render_day(day: PeriodReport, detail: Detail = "brief") -> str:
    """The whole window. A window with nothing in any section says so in one line rather than
    printing empty headings — a report made of section titles reads as broken, not as quiet.

    Emptiness is judged on the SECTIONS, not on `actors`. It was judged on actors, and that is
    precisely how the silent-planning-day bug hid: four cards created means one actor with four
    tasks, so the report was not "empty", it just had no section that could hold a `ready` card
    and printed three headings with nothing under them. A report that draws nothing must say
    nothing happened; a report that has something to draw must draw it.
    """
    body = (closed_section(day, detail) + opened_section(day, detail) + moving_section(day)
            + _talk(day, detail))
    if not _anything(day):
        quiet = ("on this day" if day["from_date"] == day["to_date"]
                 else "in this window")
        return f"# {day['label']}\n\nNothing happened {quiet}."
    return "\n".join([_headline(day), ""] + body + _actors(day))


def _anything(day: PeriodReport) -> bool:
    """Whether the window holds a single fact worth a heading.

    `dropped` counts: a window that closed more cards than the cap renders has plenty to say,
    and answering it with "nothing happened" would be the loudest possible lie.
    """
    return bool(day["closed"] or day["opened"] or day["in_flight"] or day["blocked"]
                or day["waiting"] or day["conversations"] or day["commits_total"]
                or day["dropped"])


def _headline(day: PeriodReport) -> str:
    """The counts, with `opened` and `waiting` shown only when they are not zero.

    Conditional and not unconditional: those two numbers exist to stop the summary line
    claiming a planning day was empty, and a window that opened nothing does not need to be
    told so — while every dossier ever committed keeps the header it was written with.
    """
    counts = [f"{len(day['closed'])} closed", f"{len(day['opened'])} opened",
              f"{len(day['in_flight'])} in flight", f"{len(day['blocked'])} blocked",
              f"{len(day['waiting'])} waiting", f"{day['commits_total']} commit(s)",
              f"{len(day['actors'])} actor(s)"]
    drop = {f"0 {name}" for name in ("opened", "waiting")}
    return f"# {day['label']} — " + " · ".join(c for c in counts if c not in drop)


def _talk(day: PeriodReport, detail: Detail = "brief") -> list[str]:
    """Every comment and message of the day, in the log's own order — a conversation read
    top-down. Truncated per line in the terminal so one essay cannot push the rest of the day
    off screen; whole in the file, where the essay is the point."""
    if not day["conversations"]:
        return []
    lines = [f"**{e['actor']}** on {e['task']}: {_body(e, detail)}"
             for e in day["conversations"]]
    return [f"## Conversaciones ({len(lines)})", "", "\n\n".join(lines), ""]


def _body(event: Event, detail: Detail) -> str:
    text = str(event["body"].get("text", ""))
    return text.strip() if detail == "full" else truncate(text, TALK_LINE)


def _actors(day: PeriodReport) -> list[str]:
    if not day["actors"]:
        return []
    rows = [[roll["actor"], str(roll["tasks"]), str(roll["commits"]),
             str(roll["comments"]), str(roll["done"])] for roll in day["actors"]]
    return ["## Por actor", "",
            table(["actor", "tasks", "commits", "comments", "closed"], rows)]
