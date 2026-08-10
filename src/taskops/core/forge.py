"""The forge vocabulary — what a board means when it says "GitHub opens me".

Three parties have to agree on one shape and none of them may own it: the
board FACT is an event (`verbs/project.py`, `op=forge`), the QUESTION is one
API call (`http/login.py`), and the DECLARATION is typed by a human at the
CLI. Put the words in any one of the three and the other two import sideways
or, worse, spell them again — v1's second identity system started exactly like
that. So they live here, pure, where every layer above may read them.

    {"host": "github.com", "repo": "owner/name", "need": "push" | "admin"}

`repo` is NOT parsed here and never anywhere above layer 4: the side holding
the clone already turned `origin` into `{host, slug, url}` (`gitwork/remote.py`
— which `core/` may not import and must not be duplicated), so `slug` IS the
argument and this module only judges its SHAPE.

Two functions, and the asymmetry between them is the point. `declare` refuses
loudly, because a human is typing and a typo that defaults to something
plausible hands a board to a stranger. `understood` refuses silently to None,
because a door GRANTS on its answer and a value nobody can verify — from an
older log, a newer op, a hand-edited file — must read as "no forge" rather
than as a promise the host cannot keep.
"""

from __future__ import annotations

from typing import Any

from .._json import as_object
from .._errors import BadRequest

GITHUB = "github.com"
FORGES = (GITHUB,)
"""The forges whose membership this host can VERIFY — one, today. Narrower
than the hosts `project op=remote` stores: gitlab.com is fine there, because
linking a commit needs no API. An unknown host is refused at DECLARATION time
rather than stored and refused later at the door."""

PUSH = "push"
ADMIN = "admin"
NEEDS = (PUSH, ADMIN)
"""The access that opens the board — GitHub's own `permissions` keys, so the
door reads `permissions[need]` out of one API answer and never maps a taskops
word onto a GitHub one. `pull` is deliberately absent: read access to a public
repo is not a membership."""


def is_repo(repo: str) -> bool:
    """Two non-empty segments, no third, no whitespace: `owner/name/extra` and
    `owner/` are how a real origin arrives wrong (GitLab nests groups), a space
    is how a typed one does. `GET /repos/{owner}/{name}` has nowhere to put a
    third segment, so a long slug is refused rather than truncated."""
    parts = repo.split("/")
    return len(parts) == 2 and all(parts) and not any(ch.isspace() for ch in repo)


def declare(host: str, repo: str, need: str) -> dict[str, Any]:
    """A human's three words → the stored fact. Each refusal names the way out."""
    if host not in FORGES:
        raise BadRequest(
            f"host={host!r} — a forge is a host this server can ASK about membership, "
            f"and that is {FORGES} today. A repo elsewhere is still recorded as the "
            "board's remote; it just does not open it"
        )
    if not is_repo(repo):
        raise BadRequest(
            f"repo={repo!r} — a forge repo is exactly owner/name (the `slug` half of "
            "a parsed origin), e.g. repo=bernatch22/taskops"
        )
    if need not in NEEDS:
        raise BadRequest(
            f"need={need!r} — the access that opens this board is one of {NEEDS}, "
            "GitHub's own permission names. Read access is not a membership"
        )
    return {"host": host, "repo": repo, "need": need}


def understood(fact: object) -> dict[str, Any] | None:
    """The stored fact → what a door may act on, or None. Absent, cleared and
    unintelligible collapse to the one None every board is born in."""
    declared = as_object(fact)
    host, repo, need = (str(declared.get(key, "")) for key in ("host", "repo", "need"))
    if host not in FORGES or need not in NEEDS or not is_repo(repo):
        return None
    return {"host": host, "repo": repo, "need": need}
