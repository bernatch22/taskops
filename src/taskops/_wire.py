"""One POST, one envelope, one place that turns an HTTP failure into OUR error.
And, since the host learned to ask a forge, one GET that deliberately does NOT
wear that envelope — `get()` at the bottom says why.

    {"ok": true,  "seq": 41, "data": {...}}     ->  the data, with `seq` in it
    {"ok": false, "error": {"code", "message"}} ->  raised, in the SERVER's words

Every door this package speaks to answers that shape (`http/rpc.py` says why it
is always an object). There are now two clients — `board.py::RemoteBoard` for
/rpc and `session.py` for /login — and they were briefly two copies of this
decoder, which is how the pair drifts: one of them keeps the server's refusal
and the other reports "HTTP 409". So the decoder is here, once, and both call it.

A refusal must survive the wire INTACT. "that key is not registered on this host
— the owner registers one: taskops server key add …" is the whole value of the
answer; replacing it with a status code throws away the only sentence that tells
somebody what to do next.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from ._json import as_object
from ._errors import Unreachable, from_code


def post(
    url: str, body: dict[str, Any] | bytes, headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    """POST JSON and come back with the envelope's `data`, `seq` folded in.

    `body` may be BYTES: /rpc relays a call exactly as the page wrote it, never
    re-serialised from a dict.
    """
    request = Request(  # noqa: S310 — the scheme comes from the project's own config
        url,
        data=body if isinstance(body, bytes) else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as answer:  # noqa: S310
            envelope: dict[str, Any] = as_object(json.loads(answer.read().decode()))
    except HTTPError as err:
        raise _refusal(err, url) from err
    except (URLError, TimeoutError, ValueError) as err:
        raise Unreachable(
            f"{url} did not answer ({err}). The board is the server's, so nothing was "
            "written. Check the server, or your .taskops/remote.json credential."
        ) from err
    return _unwrap(envelope, url)


def get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, dict[str, Any]]:
    """GET JSON from a server that is NOT a taskops one — the status comes back.

    `post` unwraps `{"ok", "data"}` because both of its callers speak to a
    taskops door. A forge does not: it answers its own shape and says what it
    MEANS in the status — 401 is a bad token, 404 is "no repo you can see" —
    so flattening those into one error would throw away the only thing the
    caller can turn into a sentence somebody can act on.

    What stays shared is the failure with no status at all: a refused
    connection, a DNS miss, a timeout. That is `Unreachable` here exactly as it
    is above, because the one caller of this function GRANTS on its answer and
    must never be able to read silence as a yes.
    """
    request = Request(url, headers=headers, method="GET")  # noqa: S310 — https, from our config
    try:
        with urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return int(answer.status), _decode(answer.read())
    except HTTPError as err:
        return int(err.code), _decode(_body_of(err))
    except (URLError, TimeoutError, ValueError) as err:
        raise Unreachable(
            f"{url} did not answer ({err}). Nothing was granted and nothing was written — "
            "a host that cannot ask does not guess."
        ) from err


def _body_of(err: HTTPError) -> bytes:
    try:
        return err.read()
    except OSError:  # pragma: no cover — a body that dies mid-read
        return b""


def _decode(raw: bytes) -> dict[str, Any]:
    """A foreign answer that is not an object is not an error here: the STATUS
    already carried the meaning, and the caller reads a field or finds none."""
    try:
        return as_object(json.loads(raw or b"{}"))
    except ValueError:
        return {}


def _unwrap(body: dict[str, Any], url: str) -> dict[str, Any]:
    """v1 let three verbs answer with a bare array, which the client decoder turned
    into `{}` with no error anywhere. Here a missing envelope is loud."""
    if not body.get("ok", False):
        error = as_object(body.get("error"))
        raise from_code(str(error.get("code", "error")), str(error.get("message", body)))
    if not isinstance(body.get("data"), dict):
        raise Unreachable(f"{url} answered without a data object — is that a taskops server?")
    data = as_object(body.get("data"))
    data.setdefault("seq", body.get("seq", 0))
    return data


def _refusal(err: HTTPError, url: str) -> Exception:
    """An HTTP error still carries the server's own refusal — keep its message."""
    try:
        error = as_object(as_object(json.loads(err.read().decode())).get("error"))
    except (ValueError, OSError):
        error = {}
    if error.get("message"):
        return from_code(str(error.get("code", "error")), str(error["message"]))
    return Unreachable(f"{url} answered HTTP {err.code} ({err.reason})")
