"""The policy verbs: set a project setting, read the ones in force.

**Validated at the door, which is the whole reason this exists.** The setting it replaces was a
`reviewer:` prefix inside a free-text decision, and a decision cannot refuse anything — so a
misspelt specialist degraded to "nobody named" and every card came out unreviewed, in silence,
indistinguishable from never having stated it. Here the name is a `Literal` and the value goes
through the same validator the card's own field uses, so the two can never disagree.

One validator per setting, looked up rather than branched on: a second setting is a row in
`_VALIDATORS` and a member of `Name`, not another `if` in this module.

Read at CREATION and stamped onto the card, never resolved at close time. Resolving it late
would make a policy changed today rewrite who was allowed to close work planned last week, and
the card could no longer say who its reviewer is — which is the whole ask.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, cast

from .._errors import BadRequest
from .._types import EventKind
from ..contracts.policy import NAMES, POLICY_KIND, POLICY_TASK, Policy
from ..engine import record
from ..storage import Store
from ..storage.policy import policies
from ._project import caller, heartbeat, project
from ._routing import call_remote, read_remote_first, whoami
from .dayzone import named as _day_zone
from .reviewer import named as _reviewer

__all__ = ["set_policy", "show", "refuse_if_policy"]

_KIND = cast("EventKind", POLICY_KIND)
"""`EventKind` is a Literal in layer 0 and this module may not widen it — the cast names the one
place this kind enters the log."""

_VALIDATORS: dict[str, Callable[[Store, str], str]] = {"reviewer": _reviewer,
                                                       "day_zone": _day_zone}
"""What each setting accepts. A name with no validator is a name nothing checks, so the lookup
is also the registration: `NAMES` and this table are asserted to agree in the tests."""


def set_policy(start: Path | str, name: str, value: str, *, actor: str = "") -> Policy:
    """State one setting, or refuse it saying what the legal values are.

    Setting it back is stating the new value; "" means "no default", which is what a project has
    before anybody sets one. There is no retire, because a setting has no history worth keeping
    in force — the log already has every value it ever held.
    """
    if name not in NAMES:
        raise BadRequest(f"`{name}` is not a policy — this taskops knows {', '.join(NAMES)}")
    if (answer := call_remote(start, "policy_set", {"name": name, "value": value,
                                                    "actor": whoami(start, actor)})) is not None:
        return cast("Policy", answer)
    with project(start) as store:
        checked = _VALIDATORS[name](store, value)
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        body: dict[str, Any] = {"name": name, "value": checked}
        event = record(store, task=POLICY_TASK, actor=who, kind=_KIND, body=body)
        return Policy(name=cast("Any", name), value=checked, actor=who, ts=event["ts"])


def refuse_if_policy(text: str) -> None:
    """Refuse a context fact that is trying to be a setting, and name the verb that is one.

    Here rather than in `context` because this module owns what a policy name IS — and because
    simply not reading `reviewer:` out of a decision any more would be silent: the sentence
    still records, still renders, still looks stated, and does nothing. Silence is the exact
    failure this whole move exists to end, so the door refuses instead of the reader ignoring.
    """
    head = text.strip().split(":", 1)[0].strip().lower()
    if head in NAMES:
        raise BadRequest(
            f"`{head}` is a project POLICY, not a decision — a decision is prose nothing "
            f"validates, and this one would record and do nothing. Use "
            f"`taskops policy {head} <value>`.")


def show(start: Path | str) -> list[Policy]:
    """Every setting in force. Empty means the project has decided nothing, which is legal."""
    if (answer := read_remote_first(start, "policy_show", {})) is not None:
        # A LIST inside an object: the wire decoder drops a bare array — see `_verbs`.
        return cast("list[Policy]", answer.get("policies", []))
    with project(start) as store:
        return policies(store)
