"""What has been written up — the listing behind the Reports view.

The one read here that does NOT go through `day_report`: this answers "which reports exist",
which is a question about the directory, not about the log. It reads each file only far enough
to answer whether it is stale and whether anybody narrated it, and never returns a body.

Today is listed even when its file is missing, because the screen's main verb is generating it
and a list that shows nothing on a fresh repository would offer nothing to press.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from ..contracts import ReportEntry
from ..engine import date_of, missing_events, stamped_seq
from ..render import is_pending
from ..storage import REPORTS_DIR, Store
from ._project import project
from .dossier import report_path

__all__ = ["report_index"]


def report_index(start: Path | str) -> list[ReportEntry]:
    """Every report on disk, newest first, with today at the top whether or not it exists."""
    with project(start) as store:
        today = date_of(now())
        directory = store.root / REPORTS_DIR
        found = sorted(directory.glob("*.md"), key=lambda path: path.stem, reverse=True) \
            if directory.is_dir() else []
        entries = [_entry(store, path) for path in found]
        if not any(entry["label"] == today for entry in entries):
            entries.insert(0, ReportEntry(label=today, path=str(report_path(store.root, today)),
                                          exists=False, stale=False, missing_events=0,
                                          has_narration=False, bytes=0))
        return entries


def _entry(store: Store, path: Path) -> ReportEntry:
    text = path.read_text(encoding="utf-8", errors="replace")
    behind = _behind(store, path.stem, text)
    return ReportEntry(label=path.stem, path=str(path), exists=True, stale=behind > 0,
                       missing_events=behind, has_narration=not is_pending(text),
                       bytes=len(text.encode("utf-8")))


def _behind(store: Store, label: str, text: str) -> int:
    """Staleness is only meaningful for a SINGLE day.

    `missing_events` counts inside one calendar window, so a report named for a range — or for
    `all` — has no window to count against. The label is opaque by contract: anything that
    assumed it parses as a date would raise the first time somebody writes a weekly report.
    """
    if not _is_day(label):
        return 0
    return missing_events(store, label, stamped_seq(text))


def _is_day(label: str) -> bool:
    return (len(label) == 10 and label[4] == "-" and label[7] == "-"
            and label.replace("-", "").isdigit())
