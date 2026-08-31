"""Serving the UI bundle. Small on purpose: the board is an API, not a website.

**A WINDOW serves it — and, since §16's hosted-window amendment, so does a
serve-mode host, but only for a board whose owner declared a forge.** The
handler asks `repos.backed()` for the FACT and serves `PACKAGED` behind the
same credential /rpc asks for; a board with no forge keeps the one sentence
(`NO_UI` below, answered `410 Gone`), which now names both ways out.

Why, and it is the same rule as /git's (ARCHITECTURE.md §16): a dashboard shows
DIFFS, and a diff needs a repo to read. A host with none — the state every
board's host is in until its owner declares a forge — could only serve a page
that falls through every step of `links.tsx::cascade` to a forge link or a
sentence. That was serving a degraded window and calling it *the* window. The
binary serves the window; the server serves the truth. What ends that state is
§16's hosted-window amendment: a bare READ-ONLY mirror of the DECLARED forge
(`<root>/<board>/mirror.git`), and only a board that holds one gets `/ui/`
back. `NO_UI` therefore means "this board declared no forge", never "this host
can never have a repo".

`410 Gone` rather than 404 because the two say different things to whoever typed
the URL: 404 is "no idea what that is, maybe later", and this is neither vague
nor temporary. The page WAS here, it was withdrawn on purpose, and only the
owner's own act (`taskops board forge`) brings it back — never time, never a
retry. The body is plain text, not the JSON error envelope,
because the one reader who reaches this door is a human with a browser.

The bundle is NOT removed from the package: `src/taskops/ui/` still ships inside
the wheel, which is what lets `pip install taskops` + `taskops ui` serve a
dashboard with no node toolchain. Only the server-side mount went, and the
`--ui` flag that configured it went with it rather than staying as a dead option.
"""

from __future__ import annotations

from pathlib import Path

NO_UI = (
    "this board's window is not served here — it declares no forge for this "
    "host to mirror. Two ways in: run `taskops ui` in a checkout joined to "
    "this board (the window reads your own clone), or the owner declares the "
    "repo with `taskops board forge <owner>/<repo>` and this host serves the "
    "page itself.\n"
)

PACKAGED = Path(__file__).resolve().parent.parent / "ui"
"""The bundle the wheel ships (`src/taskops/ui/`). A WINDOW mounts it via
`Mounts.ui`; a serve-mode host serves the SAME files for a board whose owner
declared a forge — one copy, never a second bundle path to drift."""

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


def asset(rest: str) -> bool:
    """Is this tail a file the packaged bundle actually ships?

    Since tk-32d2ba the page lives at the board's OWN address, so its relative
    links — `./style.css`, `./app.js` off `index.html` — arrive as
    `/<board>/style.css` and the router must tell the page's tails from a
    board's machine doors. It can, deterministically: the bundle's filenames
    are a CLOSED SET — whatever `ui/build.mjs` wrote into the wheel, flat,
    every suffix in `TYPES` — and none of them is `rpc`, `git`, `feed`, `ui`
    or `api`, so an asset can never shadow a door and a door never shadows an
    asset. Checked against the real files rather than a hardcoded list, so a
    bundle that grows a font ships without a router edit; a nested or
    dot-leading tail is refused before disk is asked, which also keeps `..`
    out without a resolve."""
    if not rest or "/" in rest or rest.startswith(".") or Path(rest).suffix not in TYPES:
        return False
    return (PACKAGED / rest).is_file()


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
    NO window opens for this board here — a board host whose board declared no
    forge — and the module docstring argues why that is a 410 and one sentence
    (now naming BOTH ways out) rather than a page."""
    if root is None:
        return 410, NO_UI.encode(), "text/plain; charset=utf-8"
    found = payload(root, rest)
    if found is None:
        return 404, MISSING.encode(), "text/plain; charset=utf-8"
    return 200, found[0], found[1]
