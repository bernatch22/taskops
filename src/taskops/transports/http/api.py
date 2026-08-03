"""The JSON endpoints. Each one is a use case call and a serialisation, and nothing else.

The contracts ARE the wire format: they are TypedDicts, so at runtime they are already the dicts
the browser receives, and `studio/src/contracts.ts` mirrors them by hand. That is why there is
no schema layer here — there is nothing to translate.

Every endpoint takes the repository root as its first argument rather than reading module state.
The server binds it once (`router.build`), which keeps these functions callable from a test with
a `tmp_path` and no port open.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, cast

from ..._errors import TaskopsError
from ..._version import __version__
from ...usecases import activity, ask, board, fleet, search, standup, update
from ...usecases.report import HISTORY_WINDOW
from ._wire import Reply, Request, error_reply, json_reply

__all__ = ["config", "get_board", "get_fleet", "get_standup", "get_task", "get_search",
           "get_activity", "post_comment", "post_status", "guarded", "strings"]


def config(root: Path, request: Request) -> Reply:
    """What the UI needs before its first render. Sent once, so the board does not have to
    discover it is read-only by being refused."""
    return json_reply({"version": __version__, "repo": str(root),
                       "readonly": request.param("_readonly") == "1"})


def get_board(root: Path, request: Request) -> Reply:
    return guarded(lambda: json_reply(board(root)))


def get_fleet(root: Path, request: Request) -> Reply:
    return guarded(lambda: json_reply(fleet(root)))


def get_standup(root: Path, request: Request) -> Reply:
    since = request.param("since", "24h")
    return guarded(lambda: json_reply(standup(root, since=since)))


def get_task(root: Path, request: Request) -> Reply:
    task_id = request.param("id")
    if not task_id:
        return error_reply(400, "?id=<task> is required", "bad_request")
    return guarded(lambda: json_reply(ask(root, task_id)))


def get_activity(root: Path, request: Request) -> Reply:
    """The history: the event log as a timeline, with a roll-up per actor.

    One read for both, because they are one projection of one list — asking twice would mean two
    scans of the same events, and a per-actor summary computed over a different window than the
    timeline it sits next to would be a summary of something the reader cannot see.
    """
    since = request.param("since", HISTORY_WINDOW)
    # `from`/`to` are epoch seconds and win over the window: "last month" has two ends, and where a
    # month STARTS is the client's fact (the 1st at 00:00 wherever the reader is), not this clock's.
    range_from = float(request.param("from", "0") or 0)
    range_to = float(request.param("to", "0") or 0)
    return guarded(lambda: json_reply(
        activity(root, since=since, range_from=range_from, range_to=range_to)))


def get_search(root: Path, request: Request) -> Reply:
    query = request.param("q")
    if not query:
        return json_reply([])
    return guarded(lambda: json_reply(search(root, query)))


def post_comment(root: Path, request: Request) -> Reply:
    """A human talking to the agents. The mentions reach their inboxes like any other message.

    The actor is RESOLVED, never taken from the request: a browser that could name its own
    actor could post as somebody else's agent, and this thread is a permanent record.
    """
    payload = request.payload()
    task_id, text = str(payload.get("task", "")), str(payload.get("text", "")).strip()
    if not task_id or not text:
        return error_reply(400, "`task` and `text` are required", "bad_request")
    mentions = strings(payload, "mentions")
    return guarded(lambda: json_reply(
        update(root, task_id, comment=text, mentions=mentions)))


def strings(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    """A tuple field off a JSON body. Tolerates the two shapes a client can produce — a list,
    or one comma-separated field — because a message that silently reached nobody is the worst
    way for this to fail, and the same is true of a label filter that silently matched
    everything. Shared by `mentions` here and by `labels` on the agent endpoints."""
    raw: object = payload.get(key)
    if isinstance(raw, str):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    if isinstance(raw, list):
        items = cast("list[object]", raw)
        return tuple(str(item).strip() for item in items if str(item).strip())
    return ()


def post_status(root: Path, request: Request) -> Reply:
    payload = request.payload()
    task_id, status = str(payload.get("task", "")), str(payload.get("status", ""))
    if not task_id or not status:
        return error_reply(400, "`task` and `status` are required", "bad_request")
    comment = str(payload.get("comment", ""))
    return guarded(lambda: json_reply(
        update(root, task_id, status=status, comment=comment)))


def guarded(call: Callable[[], Reply]) -> Reply:
    """Run an endpoint, turning a typed failure into its own HTTP status.

    The taxonomy already carries `http_status`, so a new error type gets the right code the day
    it is added rather than the day somebody remembers to map it here.
    """
    try:
        return call()
    except TaskopsError as err:
        return error_reply(err.http_status, str(err), err.code)
    except OSError as err:
        return error_reply(500, str(err), "io_error")
