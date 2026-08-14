"""The questions the OWNER asks GitHub, from their own laptop, with their own token.

    collaborators("bernatch22/taskops", "push", token)  ->  ["ana", "leo", …]
    keys_of("ana")                                      ->  ["ssh-ed25519 AAAA…", …]

Two calls, and only the FIRST one is authenticated — `<login>.keys` is a public
endpoint, which is the whole reason this chapter exists: somebody with push on a
repo has already published the key they push with, so asking them for a second
one was always redundant.

**The token's whole life is inside `collaborators`.** Read by `token()`, put in
one `Authorization` header per page, dropped with the frame: not returned, not
printed, not written, and never sent to the taskops host — `http/members.py`
takes principals and ssh key lines and does not know what GitHub is. That is how
`taskops board forge` syncs a team without the host ever holding somebody's
credential.

**This is the ONLY place in taskops that talks to GitHub.** A board door used to
ask the neighbouring question — does the token this stranger just POSTed have
`need` on the repo — and it is deleted: it made every dev's own credential travel
to the host for a fact the owner already holds. Here the token never leaves the
machine that owns it, and the host is told nothing but principals and ssh key
lines. A second door asking GitHub anything is the thing not to re-introduce.
"""

from __future__ import annotations

import os
import json
import getpass
from typing import Any

from .. import _wire
from .._json import as_rows, as_object
from .._errors import TaskopsError

API = "https://api.github.com"
KEYS = "https://github.com"
"""The two roots, as module constants so a test can point them at a stub over a
real socket — mocking `_wire` instead would test neither urllib, nor the header
the token travels in, nor the pagination, which is where a team of 31 silently
became a team of 30."""

TIMEOUT = 20.0
PAGE = 100
"""GitHub's own maximum. Asking for fewer would only make the loop below run
more times against the same rate budget."""

NO_TOKEN = (
    "no GitHub token, and nothing was asked. Any ONE of these gives me one:\n"
    "  gh auth login              the CLI's token is read automatically\n"
    "  export GITHUB_TOKEN=…      an environment variable\n"
    "  (or paste it at the hidden prompt)\n"
    "No flag takes a token, deliberately: a token in a flag value lands in your shell "
    "history forever, and this one is only ever used for a single command."
)


def token() -> str:
    """WHERE the token comes from, in order — and never from a flag value.

    `gh auth token` first, because the CLI is already installed and already
    authenticated on the machine of anybody who ADMINS a repo, so the common
    case asks the human nothing. Then `$GITHUB_TOKEN`, which is how CI and a
    shell that never installed `gh` say it. Then a HIDDEN prompt.

    **A flag is not one of the sources and must never become one.** A secret
    passed as an argument is written to `~/.zsh_history` by the shell before the
    process starts, survives every rotation of the token, and is visible in `ps`
    to every user on the box while the command runs. The prompt is the fallback
    precisely because it is the one input that leaves no trace.
    """
    from ..gitwork import run

    try:
        asked = run.tool("gh", "auth", "token", timeout=20.0)
    except TaskopsError:
        asked = None  # no `gh` on PATH, or it hung — the next source answers
    if asked is not None and asked.ok and asked.out.strip():
        return asked.out.strip()
    if os.environ.get("GITHUB_TOKEN", "").strip():
        return os.environ["GITHUB_TOKEN"].strip()
    typed = getpass.getpass("GitHub token (input hidden, used once, stored nowhere): ").strip()
    if not typed:
        raise TaskopsError(NO_TOKEN)
    return typed


def collaborators(repo: str, need: str, secret: str) -> list[str]:
    """Every human with `need` on `repo`, ALL of them — pagination is not optional.

    A first page is 30 by default and 100 at most, and a team that outgrows one
    page is exactly the team this command exists for: stopping at page one would
    enrol some of them and report the rest as DRIFT, which reads as a revocation
    list. The loop ends on a short page rather than on `Link: rel="next"`, which
    would be a second condition saying the same thing.

    The `permission=` filter is GitHub's own, and each row's `permissions` object
    is checked against it because `http/github.py`'s door grants on exactly that
    field — a filter and a door that disagree let somebody in through one and
    never enrol them through the other. `type` drops bots: `github-actions[bot]`
    is not a principal name and has no key to publish.
    """
    found: list[str] = []
    page = 1
    while True:
        rows = _page(f"{API}/repos/{repo}/collaborators", repo, need, secret, page)
        found.extend(
            str(row.get("login", "")).strip()
            for row in rows
            if str(row.get("login", "")).strip() and _allowed(row, need)
        )
        if len(rows) < PAGE:
            return found
        page += 1


def _page(url: str, repo: str, need: str, secret: str, page: int) -> list[dict[str, Any]]:
    where = f"{url}?permission={need}&per_page={PAGE}&page={page}"
    status, raw = _wire.text(where, headers(secret), TIMEOUT)
    if status != 200:
        raise TaskopsError(_why(status, repo, need, raw))
    try:
        return as_rows(json.loads(raw or "[]"))
    except ValueError as err:  # pragma: no cover — a 200 that is not JSON
        raise TaskopsError(f"GitHub answered {where} with something that is not JSON: {err}") from err


def _allowed(row: dict[str, Any], need: str) -> bool:
    """A row GitHub filtered in, confirmed against the field the door reads. An
    entry with no `permissions` object at all is trusted to the filter — the
    alternative is dropping a whole team the day that field is renamed."""
    if str(row.get("type", "User")) != "User":
        return False
    seen = as_object(row.get("permissions"))
    return not seen or seen.get(need) is True


def keys_of(login: str) -> list[str]:
    """`https://github.com/<login>.keys` — PUBLIC, no token, no rate budget spent.

    An empty list is a real answer, not a failure: an account that pushes over
    HTTPS has published no ssh key, and the caller NAMES those people with an
    invite rather than leaving them out. A 404 — renamed or deleted between the
    two calls — collapses to the same empty list for the same reason.
    """
    status, raw = _wire.text(f"{KEYS}/{login}.keys", {"User-Agent": "taskops"}, TIMEOUT)
    if status != 200:
        return []
    seen: list[str] = []
    for line in raw.splitlines():
        one = line.strip()
        if one and one not in seen:
            seen.append(one)
    return seen


def headers(secret: str) -> dict[str, str]:
    """The token's whole life. `X-GitHub-Api-Version` is pinned because the
    shape of `permissions` is what this module reads, and an unpinned API is
    free to reshape it — a silently missing key would read as "no access"."""
    return {
        "Authorization": f"Bearer {secret}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "taskops",
    }


def _why(status: int, repo: str, need: str, raw: str) -> str:
    """The refusal, and never the token in it — `raw` is GitHub's own body, which
    holds its message and cannot hold the header it was refused for."""
    try:
        said = str(as_object(json.loads(raw or "{}")).get("message", ""))
    except ValueError:
        said = ""
    tail = f" GitHub said: {said}" if said else ""
    if status == 401:
        return (
            f"GitHub rejected that token (401) — expired, revoked or mistyped. Listing the "
            f"collaborators of {repo} needs a token of somebody who can read them.{tail}"
        )
    if status == 403:
        return (
            f"GitHub refused that token (403) listing the collaborators of {repo} — an "
            f"organisation that enforces SSO has to authorise it, and a rate limit answers "
            f"the same way. Nobody was enrolled; the board's declaration stands, so the fix "
            f"is to run the same command again.{tail}"
        )
    if status == 404:
        return (
            f"GitHub has no repository {repo!r} that this token can see — which is also what "
            f"a private repo answers a token without access. Only somebody who can read its "
            f"collaborators can sync them.{tail}"
        )
    return f"GitHub answered HTTP {status} listing the {need} collaborators of {repo} — nothing was enrolled.{tail}"
