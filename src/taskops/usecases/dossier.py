"""`report … --write` — the dossier persisted where git can keep it.

The only use case here that writes a FILE rather than an event, and deliberately so. Every
other projection is regenerated on demand because regenerating is always right; this one
stops being derived the moment a human or `/taskops:digest` writes the narration into it, so
it is written once, refused a second time, and committed like source.

The window is a `Selector`, not a date: a day, a week and the whole project are the same
document over different spans, and the file is named by the window's LABEL — `2026-07-28.md`,
`2026-07-22..2026-07-28.md`, `all.md`.

Which is also why it goes through `render`: the file's shape is a rendering, and the same
string has to be producible in a test from a literal dict.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from .._errors import AlreadyWritten
from ..contracts import ReportFile
from ..engine import (
    OnPass,
    OnText,
    label_of,
    missing_events,
    narrate,
    period_report,
    stamp,
    stamped_seq,
)
from ..render import is_pending, narrated, render_day, render_report
from ..storage import REPORTS_DIR, Store
from ._project import project
from ._range import Selector, resolve

__all__ = ["write_report", "read_report", "digest", "report_path"]


def write_report(start: Path | str, sel: Selector | None = None, *,
                 force: bool = False) -> Path:
    """Render the window and write `.taskops/reports/<label>.md`. Returns where it landed.

    Refuses an existing file unless `force`, because the file may already carry a narration
    nobody can regenerate — and the report someone linked to yesterday changing under them is
    exactly the thing that makes a written record worthless.
    """
    with project(start) as store:
        span = resolve(store, sel or Selector())
        path = report_path(store.root, _label(span))
        if path.exists() and not force:
            raise AlreadyWritten(f"{path} already exists — read it, or pass --force to "
                                 f"regenerate it (any narration in it is lost)")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_generate(store, span), encoding="utf-8")
        return path


def read_report(start: Path | str, date_text: str = "") -> ReportFile:
    """What is on disk for a DAY, and whether the day has moved on since.

    One day and not a window: this is what the studio polls for staleness, and staleness of a
    range is a different question — `all.md` is out of date the moment anything happens.

    A day with no file still answers with a dossier — the one that would be written — so a
    reader never gets an empty screen and a "generate it" button as the only content.
    """
    with project(start) as store:
        span = resolve(store, Selector(date=date_text))
        date = span[0]
        path = report_path(store.root, date)
        written = path.read_text(encoding="utf-8") if path.is_file() else ""
        behind = missing_events(store, date, date, stamped_seq(written))
        return ReportFile(date=date, path=str(path),
                          dossier_md=written or _generate(store, span),
                          exists=bool(written), stale=behind > 0, missing_events=behind)


def digest(start: Path | str, sel: Selector | None = None, *, model: str = "",
           force: bool = False, on_pass: OnPass = None, on_text: OnText = None) -> Path:
    """Write the window's report if it is missing, then have Claude narrate it.

    The two callbacks are how a caller SEES it happen — which pass is running, and the prose as
    it is written. Optional, and nothing here prints: a use case that wrote to stdout would be
    unusable from the HTTP transport, which calls this same function.

    Two failures are kept apart on purpose. The dossier is written FIRST and committed to disk
    before the model is called, so a narration that fails — no `claude`, not logged in, a
    timeout — costs the prose and never the facts. Running it again then narrates the file that
    is already there rather than starting over.

    An existing narration is refused without `force` for the same reason a written report is:
    somebody may have written it by hand, and this is the one section a machine cannot recover.

    `force` regenerates the DOSSIER too, not only the prose. Narrating the file as it lies is
    what the first version did, and it produced the worst possible failure: a fresh narration of
    a stale document. A report written before a card was closed — or before the renderer learned
    to show open cards at all — reads to the model as a day on which nothing happened, and the
    prose says so, accurately and uselessly. Anybody passing `--force` is asking for this report
    to be redone; redoing half of it is the answer nobody wants.
    """
    with project(start) as store:
        span = resolve(store, sel or Selector())
        path = report_path(store.root, _label(span))
        if force or not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_generate(store, span), encoding="utf-8")
        report = path.read_text(encoding="utf-8")
        if not is_pending(report) and not force:
            raise AlreadyWritten(f"{path} already carries a narration — read it, or pass "
                                 f"--force to replace it (the old one is lost)")
        prose = narrate(report, model=model, on_pass=on_pass, on_text=on_text)
        path.write_text(narrated(report, prose), encoding="utf-8")
        return path


def report_path(root: Path, label: str) -> Path:
    return root / REPORTS_DIR / f"{label}.md"


def _label(span: tuple[str, str, str]) -> str:
    """The window's name, asked of the renderer's own source of truth rather than rebuilt
    here — a path and a heading that disagree is the bug this indirection exists to stop."""
    return span[2] or label_of(span[0], span[1])


def _generate(store: Store, span: tuple[str, str, str]) -> str:
    """The file's whole text, stamped with the log's max_seq AT THIS MOMENT.

    Read after the dossier would be a race with itself — an event landing mid-render would be
    in the report and outside its own fingerprint, and the file would claim to be older than
    it is. Read first, and the worst case is a report that reports itself stale.

    The rendering is `full`: the spec of every card, every comment whole, every file of every
    commit. The terminal keeps the short form — this is the copy somebody reads INSTEAD of the
    git log a month later, and a truncation it cannot expand is a fact permanently lost.
    """
    return render_report(stamp(_label(span), store.events.max_seq(), now()),
                         render_day(period_report(store, *span), detail="full"))
