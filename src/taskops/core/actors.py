"""The actor grammar: who may speak, and what their names may look like.

Split out of `types.py` along a real seam — *what the rows are* versus *who is
speaking* — when the review feature needed room there (the 200-line budget is
pinned by `tests/test_architecture.py`). `types.py` re-exports everything here,
so every importer keeps working unchanged.

`role_of` is the only actor parser in the codebase. v1 had five identity
resolvers plus an `attributed` inference, and a sub-agent that omitted its
actor silently resolved to the human's id and wandered into the pool.
"""

from __future__ import annotations

from .._errors import BadRequest

SYSTEM = "taskops"  # the actor of events nobody typed

ANON = "anon"
"""NOBODY: a reader of a PUBLIC board who carries no credential.

A whole identity rather than an empty string, and that is the decision: an
actor is threaded through every verb, every lease call and every mention fold,
so "no actor" as `""` would be a hole that each of those has to remember to
check. `anon` is a name with a role, refused by the registry from every write
in ONE place, and the store's `renew` is a no-op for it — so the milestone's
rule (ANONYMOUS NEVER CAUSES A WRITE) is two guards, not thirty.

It is deliberately outside the `<role>:<name>` grammar: no invite, no key and
no `TASKOPS_ACTOR` can ever spell it, so nobody can log in AS anonymous.
"""

ROLE_DEV = "dev"
ROLE_AGENT = "agent"
ROLE_SYSTEM = "system"
ROLE_ANON = "anon"

_NAME_OK = set("abcdefghijklmnopqrstuvwxyz0123456789._-")


def role_of(actor: str) -> str:
    """Derive the role from the actor grammar, or refuse with the way out."""
    if actor == SYSTEM:
        return ROLE_SYSTEM
    if actor == ANON:
        return ROLE_ANON
    head, sep, rest = actor.partition(":")
    if not sep or not rest:
        raise BadRequest(
            f"actor {actor!r} is not an identity. Use dev:<name> for the orchestrator "
            "or agent:<dev>/<name> for a worker (export TASKOPS_ACTOR=agent:<dev>/<name>)."
        )
    if head == ROLE_DEV:
        _check_name(rest, actor)
        return ROLE_DEV
    if head == ROLE_AGENT:
        owner, slash, name = rest.partition("/")
        if not slash:
            raise BadRequest(f"actor {actor!r} needs an owner: agent:<dev>/<name>")
        _check_name(owner, actor)
        _check_name(name, actor)
        return ROLE_AGENT
    raise BadRequest(f"actor {actor!r}: unknown role {head!r} — use dev: or agent:")


def _check_name(name: str, actor: str) -> None:
    if not name or len(name) > 40 or not set(name) <= _NAME_OK:
        raise BadRequest(f"actor {actor!r}: {name!r} must be 1-40 chars of [a-z0-9._-]")


def slugify(title: str) -> str:
    """Milestone branch slug. Called ONCE, at creation; the result is stored."""
    out = [c if c in _NAME_OK and c not in "._" else "-" for c in title.lower()]
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:32] or "milestone"
