"""SERVER-scope roles — who may operate the HOST, beside `actors.py`'s roles.

Two different questions, and v1 conflated them into one token check. `actors.py`
answers *what may you do on a board* (`dev:` plans, `agent:` works);
this file answers *what may you do to the server itself* — create a board, list
them, register a key, mint an invite. A board credential says nothing about
that, which is exactly why every admin act used to fall out of `taskops` and
into ssh.

Three roles and no fourth:

    owner    the principal that bootstrapped this host — everything
    member   a registered key that is not the owner
    anon     no credential at all — reads a PUBLIC board, writes nothing

GitHub's model, deliberately: anonymous read, keyed write, no third state. The
registry below is `verbs/__init__.py`'s shape at the server scope — the roles
allowed and the refusal declared ONCE per operation, so a rule cannot be
re-taken differently at a second call site, and every refusal names the role
that may and the way a key gets registered.
"""

from __future__ import annotations

from typing import NamedTuple

from .._errors import Refused

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"
ROLE_ANON = "anon"

SERVER_ROLES = (ROLE_OWNER, ROLE_MEMBER, ROLE_ANON)

OWNER = frozenset({ROLE_OWNER})
KEYED = frozenset({ROLE_OWNER, ROLE_MEMBER})
ANYONE = frozenset(SERVER_ROLES)

ENROL = "a key is registered by the server owner: taskops server key add <name> --key <path.pub>"


class Operation(NamedTuple):
    roles: frozenset[str]
    refusal: str  # names the role that may — and, for anon, how a key is registered


OPERATIONS: dict[str, Operation] = {
    "board.create": Operation(
        OWNER,
        "creating a board is the server OWNER's move, and only the owner's",
    ),
    "board.list": Operation(
        KEYED,
        f"listing this host's boards needs a registered key (owner or member) — {ENROL}",
    ),
    "board.read": Operation(ANYONE, ""),
    "board.write": Operation(
        KEYED,
        f"writing to a board needs a registered key (owner or member) — {ENROL}",
    ),
    "session.mint": Operation(
        KEYED,
        f"signing in needs a key this host knows (owner or member) — {ENROL}",
    ),
    "key.add": Operation(
        OWNER,
        "registering a key is the server OWNER's move",
    ),
    "key.revoke": Operation(
        OWNER,
        "revoking a key is the server OWNER's move",
    ),
    "invite.mint": Operation(
        OWNER,
        "minting an invite is the server OWNER's move",
    ),
    "invite.revoke": Operation(
        OWNER,
        "revoking an invite is the server OWNER's move",
    ),
}


def permit(operation: str, role: str) -> None:
    """Refuse unless this server-role may run this operation. The ONE gate.

    An unknown operation is a programming error, not a user's — it refuses with
    the list, the same way `verbs.call` does for an unknown verb.
    """
    spec = OPERATIONS.get(operation)
    if spec is None:
        known = ", ".join(sorted(OPERATIONS))
        raise Refused(f"unknown server operation {operation!r} — this host knows: {known}")
    if role not in spec.roles:
        may = " or ".join(sorted(spec.roles))
        raise Refused(f"{role} may not {operation} — {may} may. {spec.refusal}")


def may(operation: str, role: str) -> bool:
    spec = OPERATIONS.get(operation)
    return spec is not None and role in spec.roles
