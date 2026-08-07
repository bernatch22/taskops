"""POST /<board>/rpc — the one door, and the envelope every answer wears.

    {"ok": true,  "seq": 41, "data": {...}}
    {"ok": false, "error": {"code": "refused", "message": "…"}}

Always an object. v1 let three verbs answer with a bare array and the client
decoder turned each one into `{}` with no error logged anywhere; with an
envelope that class of bug cannot be written.

`seq` is the server's monotonic counter, so both sides talk about the same
number. v1 had two incomparable cursors and reconciled them by guessing.
"""

from __future__ import annotations

from typing import Any, cast

from .. import verbs
from .._json import as_object
from .._errors import Refused, NotFound, BadRequest, Unreachable, TaskopsError
from ..store.stores import Stores

STATUS: dict[type[TaskopsError], int] = {
    BadRequest: 400,
    Refused: 409,
    NotFound: 404,
    Unreachable: 502,
}


def dispatch(stores: Stores, verb: str, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run a verb and wrap it. Raises nothing: failures come back as envelopes."""
    try:
        data = verbs.call(stores, verb, actor, args)
    except TaskopsError as err:
        return failure(err)
    return {"ok": True, "seq": stores.head(), "data": data}


def failure(err: TaskopsError) -> dict[str, Any]:
    return {"ok": False, "error": {"code": err.code, "message": str(err)}}


def status_for(body: dict[str, Any]) -> int:
    if body.get("ok"):
        return 200
    error = body.get("error")
    code = cast("str", error["code"]) if isinstance(error, dict) and "code" in error else ""
    for kind, number in STATUS.items():
        if kind.code == code:
            return number
    return 500


def verb_of(payload: dict[str, Any]) -> str:
    """The verb first: what it needs decides which credential can run it."""
    verb = payload.get("verb")
    if not isinstance(verb, str) or verb not in verbs.REGISTRY:
        known = ", ".join(sorted(verbs.REGISTRY))
        raise BadRequest(f"verb must be one of: {known}")
    return verb


def rest_of(payload: dict[str, Any], subject: str) -> tuple[str, dict[str, Any]]:
    """(actor, args). An omitted actor falls back to the credential's own subject.

    That fallback is what lets the browser call `board` with nothing but a
    token — and it is NOT the identity inference of v1, which guessed from five
    places: this is the one identity the credential already proved.
    """
    actor = payload.get("actor")
    if not isinstance(actor, str) or not actor:
        actor = subject if subject.startswith(("dev:", "agent:")) else ""
    if not actor:
        raise BadRequest(
            "this credential names no person, so the call must name its actor. "
            "A worker exports it: export TASKOPS_ACTOR=agent:<dev>/<name>"
        )
    if not isinstance(payload.get("args", {}), dict):
        raise BadRequest("args must be an object")
    return actor, as_object(payload.get("args", {}))


def needs(verb: str) -> str:
    """The capability a verb consumes — the registry decides, not the router."""
    return "write" if verbs.writes(verb) else "read"
