"""What a project is linked to on GitHub: one file, one line, `owner/repo`.

The link is the entire configuration of the login: it says which repository's collaborator
list stands for this board. There is no second field — no team, no role, no list of allowed
logins — because every one of those would be a copy of something GitHub already knows, and a
copy is the thing that goes stale the day somebody's access is revoked.

**Shape is validated, existence is not.** `[\\w.-]+/[\\w.-]+` is checked when the link is
written, so a typo is refused where a person can see it; whether the repository exists is
answered by GitHub at login time, with the USER's token, which is the only place it can be
answered honestly. A project with no link is unchanged by any of this: token only.
"""

from __future__ import annotations

import re
from pathlib import Path

from .._errors import BadRequest

__all__ = ["LINK_FILE", "SLUG", "read_link", "write_link", "remove_link", "links"]

LINK_FILE = "github"

SLUG = re.compile(r"^[\w.-]+/[\w.-]+$")
"""`owner/repo`. Deliberately narrow: it is pasted into a URL path, so anything that could
carry a `/`, a `?` or a `..` past the two segments is refused as syntax, before any request."""


def read_link(project: Path) -> str:
    """The slug, or "" when the project is not linked."""
    try:
        return (project / LINK_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_link(project: Path, slug: str) -> str:
    """Link the project. Returns the slug written; raises on a shape that cannot be one."""
    cleaned = slug.strip()
    if not SLUG.match(cleaned) or _traversal(cleaned):
        raise BadRequest(f"'{slug}' is not a GitHub repository — write it as owner/repo, "
                         f"exactly as it appears in the URL of the repository page")
    (project / LINK_FILE).write_text(cleaned + "\n", encoding="utf-8")
    return cleaned


def _traversal(slug: str) -> bool:
    """`..` is a legal `[\\w.-]+`, and `../etc` therefore passes the shape while naming
    `https://api.github.com/repos/../etc` — a request to a different endpoint entirely. A
    segment that is nothing but dots is never a GitHub name, so it is refused outright."""
    return any(set(part) == {"."} for part in slug.split("/"))


def remove_link(project: Path) -> bool:
    """Unlink. True when there was one — the project falls back to token-only."""
    try:
        (project / LINK_FILE).unlink()
    except OSError:
        return False
    return True


def links(root: Path) -> list[tuple[str, str]]:
    """`(project, slug)` for every linked project under the server root, sorted.

    Directories are read from disk rather than matched against the URL-name pattern that
    lives in the HTTP transport: a use case may not import a transport, and a project whose
    name is not servable is one the login can hand out and no URL can reach — harmless, and
    strictly better than duplicating the pattern in a second place that drifts.
    """
    try:
        found = sorted(path for path in root.iterdir() if path.is_dir())
    except OSError:
        return []
    return [(path.name, slug) for path in found if (slug := read_link(path))]
