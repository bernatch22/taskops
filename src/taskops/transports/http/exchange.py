"""The four replication endpoints — the wire half of remote sync.

Its own module because these are the only endpoints whose caller is another taskops rather
than the board: the shapes here are a CONTRACT a client codes against (`docs/exchange.md`),
not something the UI and the server can rename together in one commit.

Every write is a POST or a PUT, so `--readonly` refuses all four writes by METHOD in `policy`
before any of this runs. A mirror on a screen cannot be pushed into.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ..._errors import ReportConflict
from ...usecases import MAX_PAGE, accept_events, pull_events, read_report_file, write_report_file
from ...usecases.index import report_index
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["post_sync", "get_sync", "get_report_file", "put_report_file"]


def post_sync(root: Path, request: Request) -> Reply:
    """Relay a batch. `{"accepted": <how many were new>, "max_seq": <this server's cursor>}`."""
    raw: object = request.payload().get("events")
    if not isinstance(raw, list):
        return error_reply(400, "`events` must be a list of events", "bad_request")
    batch = cast("list[Any]", raw)
    return guarded(lambda: json_reply(accept_events(root, batch)))


def get_sync(root: Path, request: Request) -> Reply:
    """One page after `?after=`, which is a cursor in THIS server's sequence and no other's."""
    after = _int(request.param("after"), 0)
    limit = _int(request.param("limit"), MAX_PAGE)
    return guarded(lambda: json_reply(pull_events(root, after=after, limit=limit)))


def _listing(rows: list[Any]) -> dict[str, Any]:
    """Labels and their stamps, from ONE index read. Both halves because the labels alone are what
    the older client asks for and the stamps are what makes a sync cheap."""
    held = [row for row in rows if row["exists"]]
    return {"labels": [row["label"] for row in held],
            "stamps": {row["label"]: row["max_seq"] for row in held}}


def get_report_file(root: Path, request: Request) -> Reply:
    """The bytes this server holds for a label, verbatim — it never regenerates one to answer.

    With NO label it answers the LISTING instead, and that half is what a sync needs: every label
    with the seq it was generated at, and no bodies. The client's `list_reports` had been calling it
    that way since before the shape existed, tolerating the 400 — so reconciling fell back to
    downloading every report in full to read one number out of each. Eight round-trips on a pull
    with nothing to bring, eleven seconds measured, and every write pays a pull.
    """
    label = request.param("label")
    if not label:
        return guarded(lambda: json_reply(_listing(report_index(root))))

    def run() -> Reply:
        found = read_report_file(root, label)
        if found is None:
            return error_reply(404, f"no report {label} on this server", "no_such_report")
        return json_reply(found)

    return guarded(run)


def put_report_file(root: Path, request: Request) -> Reply:
    """Push a report. 409 unless it is strictly newer than what is here — see `usecases.reportfile`.

    The conflict is answered by hand rather than through `guarded`, because `ours` and `theirs`
    have to reach the client as NUMBERS. Its whole next move is deciding which copy survives,
    and a sentence it would have to parse to find out is not an answer.
    """
    payload = request.payload()
    label, content = str(payload.get("label", "")), str(payload.get("content", ""))
    if not label or not content:
        return error_reply(400, "`label` and `content` are required", "bad_request")
    force = bool(payload.get("force"))

    def run() -> Reply:
        try:
            return json_reply(write_report_file(root, label, content, force=force))
        except ReportConflict as clash:
            return json_reply({"error": str(clash), "code": clash.code,
                               "ours": clash.ours, "theirs": clash.theirs}, 409)

    return guarded(run)


def _int(text: str, fallback: int) -> int:
    """A query number, or the default. A cursor somebody typed by hand must not be a 500."""
    return int(text) if text.lstrip("-").isdigit() else fallback
