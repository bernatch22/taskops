"""Logging in with GitHub — and the server never holds a GitHub credential to do it.

**The validation runs on the USER's token, not the server's.** The client sends the token
its own `gh auth token` prints; the server asks `GET /repos/{owner}/{repo}` WITH THAT TOKEN
and believes the answer: 200 with `permissions.push` true means the account may write to the
repository, which is exactly the group that should be able to open its board. So there is no
GitHub App, no OAuth secret, no webhook, and nothing on this disk that could be stolen and
used against GitHub — the server's whole knowledge of the world is `owner/repo` in a file.

**The token is used for these calls and DISCARDED.** It is never written to `.sessions.json`,
never logged, never returned, and never kept in memory past this function. What survives the
login is the session `mint` returns — which grants exactly the projects that answered yes, on
this server only, for a week. `tests/transports/test_accounts.py` pins that as an assertion,
because "we don't store it" is a claim that decays silently.

**GitHub is the collaborator list, and is never copied.** Granting somebody the board IS
granting them the repository, which is a thing the owner already does. Revoking access on
GitHub closes the door on the next login rather than the next request — a week at worst,
which is the trade a stateless session makes and the reason `TTL` is short.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest, TaskopsError, Unreachable
from ._ghlink import links
from ._sessions import mint

__all__ = ["authenticate", "may_push", "NoAccess", "API", "TIMEOUT"]


class NoAccess(TaskopsError, PermissionError):
    """Identity established, permission absent — 403 and never 401.

    401 means "authenticate", and repeating it here would send somebody back to the login
    they just completed. It lives beside the login rather than in `_errors` because that
    module is at its line budget and this is the only place that can raise it: no boundary
    outside the login has an identity to establish, so nothing else could ever catch it by
    type. Every transport maps it the same way regardless — by `http_status`, like the rest.
    """

    code = "no_access"
    http_status = 403

API = "https://api.github.com"

TIMEOUT = 10.0
"""Per call. A login walks the linked projects one at a time, so this bounds each hop rather
than the whole thing — a server with twenty linked repositories answers a login in seconds."""

AGENT = "taskops"
"""GitHub REFUSES a request with no `User-Agent`, with a 403 that reads like a permission
problem. Sending one is not politeness; it is the difference between working and not."""


def authenticate(root: Path, github_token: str) -> dict[str, Any]:
    """`{"login", "session", "projects"}` — or `NoAccess` when nothing would be in it.

    `root` is the SERVER root (a directory of projects), not a taskops repository.
    """
    home = Path(root)
    token = github_token.strip()
    if not token:
        raise BadRequest("a GitHub token is required — `taskops login` sends the one "
                         "`gh auth token` prints, and this server keeps none of its own")
    login = str(_call(token, "/user").get("login") or "")
    granted = [name for name, slug in links(home) if may_push(token, slug)]
    if not granted:
        raise NoAccess(f"the GitHub account {login or 'you logged in as'} has no push access "
                       f"to any repository linked to a project on this server — ask whoever "
                       f"owns the repository for write access, then run `taskops login` again")
    return {"login": login, "session": mint(home, login, granted), "projects": granted}


def whoami(github_token: str) -> str:
    """The GitHub login behind a token, asked of GitHub. Never taken from the caller.

    Exported because CREATING a board needs the same answer logging in does, and the reason
    the client cannot supply it is the whole security argument: the request carries a token and
    no username, so there is nothing to forge — the name comes back from `/user` or not at all.
    """
    return str(_call(github_token.strip(), "/user").get("login") or "")


def may_push(token: str, slug: str) -> bool:
    """Write access to one repository. A repository the account cannot see answers 404, which
    is GitHub refusing to confirm it exists — the same answer as "no access", and treated as
    one here so a private repository is never an existence oracle.

    ONLY 404 counts as "not yours". A 403 is a rate limit or a suspended token far more often
    than it is a permission, and swallowing it would turn "GitHub is throttling us" into a
    silent, confusing "you have access to nothing" — so it is raised with GitHub's own words.
    """
    found = _call(token, f"/repos/{slug}", absent=True)
    rights = found.get("permissions")
    return bool(isinstance(rights, dict) and cast("dict[str, Any]", rights).get("push"))


def _call(token: str, path: str, *, absent: bool = False) -> dict[str, Any]:
    """One GitHub read. Anything that is not an answer becomes a typed error a transport
    already knows how to map — and GitHub's own words are relayed VERBATIM, because when the
    reason is a rate limit or a revoked token, its sentence is the only one that says so."""
    request = urllib.request.Request(API + path)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", AGENT)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return _body(answer.read())
    except urllib.error.HTTPError as err:
        return _refused(err, absent=absent)
    except (urllib.error.URLError, OSError) as err:
        raise Unreachable(f"could not reach {API}: {err} — the login needs GitHub, and "
                          f"nothing else on this server does") from err


def _refused(err: urllib.error.HTTPError, *, absent: bool) -> dict[str, Any]:
    said = str(_body(err.read()).get("message") or "").strip()
    if absent and err.code == 404:
        return {}
    if err.code in (401, 403):
        raise NoAccess(f"github refused the token ({err.code}): {said or 'no reason given'}")
    raise Unreachable(f"github answered {err.code}: {said or 'no body'}")


def _body(raw: bytes) -> dict[str, Any]:
    try:
        parsed: Any = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}
