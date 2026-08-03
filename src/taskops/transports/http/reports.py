"""The three report endpoints: the index, one report's markdown, and narrating one.

Their own module rather than three more functions in `api.py`, because they are the only
endpoints that touch a FILE — a report is written to disk and committed, unlike every other
projection here, which is regenerated on demand. Grouping them keeps that difference visible.

`POST /api/report/digest` is the one endpoint in taskops that costs money and takes MINUTES:
it shells out to `claude`. It is a POST for exactly that reason — a write is refused under
`--readonly` by the policy, by method, so a board on a screen in a room cannot spend an API key
by being looked at.

It does not WAIT for it, though. It starts the narration and answers immediately; the prose
arrives on `/api/live` as it is written. Holding the response open for a multi-minute model
call was the whole bug: the browser showed a mute spinner, the file said `_pendiente_`
throughout, and a connection that dropped took the only feedback there was with it.
"""

from __future__ import annotations

from pathlib import Path

from ...usecases import narration, parse_date, read_report, report_index
from ._wire import Reply, Request, error_reply, json_reply
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
    """START narrating the report. Answers `{"status": "narrating", "label"}` at once.

    Not the finished file, deliberately. The narration is minutes of a model writing, and the
    only honest thing a request can return in that time is "it began" — the prose itself
    arrives on `/api/live`, frame by frame, on the socket the board already holds. The UI shows
    it appearing and refetches the file when the terminal frame lands.

    The day is parsed HERE, before the thread starts, so a label nobody can read is still a 400
    with the parser's own sentence in it rather than a `narration.failed` frame two seconds
    later on a stream the caller may not even be watching.

    `force` is the Regenerate button; without it an existing narration is refused, since a
    person may have edited that prose. A second request while one is running is refused too
    (409) — two models rewriting one file is corruption, not contention.
    """
    if why := narration.narratable_here():
        return error_reply(503, why, "cannot_narrate")
    payload = request.payload()
    label = str(payload.get("date") or payload.get("label") or "")
    force = bool(payload.get("force"))

    def run() -> Reply:
        # A day, named explicitly: the button lives on a day's row, and a window selector is
        # something the UI has no way to express yet.
        day = parse_date(label)
        return json_reply({"status": "narrating",
                           "label": narration.start(root, day, force=force)})

    return guarded(run)
