"""Serving the built UI out of the package.

The bundle ships INSIDE the wheel (`transports/http/ui/`), so `pip install taskops` serves the
board with no node toolchain anywhere. A path outside the package would work from a checkout and
404 from an install — the worst possible split, because it only breaks for users.
"""

from __future__ import annotations

from pathlib import Path

from ._wire import Reply, error_reply

__all__ = ["serve", "UI"]

UI = Path(__file__).resolve().parent / "ui"

_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
          ".json": "application/json", ".ico": "image/x-icon",
          ".woff2": "font/woff2", ".png": "image/png"}

_MISSING = (b"<!doctype html><meta charset=utf-8><title>taskops ui</title>"
            b"<body style='font:14px/1.6 ui-monospace,monospace;padding:3rem;"
            b"max-width:44rem;margin:auto;background:#0f1115;color:#e6e8ee'>"
            b"<h1 style='color:#b8ff3a'>ui not built</h1>"
            b"<p>The UI bundle is missing from this install. From a checkout:</p>"
            b"<pre style='background:#171a21;padding:1rem;border-radius:6px'>"
            b"cd ui &amp;&amp; npm install &amp;&amp; npm run build</pre>"
            b"<p>The JSON API is up either way &mdash; try "
            b"<a style='color:#b8ff3a' href='/api/board'>/api/board</a>.</p>")


def serve(path: str) -> Reply:
    """One file from `ui/`, or index.html for anything the SPA routes itself.

    A missing bundle answers with an INSTRUCTION rather than a 404: it happens exactly once per
    checkout, to somebody who has just cloned the repository, and "not found" would send them
    looking for a bug instead of running the build.
    """
    target = _resolve(path)
    if target is None:
        return Reply(status=200, body=_MISSING,
                     headers={"Content-Type": "text/html; charset=utf-8"})
    try:
        body = target.read_bytes()
    except OSError as err:
        return error_reply(500, f"cannot read {target.name}: {err}", "io_error")
    return Reply(status=200, body=body, headers=_headers(target))


def _resolve(path: str) -> Path | None:
    """The file to send, or None when the bundle is absent.

    The traversal check is the important line: a request for `/../../etc/passwd` must not escape
    `ui/`, and `is_relative_to` after resolving is the check that actually holds — comparing
    strings before resolving is the version that gets bypassed.
    """
    index = UI / "index.html"
    wanted = (UI / path.lstrip("/")).resolve() if path not in ("/", "") else index
    if not wanted.is_relative_to(UI.resolve()) or not wanted.is_file():
        return index if index.is_file() else None
    return wanted


def _headers(target: Path) -> dict[str, str]:
    """`no-cache` on EVERYTHING, deliberately.

    The usual split — immutable assets, uncached entry point — needs content-hashed filenames to
    be safe, and these are not hashed: `app.js` keeps its name across every build. Caching it
    would leave a developer staring at yesterday's UI after a rebuild with nothing to explain it.
    Revalidation costs a 304 against a server on loopback, which is free.
    """
    return {"Content-Type": _TYPES.get(target.suffix, "application/octet-stream"),
            "Cache-Control": "no-cache"}
