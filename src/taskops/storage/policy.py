"""The policy projection: policy events -> the settings in force.

Folded on every read rather than kept in a table, the same call `storage.context` makes and for
the same reason: the log arrives out of order when two ends of a file are merged by `git pull`,
and a fold over the events cannot be left stale by that while a materialised column can. There
are a handful of these, not thousands.

Last write wins, per name. There is no retire: setting a policy back is stating the new value,
and "" is a legal value meaning "no default" — which is what every project has before anybody
sets one.
"""

from __future__ import annotations

from ..contracts.policy import NAMES, POLICY_KIND, POLICY_TASK, Name, Policy
from .store import Store

__all__ = ["policies", "in_force"]


def policies(store: Store) -> list[Policy]:
    """Every setting in force, one per name, alphabetical.

    Unknown names are skipped rather than raised on: a teammate running a newer taskops will
    write settings this version has never heard of into the shared log, and one of them must
    not make the project unreadable. That is the same contract the event reader keeps.
    """
    latest: dict[str, Policy] = {}
    for event in store.events.of_task(POLICY_TASK, kinds=(POLICY_KIND,)):
        name = str(event["body"].get("name", ""))
        if name not in NAMES:
            continue
        latest[name] = Policy(name=_as_name(name), value=str(event["body"].get("value", "")),
                              actor=event["actor"], ts=event["ts"])
    return [latest[name] for name in sorted(latest)]


def in_force(store: Store, name: str) -> str:
    """One setting's value, or "" when nobody set it.

    "" is deliberately the same answer for never-set and set-to-nothing: a caller asking what a
    card should be created with wants a value, not the history of how it got there.
    """
    return next((p["value"] for p in policies(store) if p["name"] == name), "")


def _as_name(value: str) -> Name:
    return value                                # type: ignore[return-value]
