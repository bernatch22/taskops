"""The verb registry — read/write and role declared ONCE, in one table.

Everything downstream reads this table: the HTTP router, the local board, the
MCP tools, the tests. In v1 the same routing decision was re-taken by hand at
25 call sites and four of them took it differently, which is where
`context_of`, `landed`, `fleet` and `activity` each broke in their own way.

Three classes of bug become unrepresentable:

* a verb outside the registry cannot be called;
* a `write` cannot silently degrade to a local store;
* a role that may not run a verb is refused in one place, with the way out.
"""

from __future__ import annotations

from typing import Any, Literal, Callable, NamedTuple

from . import (
    card,
    plan,
    take,
    filed,
    pulse,
    assign,
    events,
    record,
    report,
    review,
    update,
    project,
    _waiting,
    activity,
    _mentions,
)
from .._errors import Refused, BadRequest
from ..core.scope import ENROL
from ..core.types import ROLE_DEV, ROLE_ANON, ROLE_AGENT, role_of
from ..store.stores import Stores

Args = dict[str, Any]
Run = Callable[[Stores, str, Args], dict[str, Any]]

DEV = frozenset({ROLE_DEV})
AGENT = frozenset({ROLE_AGENT})
BOTH = frozenset({ROLE_DEV, ROLE_AGENT})

WATCHERS = frozenset({ROLE_DEV, ROLE_AGENT, ROLE_ANON})
"""BOTH plus nobody: a read that a PUBLIC board answers with no credential.

GitHub's model, exactly — anonymous read, keyed write, no third state. The set
is on the READ verbs only, so "may anon do this" is answered by the same table
that answers "may a worker plan", and there is no second place to say no.

`waiting` deliberately keeps `DEV`: it is the orchestrator's three groups, not
a wider read. `mentions` carries this set and is EMPTY for anon by
construction — a comment can only name an actor somebody registered, and `anon`
is outside the actor grammar (`core/actors.py::ANON`), so nothing can address it.
"""

NO_KEY = (
    "anonymous may read this board and nothing else — writing needs a registered key. "
    f"Ask the board's owner for an invite (`taskops invite <you> --board <name>`) and join "
    f"with it: taskops join <url>?invite=… --key ~/.ssh/id_ed25519. {ENROL}"
)
"""The refusal an unkeyed writer gets, and it names the way IN — the house rule,
extended to the one caller that has no identity to be told about."""


class Verb(NamedTuple):
    fn: Run
    kind: Literal["read", "write"]
    roles: frozenset[str]
    refusal: str  # what to tell the wrong role — always names the call that works


REGISTRY: dict[str, Verb] = {
    "board": Verb(pulse.run, "read", WATCHERS, ""),
    # The ✉ half of `board` alone, and the only read that does NOT renew: the
    # delivery hook calls it on somebody else's behalf.
    "mentions": Verb(_mentions.mentions, "read", WATCHERS, ""),
    # The orchestrator's three groups of `board`, and the OTHER read that does
    # not renew — same delivery hook, same reason (`verbs/_waiting.py`). DEV
    # only, because merging, verifying and re-dispatching are the dev's moves.
    "waiting": Verb(
        _waiting.waiting,
        "read",
        DEV,
        "these are the orchestrator's moves, not yours. Your own picture: taskops_board",
    ),
    "card": Verb(card.run, "read", WATCHERS, ""),
    # `card` for a whole chapter, in one read: the same facts per card, minus
    # the two long ones unless depth=full asks for them (`verbs/activity.py`).
    "activity": Verb(activity.run, "read", WATCHERS, ""),
    "report": Verb(report.run, "read", WATCHERS, ""),
    # The LOG, paged — the one read that answers "what happened" rather than
    # "what is each card". Board-wide by construction (verbs/events.py).
    "events": Verb(events.run, "read", WATCHERS, ""),
    "plan": Verb(
        plan.run,
        "write",
        DEV,
        "workers do not plan the board. Report what you found instead: "
        'taskops_comment task=<yours> text="…"',
    ),
    "assign": Verb(
        assign.run,
        "write",
        DEV,
        "dispatching is the orchestrator's move. Take what is yours: taskops_take",
    ),
    "merged": Verb(
        record.merged,
        "write",
        DEV,
        "workers do not integrate branches. Close your card and the orchestrator merges it: "
        'taskops_update task=<yours> status=done note="…"',
    ),
    "take": Verb(
        take.run,
        "write",
        AGENT,
        "you are the orchestrator — you dispatch, you do not hold cards: "
        "taskops_assign tasks=[<id>] and spawn the worker with the brief it returns. "
        "If you ARE that spawned worker: sub-agents share this MCP server and its identity, "
        "so pass actor=agent:<dev>/<name> (your brief names it) on EVERY taskops call",
    ),
    "update": Verb(update.run, "write", BOTH, ""),
    # Optional review: claim a submitted card to read it, or record the verdict.
    # BOTH roles — a verifier is an ordinary agent; there is no reviewer ROLE.
    "review": Verb(review.run, "write", BOTH, ""),
    "bind": Verb(record.bind, "write", BOTH, ""),
    # A fact about the repo itself, written by init/join — the only side that
    # has a clone. BOTH roles: whoever ran the command owns the checkout.
    "project": Verb(project.run, "write", BOTH, ""),
    # A committed report is put on a chapter, by reference (`verbs/filed.py`).
    # BOTH roles and no owner check: a chapter is not a card, so there is
    # nobody holding it to be the one allowed to narrate it — and the read half
    # (`core/reports.py::of`) is open to anyone the board is open to.
    "filed": Verb(filed.run, "write", BOTH, ""),
}


def call(stores: Stores, verb: str, actor: str, args: Args) -> dict[str, Any]:
    """The single door into the model. Both boards and the HTTP router use it."""
    spec = REGISTRY.get(verb)
    if spec is None:
        known = ", ".join(sorted(REGISTRY))
        raise BadRequest(f"unknown verb {verb!r} — this board answers: {known}")
    role = role_of(actor)
    if role not in spec.roles:
        # ANON is refused in its OWN words: half the write verbs carry an empty
        # `refusal` because a dev and an agent both may run them, so the generic
        # sentence would end in a colon and say nothing at all — and the one
        # reader who most needs to be told the way in is the one with no
        # identity yet. `waiting` (a read anon may not run) keeps its own.
        unkeyed = role == ROLE_ANON and spec.kind == "write"
        raise Refused(f"{actor} may not {verb}: {NO_KEY if unkeyed else spec.refusal}")
    return spec.fn(stores, actor, args)


def writes(verb: str) -> bool:
    spec = REGISTRY.get(verb)
    return spec is not None and spec.kind == "write"
