"""Serving the UI bundle. Small on purpose: the board is an API, not a website.

**And only a WINDOW serves it.** `taskops serve` — a board host — answers /rpc,
/feed, /healthz and nothing else; its /ui/ is one sentence naming `taskops ui`
(`NO_UI` below, answered `410 Gone`).

Why, and it is the same rule as /git's (ARCHITECTURE.md §16): a dashboard shows
DIFFS, and a diff is read from the reader's own clone. The server deliberately
has no clone — it never gains a repo, a checkout or a git credential — so a page
served from it could only ever fall through every step of `links.tsx::cascade`
to a forge link or a sentence. That was serving a degraded window and calling it
*the* window. The binary serves the window; the server serves the truth.

`410 Gone` rather than 404 because the two say different things to whoever typed
the URL: 404 is "no idea what that is, maybe later", and this is neither vague
nor temporary. The page WAS here, it was withdrawn on purpose, and it is never
coming back to this host. The body is plain text, not the JSON error envelope,
because the one reader who reaches this door is a human with a browser.

The bundle is NOT removed from the package: `src/taskops/ui/` still ships inside
the wheel, which is what lets `pip install taskops` + `taskops ui` serve a
dashboard with no node toolchain. Only the server-side mount went, and the
`--ui` flag that configured it went with it rather than staying as a dead option.
"""

from __future__ import annotations

from pathlib import Path

NO_UI = (
    "this host serves the board, not the dashboard — run `taskops ui` in a "
    "checkout joined to this board and it serves the window itself, reading "
    "diffs from your own clone.\n"
)

MISSING = "no UI bundle is installed here — this checkout's taskops has none.\n"
"""A window that HAS a clone but whose install carries no bundle. Distinct from
`NO_UI`: that one is a design, this one is a broken install."""

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


def at_root(root: Path | None, path: str) -> tuple[bytes, str] | None:
    """The bundle served at the ROOT of a window — `/`, `/app.js`, `/style.css`.

    `taskops ui` used to hand out `/board/ui/?token=…`, and that path is an
    implementation detail leaking into the one URL a human types: `board` is
    just the name a window mounts its single board under, and `/ui/` was the
    door on a HOST that no longer serves a page at all. A window is a window;
    its address is its port.

    Deliberately NOT `resolve`: that one falls back to the index for any
    unknown tail, which is right for a door mounted under `/<board>/ui/` and
    wrong at the root, where it would swallow every mistyped API path and
    answer a mistake with a page. Only real files, plus `/` for the index — so
    `/nope` is still the honest 404 the API gives.

    `root is None` IS the host switch and the only one there is: `Mounts` sets
    `ui` from the same `repo is not None` that /git and /healthz's identity
    read, so a board host cannot start serving a dashboard by any route,
    including this one — there is no second condition to keep in step.
    """
    if root is None or not root.is_dir():
        return None
    rest = path.partition("?")[0].strip("/")
    base = root.resolve()
    target = (root / INDEX) if not rest else (root / rest).resolve()
    if base != target and base not in target.parents:
        return None  # `..%2f..` and symlinks have already collapsed
    return (target.read_bytes(), content_type(target)) if target.is_file() else None


def answer(root: Path | None, rest: str) -> tuple[int, bytes, str]:
    """The WHOLE /ui door: (status, body, content-type). `root is None` means
    this process is a board host — see the module docstring for why that is a
    410 and one sentence rather than a page."""
    if root is None:
        return 410, NO_UI.encode(), "text/plain; charset=utf-8"
    found = payload(root, rest)
    if found is None:
        return 404, MISSING.encode(), "text/plain; charset=utf-8"
    return 200, found[0], found[1]
