"""Who is calling — resolved once, from the least surprising source available.

An agent rarely knows its own name, and asking it to invent one produces a fleet of
actors called `agent:claude/agent`. So the resolution order goes from most explicit
to most inferable, and every step is something a human configured on purpose:

1. what the caller passed (a fleet launcher naming its workers)
2. `$TASKOPS_ACTOR` (the plugin exports it per session)
3. the git identity, turned into `dev:<local-part>`

The last one is why a developer who never configures anything still gets attributed
work rather than an `unknown`. It is also why `git config user.email` being wrong
shows up here: the actor on the board is the identity the commits will carry.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .._errors import BadRequest
from ..contracts import Actor

__all__ = ["parse", "resolve", "ENV_ACTOR", "ENV_SESSION"]

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
    """The caller's identity: what it said, else the environment, else git."""
    for candidate in (asked, os.environ.get(ENV_ACTOR, "")):
        if candidate.strip():
            return parse(candidate)
    return parse(_from_git(root))


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
