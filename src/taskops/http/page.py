"""The page door — `handler._static`, moved whole when the git smart-HTTP
door (`gitpack.py`) pushed the handler past its ≤200-line budget: this is the
one GET branch that is a policy of its own (visibility, the repo fact, the
410) rather than a route, so it is the cohesive cut. The bytes themselves are
still `static.py`'s; the credential is still the handler's ONE `_credential`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from hashlib import sha256

from . import rpc, static
from .._errors import TaskopsError

if TYPE_CHECKING:
    from .handler import Handler


class Writer(Protocol):
    """The slice of an HTTP handler this module needs to answer a page."""

    headers: Any
    wfile: Any

    def send_response(self, code: int, message: str | None = None) -> None: ...

    def send_header(self, keyword: str, value: str) -> None: ...

    def end_headers(self) -> None: ...


def validator(data: bytes) -> str:
    """The bundle's own content, as an ETag. A hash and not an mtime: the wheel
    is unpacked afresh on every install, so every file's mtime moves whether or
    not a byte changed, and a validator that lies in THAT direction is worse
    than none — it would 304 a reader onto the build they already had."""
    return f'"{sha256(data).hexdigest()[:16]}"'


def deliver(out: Writer, status: int, data: bytes, kind: str) -> None:
    """Write a page or an asset, with the one header pair that keeps a reader
    off a build they have already replaced.

    **`no-cache` is not "do not store" — it is "ask me first".** The bundle's
    URL never changes (`/app.js`, one name, three mounts) while its CONTENT
    changes on every `node ui/build.mjs` and on every upgrade. Served with no
    Cache-Control and no validator, as it was until 2026-09-08, a browser has
    nothing to revalidate against and nothing saying the answer is stale, so it
    applies its own heuristic and can serve the previous build after an install
    — silently, and for as long as it likes, because a reload of a URL it
    believes is fresh never reaches this process at all.
    `static.payload()` re-reads the file per request precisely so the SERVER can
    never be stale; this is that same rule carried one hop further, to the only
    party left that could be.

    The ETag makes the ask cheap: a reader already holding the current build
    gets a 304 and no body, so correctness costs one round trip and not 345 KB.
    It is content-addressed, so two hosts serving one wheel agree, and a rebuild
    that changed nothing revalidates to the same tag.

    A refusal (410, 404) carries neither header: those are sentences about the
    board's state, they are cheap, and caching a `NO_UI` past the push that ends
    it would be this same bug pointing the other way."""
    tag = validator(data) if status == 200 else ""
    if tag and out.headers.get("If-None-Match") == tag:
        out.send_response(304)
        out.send_header("ETag", tag)
        out.send_header("Content-Length", "0")
        out.end_headers()
        return
    out.send_response(status)
    out.send_header("Content-Type", kind)
    out.send_header("Content-Length", str(len(data)))
    if tag:
        out.send_header("Cache-Control", "no-cache")
        out.send_header("ETag", tag)
    out.end_headers()
    out.wfile.write(data)


def answer(handler: Handler, board: str, rest: str) -> None:
    """The page — at the board's own root since tk-32d2ba, and still at
    /ui/, the 0.5.0 address (kept: links were pasted). A WINDOW serves
    its bundle to whoever reaches the port, unchanged. A serve-mode HOST
    serves the SAME packaged bundle for a board
    whose own repository is here (`repos.backed` — the fact, never a diff),
    behind the credential /rpc asks for: public board, anonymous READ;
    private board, the join refusal. The 410 comes BEFORE the credential on
    purpose — it says nothing about the board a login would guard, and the
    no-git sentence predates keys on this door. A GET here runs no verb,
    so an anonymous page load writes nothing — no presence row (§11)."""
    if handler.mounts.ui is not None:
        deliver(handler, *static.answer(handler.mounts.ui, rest))
        return
    try:
        handler.mounts.check(board)
        if not handler.mounts.repos.backed(board):
            deliver(handler, *static.answer(None, rest))
            return
        handler._credential(board, "read")  # noqa: SLF001
    except TaskopsError as err:
        handler._fail(rpc.status_for(rpc.failure(err)), err)  # noqa: SLF001
        return
    deliver(handler, *static.answer(static.PACKAGED, rest))
