"""POST /<board>/join/github — GitHub INTRODUCES you, once, and a key stays.

    POST /<board>/join/github
      {"github_token": "…", "principal": "ana", "pubkey": "ssh-ed25519 AAAA…"}
      -> {"principal": "ana", "actor": "dev:ana", "role": "member",
          "fingerprint": "SHA256:…", "repo": "owner/name", "need": "push"}

**The token is not a credential and never becomes one.** It is read out of one
request body, put in the `Authorization` header of ONE outgoing call, and
dropped. It is not written to the log, not to `server.sqlite`, not to
`allowed_signers`, not echoed in the answer above, and not spelled into any
refusal below — the answer holds a fingerprint, which is the only thing this
door creates. Nothing here mints a session either: what the caller does next is
the ordinary `/login` challenge with the key it just enrolled, so from the
second call onwards this chapter is invisible. That is the whole difference
from v1's GitHub login, which kept the token, called GitHub on every sign-in,
and ended up as a second identity system beside the keys.

Three refusals, and each of them is a "no" that never degrades into a yes:

* **no forge declared** — the board never opted in, so this door does not exist
  for it and nothing leaves this host. A board that declares none keeps the
  invite-only flow it had before this file existed (`verbs/project.py::forge`
  is the ONE reader, and `None` is what every board is born with).
* **GitHub did not answer** — `Unreachable`, loudly, from `_wire.get`. A host
  that cannot ask does not guess.
* **that token does not have `need` on `repo`** — named, with the level that
  would work, because "403" tells the person nothing they can act on.

And one that is not about GitHub at all: a principal this host ALREADY knows is
refused. `login.register` adds a key to an existing name (an owner re-joining
with an invite must not be demoted), which through this door would mean anybody
with push on the repo could claim the name `berna` and hang their own key off
the OWNER — membership of a repo is not permission to become somebody. Through
this door enrolment only ever creates a NEW principal.

**No new row in `core/scope.py`, on purpose.** A server operation is a rule
about what a ROLE may do, and the caller here holds no role — the same as at
`invite/redeem`, whose authorisation is the invite it burns rather than a
principal it does not have yet. GitHub's yes is that proof, and the effect is
the one `key.add` already describes, so a `join.github` operation would be a
second credential type standing where a role belongs. What the caller BECOMES
is `member`, through the ordinary table, on the ordinary `/login`. Nor is this
the banned anonymous write: nothing here is anonymous — a specific account with
a specific access level on a named repo caused it, which is more than an invite
proves.

One forge today (`core/forge.py::FORGES`). A second one is a sibling module
chosen by the declared `host`, never a branch in here: the vocabulary is
already shared and the shapes of "ask, then enrol" would not be.
"""

from __future__ import annotations

from typing import Any

from . import login
from .. import _wire
from ..core import scope
from .._json import as_object
from .._errors import Refused, BadRequest
from ..store.stores import Stores
from ..verbs.project import forge

API = "https://api.github.com"
"""GitHub's API root. A module constant so a test can point this door at a
stub over a real socket — mocking `_wire.get` instead would test neither
urllib nor the header the token travels in."""

TIMEOUT = 10.0

BODY = (
    'POST {"github_token": "<a token that can read the repo>", '
    '"principal": "<your name on this host>", "pubkey": "<~/.ssh/id_ed25519.pub>"}'
)

NO_FORGE = (
    "this board is opened by invite, not by GitHub — its owner opts in by naming the "
    "repo whose membership counts: taskops board forge <owner>/<name> --need push"
)


def answer(host: login.Host, stores: Stores, body: dict[str, Any], now: float) -> dict[str, Any]:
    """Verify membership, enrol the key, hand back who you now are.

    The order is the design: the board's own declaration is read FIRST, so a
    board that never opted in refuses before anything leaves this host — no
    forge, no outgoing call, and the caller's token spent on nobody.
    """
    declared = forge(stores)
    if declared is None:
        raise Refused(NO_FORGE)
    who = str(body.get("principal", "")).strip()
    keyline = str(body.get("pubkey", "")).strip()
    token = str(body.get("github_token", "")).strip()
    if not who or not keyline or not token:
        raise BadRequest(BODY)
    if host.store().principal(who) is not None:
        raise Refused(
            f"this host already has a principal named {who!r}, and GitHub membership does "
            f"not extend it — pick a name nobody holds, or its owner adds your key: "
            f"taskops server key add {who} --key <path.pub>"
        )
    allows(declared["repo"], declared["need"], token)
    name = login.register(host, who, keyline, now)
    key = host.store().keys(name)[0]
    return {
        "principal": name,
        "actor": f"dev:{name}",
        "role": scope.ROLE_MEMBER,
        "fingerprint": key.fingerprint,
        "repo": declared["repo"],
        "need": declared["need"],
    }


def allows(repo: str, need: str, token: str) -> None:
    """ONE call to GitHub, and the token exists nowhere but its header.

    `GET /repos/{owner}/{name}` answers `permissions` FOR THE AUTHENTICATED
    USER, which is why one request settles the question and why the rate budget
    spent is the caller's own (5000/h authenticated, against 60/h anonymous).
    Returns nothing: membership is an absence of refusal, so a caller cannot
    accidentally treat a falsy answer as a grant.
    """
    status, seen = _wire.get(f"{API}/repos/{repo}", headers(token), TIMEOUT)
    if status == 200 and as_object(seen.get("permissions")).get(need) is True:
        return
    raise Refused(_why(status, repo, need))


def headers(token: str) -> dict[str, str]:
    """The token's whole life. `X-GitHub-Api-Version` is pinned because
    `permissions` is the field this door reads and an unpinned API is free to
    reshape it — a silently missing key would read as "no access"."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "taskops",
    }


def _why(status: int, repo: str, need: str) -> str:
    """The refusal, and never the token in it. Each one names what would work."""
    opens = f"this board opens to whoever has {need} on {repo}"
    if status == 401:
        return (
            f"GitHub rejected that token (401) — it is expired, revoked or mistyped. "
            f"{opens}, so the token only has to be able to read that repo. "
            "It is used for this one call and stored nowhere."
        )
    if status == 403:
        return (
            f"GitHub refused that token (403) — an organisation that enforces SSO has to "
            f"authorise it, and a rate limit answers the same way. {opens}"
        )
    if status == 404:
        return (
            f"GitHub has no repository {repo!r} that this token can see — which is also "
            f"what a private repo answers a token without access to it. {opens}"
        )
    if status == 200:
        return (
            f"that token can read {repo} but does not have {need} on it — {opens}. "
            f"An admin of {repo} grants it; a key already registered here signs in without"
            " GitHub at all."
        )
    return f"GitHub answered HTTP {status} asking about {repo} — nothing was granted. {opens}"
