"""The one error tree.

Every exception that escapes this package descends from `TaskopsError`. A
foreign exception is converted at the boundary that raises it (`raise X from
err`) — a caller never sees `sqlite3.OperationalError` or
`json.JSONDecodeError`. Each class carries a stable `code` because that code
crosses the wire in the RPC envelope, so the string lives here and nowhere
else.

`Refused` is the interesting one: a rule said no, and **its message contains
the call that fixes it, verbatim**. That was the best habit of v1 and it is
kept word for word.
"""

from __future__ import annotations


class TaskopsError(Exception):
    """Root of everything this package raises."""

    code = "error"


class Refused(TaskopsError):
    """A rule said no. The message must name the way out."""

    code = "refused"


class NotFound(TaskopsError):
    """A card, milestone, board or event that does not exist."""

    code = "not_found"


class Unreachable(TaskopsError):
    """The remote board did not answer. Never silently degrades to local."""

    code = "unreachable"


class BadRequest(TaskopsError):
    """Malformed input: bad actor grammar, unknown verb, wrong argument shape."""

    code = "bad_request"


CODES: dict[str, type[TaskopsError]] = {
    cls.code: cls for cls in (Refused, NotFound, Unreachable, BadRequest, TaskopsError)
}


def from_code(code: str, message: str) -> TaskopsError:
    """Rebuild an error carried over the wire. Unknown code → the root type."""
    return CODES.get(code, TaskopsError)(message)
