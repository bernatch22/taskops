"""Who is calling — resolved once, from the least surprising source available.

An agent rarely knows its own name, and asking it to invent one produces a fleet of
actors called `agent:claude/agent`. So the resolution order goes from most explicit
to most inferable, and every step is something a human configured on purpose:

1. what the caller passed (a fleet launcher naming its workers)
2. `$TASKOPS_ACTOR` (exported per session — the only way to be two devs on one machine)
3. `$GITHUB_USER`, then `$USER` — the account, which is who you are on this box
4. the git identity, turned into `dev:<local-part>`

**git moved to LAST, and that is the fix.** It used to come straight after `$TASKOPS_ACTOR`,
and an agent rewrote `git config user.email` on a lab checkout — because the repository's own
CLAUDE.md told it which git identity to use — so an entire developer silently became somebody
else mid-run. Two clones drifting to the same name would deadlock `reviewer: peer`: the only
actor allowed to close a card would be its author. `$USER` is not something an agent edits in
passing, so it belongs above a file that is fair game.

`$TASKOPS_ACTOR` stays ABOVE `$USER` rather than below it, which is the one place this differs
from how it was asked for. Two sessions on one machine share a `$USER`; if the account won,
`dev:uno` and `dev:dos` would both resolve to the same person and peer review would have
nobody to hand a card to. The explicit value is the only thing that can tell them apart, so it
has to be able to.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .._errors import BadRequest
from ..contracts import Actor

__all__ = ["parse", "resolve", "a_person", "ENV_ACTOR", "ENV_SESSION"]

ENV_ACTOR = "TASKOPS_ACTOR"
ENV_SESSION = "TASKOPS_SESSION"

_FALLBACK = "dev:unknown"


def parse(actor_id: str) -> Actor:
    """`agent:berna/one` -> its parts. Raises on a shape nothing can attribute.

    Strict rather than lenient, unlike most readers in this package: an actor id is
    a JOIN KEY — it addresses an inbox and appears in every event — so accepting a
    malformed one creates a second identity for the same person that nobody notices
    until half their work is filed under it.
    """
    kind, _, rest = actor_id.strip().partition(":")
    if kind == "dev" and rest and "/" not in rest:
        return Actor(id=f"dev:{rest}", kind="dev", dev=rest)
    if kind == "agent" and "/" in rest:
        dev, _, name = rest.partition("/")
        if dev and name:
            return Actor(id=f"agent:{dev}/{name}", kind="agent", dev=dev)
    raise BadRequest(f"`{actor_id}` is not an actor id — use `dev:<name>` or "
                     f"`agent:<dev>/<name>`")


def resolve(root: Path, asked: str = "") -> Actor:
    """The caller's identity, most explicit source first. See this module's header."""
    for candidate in (asked, os.environ.get(ENV_ACTOR, "")):
        if candidate.strip():
            return parse(candidate)
    for variable in ACCOUNT_VARS:
        if account := _clean(os.environ.get(variable, "")):
            return parse(f"dev:{account}")
    return parse(_from_git(root))


ACCOUNT_VARS = ("GITHUB_USER", "USER", "LOGNAME")
"""The account this session runs as, in preference order. `GITHUB_USER` first because a team
that sets it means it — it is the name their PRs and their board should agree on."""


def _clean(value: str) -> str:
    """An account name reduced to what `parse` accepts, or "" if nothing survives.

    Names are not rejected, they are NORMALISED: `$USER` can hold a dot, a space, a domain
    slash. Refusing those would drop a real identity back to git — the source this reordering
    exists to demote — so it is filed under the closest legal name instead.
    """
    kept = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in value.strip())
    return kept.strip("-").lower()


def _from_git(root: Path) -> str:
    """`dev:<local-part of user.email>`, or a named fallback.

    Falling back rather than raising: a git identity is missing in a fresh
    container and in a repository nobody configured, and refusing to work there
    would make taskops unusable in exactly the throwaway environments agents run
    in. The fallback is VISIBLE on the board, which is the nudge.
    """
    email = _git_config(root, "user.email")
    local = email.partition("@")[0].strip()
    return f"dev:{local}" if local else _FALLBACK


def _git_config(root: Path, key: str) -> str:
    """One git config value, or "" if git is absent, broken or silent.

    Never raises: this is called during identity resolution, which happens on the
    way into every single call. A missing git must degrade, not take the tool down.
    """
    try:
        done = subprocess.run(["git", "config", "--get", key], cwd=root,
                              capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def a_person(root: Path, asked: str, doing: str) -> Actor:
    """Resolve the caller and refuse an AGENT — for the handful of calls that are a human's.

    Here rather than at each call site because it is a rule about an actor id and nothing else,
    and layer 0 already draws the line for exactly this shape: *guards that demand a
    justification accept one from a dev and reject it from an agent.*

    The session that plans resolves to a `dev:` id — `SessionStart` fires for the main
    conversation and never for a sub-agent — so this costs the legitimate caller nothing.
    """
    who = resolve(root, asked)
    if who["kind"] == "agent":
        raise BadRequest(f"{who['id']} may not {doing} — that is a person's call about the "
                         f"project, and a worker that could make it could move the goalposts "
                         f"it is judged against.")
    return who
