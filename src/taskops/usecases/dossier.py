"""`report day --write` — the daily dossier persisted where git can keep it.

The only use case here that writes a FILE rather than an event, and deliberately so. Every
other projection is regenerated on demand because regenerating is always right; this one
stops being derived the moment a human or `/taskops:digest` writes the narration into it, so
it is written once, refused a second time, and committed like source.

Which is also why it goes through `render`: the file's shape is a rendering, and the same
string has to be producible in a test from a literal dict.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from .._errors import AlreadyWritten
from ..contracts import ReportFile
from ..engine import day_report, missing_events, stamp, stamped_seq
from ..render import render_day, render_report
from ..storage import REPORTS_DIR, Store
from ._project import project
from .report import parse_date

__all__ = ["write_report", "read_report", "report_path"]


def write_report(start: Path | str, date_text: str = "", *, force: bool = False) -> Path:
    """Render the day and write `.taskops/reports/YYYY-MM-DD.md`. Returns where it landed.

    Refuses an existing file unless `force`, because the file may already carry a narration
    nobody can regenerate — and the report someone linked to yesterday changing under them is
    exactly the thing that makes a written record worthless.
    """
    with project(start) as store:
        date = parse_date(date_text)
        path = report_path(store.root, date)
        if path.exists() and not force:
            raise AlreadyWritten(f"{path} already exists — read it, or pass --force to "
                                 f"regenerate it (any narration in it is lost)")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_generate(store, date), encoding="utf-8")
        return path


def read_report(start: Path | str, date_text: str = "") -> ReportFile:
    """What is on disk for a day, and whether the day has moved on since.

    A day with no file still answers with a dossier — the one that would be written — so a
    reader never gets an empty screen and a "generate it" button as the only content.
    """
    with project(start) as store:
        date = parse_date(date_text)
        path = report_path(store.root, date)
        written = path.read_text(encoding="utf-8") if path.is_file() else ""
        behind = missing_events(store, date, stamped_seq(written))
        return ReportFile(date=date, path=str(path),
                          dossier_md=written or _generate(store, date),
                          exists=bool(written), stale=behind > 0, missing_events=behind)


def report_path(root: Path, date: str) -> Path:
    return root / REPORTS_DIR / f"{date}.md"


def _generate(store: Store, date: str) -> str:
    """The file's whole text, stamped with the log's max_seq AT THIS MOMENT.

    Read after the dossier would be a race with itself — an event landing mid-render would be
    in the report and outside its own fingerprint, and the file would claim to be older than
    it is. Read first, and the worst case is a report that reports itself stale.
    """
    return render_report(stamp(date, store.events.max_seq(), now()),
                         render_day(day_report(store, date)))
