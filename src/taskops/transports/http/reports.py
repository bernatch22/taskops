"""The three report endpoints: the index, one report's markdown, and narrating one.

Their own module rather than three more functions in `api.py`, because they are the only
endpoints that touch a FILE — a report is written to disk and committed, unlike every other
projection here, which is regenerated on demand. Grouping them keeps that difference visible.

`POST /api/report/digest` is the one endpoint in taskops that costs money and takes half a
minute: it shells out to `claude`. It is a POST for exactly that reason — a write is refused
under `--readonly` by the policy, by method, so a board on a screen in a room cannot spend an
API key by being looked at.
"""

from __future__ import annotations

from pathlib import Path

from ...usecases import Selector, digest, read_report, report_index
from ._wire import Reply, Request, json_reply
from .api import guarded

__all__ = ["get_report", "get_reports", "post_digest"]


def get_reports(root: Path, request: Request) -> Reply:
    """Every report on disk, newest first. Rows only — no bodies.

    Thirty days of dossiers is a megabyte of markdown, and the list on the left of the screen
    shows a label and two badges. The body arrives when a row is clicked.
    """
    return guarded(lambda: json_reply(report_index(root)))


def get_report(root: Path, request: Request) -> Reply:
    """A day's written dossier, and whether the day outran it.

    `?date=` is optional and defaults to today, like the CLI — the endpoint answers for a day
    that was never written up as readily as for one that was, so a UI can show the report and
    the "not written yet" state through one call instead of probing for a 404.
    """
    return guarded(lambda: json_reply(read_report(root, request.param("date"))))


def post_digest(root: Path, request: Request) -> Reply:
    """Write the report if it is missing, then have Claude narrate it. Answers with the file.

    Answering with the whole `ReportFile` and not with a path is what lets the UI render the
    narration it just paid for without a second round trip — and it is the same shape
    `GET /api/report` returns, so the view has one way to read a report.

    `force` is the Regenerate button. Without it an existing narration is refused (409): a
    person may have edited that prose, and it is the one section nothing can recover.
    """
    payload = request.payload()
    label = str(payload.get("date") or payload.get("label") or "")
    force = bool(payload.get("force"))

    def run() -> Reply:
        # A day, named explicitly: the button lives on a day's row, and a window selector is
        # something the UI has no way to express yet.
        digest(root, Selector(date=label), force=force)
        return json_reply(read_report(root, label))

    return guarded(run)
