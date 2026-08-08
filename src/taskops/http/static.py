"""Serving the UI bundle. Small on purpose: the board is an API, not a website."""

from __future__ import annotations

from pathlib import Path

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

INDEX = "index.html"


def resolve(root: Path, rest: str) -> Path | None:
    """Map a URL tail to a file inside `root`, or None.

    The containment check is done on the RESOLVED path: `..%2f..` and symlinks
    both collapse before the comparison, so a request cannot climb out of the
    bundle directory.
    """
    if not root.is_dir():
        return None
    target = (root / rest.lstrip("/")).resolve() if rest.strip("/") else (root / INDEX).resolve()
    base = root.resolve()
    if base != target and base not in target.parents:
        return None
    if target.is_dir():
        target = target / INDEX
    if target.is_file():
        return target
    fallback = base / INDEX  # a single-page app answers its own routes
    return fallback if fallback.is_file() else None


def content_type(path: Path) -> str:
    return TYPES.get(path.suffix, "application/octet-stream")


def payload(root: Path, rest: str) -> tuple[bytes, str] | None:
    """(bytes, content-type) for a URL tail, or None. The bundle is small and
    read per request on purpose: `taskops ui` is a developer's own process, and
    a cache would serve the previous build after every `node ui/build.mjs`."""
    path = resolve(root, rest)
    return (path.read_bytes(), content_type(path)) if path else None
