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

from . import card, plan, take, pulse, assign, record, report, review, update, _mentions
from .._errors import Refused, BadRequest
from ..core.types import ROLE_DEV, ROLE_AGENT, role_of
from ..store.stores import Stores

Args = dict[str, Any]
Run = Callable[[Stores, str, Args], dict[str, Any]]

DEV = frozenset({ROLE_DEV})
AGENT = frozenset({ROLE_AGENT})
BOTH = frozenset({ROLE_DEV, ROLE_AGENT})


class Verb(NamedTuple):
    fn: Run
    kind: Literal["read", "write"]
    roles: frozenset[str]
    refusal: str  # what to tell the wrong role — always names the call that works


REGISTRY: dict[str, Verb] = {
    "board": Verb(pulse.run, "read", BOTH, ""),
    # The ✉ half of `board` alone, and the only read that does NOT renew: the
    # delivery hook calls it on somebody else's behalf (MENTIONS.md §9a).
    "mentions": Verb(_mentions.mentions, "read", BOTH, ""),
    "card": Verb(card.run, "read", BOTH, ""),
    "report": Verb(report.run, "read", BOTH, ""),
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
}


def call(stores: Stores, verb: str, actor: str, args: Args) -> dict[str, Any]:
    """The single door into the model. Both boards and the HTTP router use it."""
    spec = REGISTRY.get(verb)
    if spec is None:
        known = ", ".join(sorted(REGISTRY))
        raise BadRequest(f"unknown verb {verb!r} — this board answers: {known}")
    role = role_of(actor)
    if role not in spec.roles:
        raise Refused(f"{actor} may not {verb}: {spec.refusal}")
    return spec.fn(stores, actor, args)


def writes(verb: str) -> bool:
    spec = REGISTRY.get(verb)
    return spec is not None and spec.kind == "write"
