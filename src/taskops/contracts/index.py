"""The INDEX of what has been written up — one row per file in `.taskops/reports/`.

Deliberately not `ReportFile`: that carries the whole markdown, and a listing of thirty days
that shipped thirty dossiers would be a megabyte of text nobody on the screen is reading. This
is the row you click, and the body arrives on `GET /api/report` when you do.

`label` is the file's STEM and is treated as an opaque string everywhere. Today it is a date;
a report over a range is named for the range (`2026-07-22..2026-07-28`, `all`), and anything
that parsed the label as a day would break on the first one of those.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["ReportEntry"]


class ReportEntry(TypedDict):
    label: str
    """The file's stem — a date, or a range. Opaque: what you pass back to read or narrate it."""

    path: str
    exists: bool
    """False for the one row that is not a file: today, when nobody has written it up yet. It
    is listed anyway, because 'generate today's report' is the reason this screen exists."""

    stale: bool
    missing_events: int
    """How many of the day's events landed after the report was generated. Always 0 for a label
    that is not a single day — a range has no window this can be counted against."""

    max_seq: int
    """The seq this report was generated at, parsed out of its own stamp. Here so a SYNC can decide
    whether it needs the body: without it, reconciling meant downloading every report in full to
    read one number out of it — eight round-trips on a pull that had nothing to bring, measured at
    eleven seconds on a real board."""

    has_narration: bool
    """Whether the prose section has been written. The dossier's facts are free to regenerate;
    the narration is the part a model was paid for and a human may have edited."""

    bytes: int
