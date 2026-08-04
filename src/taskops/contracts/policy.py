"""A project's standing POLICY — the settings the engine reads, not the prose a worker reads.

This is the half that `context` should never have carried. A decision is free text written for
a model to weigh; a policy is a value the engine acts on, and the two want opposite things: a
decision must accept any sentence, a policy must refuse a typo. Holding one inside the other
gave the worst of both — `reviewer: tsetr` parsed to nothing and every card came out with no
reviewer, silently, which is the exact failure a validated field cannot have.

Same shape as context, and for the same reasons: it is an EVENT, so it replicates through
`git pull`, is content-hashed against double import, and keeps its history. Nothing here is a
config file — `.taskops/events.jsonl` is the only truth, and a value the log cannot reproduce
is a value a clone would disagree about.
"""

from __future__ import annotations

from typing import Literal, TypedDict, get_args

from .context import CONTEXT_TASK

__all__ = ["Name", "NAMES", "Policy", "POLICY_KIND", "POLICY_TASK"]

Name = Literal["reviewer", "day_zone"]
"""The settings that exist. The Literal is the point: a name this version does not know is
refused at the door instead of stored as a setting nothing will ever read.

`day_zone` is where a project's DAY starts — the IANA zone every dossier's midnight is cut at.
A setting rather than a constant because it is a fact about a TEAM: one machine has no
disagreement to settle, and a board rendered from two machines three hours apart has nothing
else that can settle it. Empty means each machine uses its own, which is what every project had
before this existed."""

NAMES: tuple[Name, ...] = get_args(Name)
"""Derived, never retyped — the same rule `EVENT_KINDS` and `SORTS` keep. A second hand-written
list is how a name becomes legal to the type checker and unknown to the validator."""

POLICY_KIND = "policy"
"""One kind for every setting, with the name in the body. Three settings must not become three
event kinds: a reader that cares which one it is already reads the body for the value."""

POLICY_TASK = CONTEXT_TASK
"""The same `project` sentinel context files under, imported rather than respelled.

An `Event` must name a task, and a policy is about the project. Two literals for one sentinel
is how one of them gets fixed and the other does not.
"""


class Policy(TypedDict):
    """One setting in force, as the projection reconstructs it from its event."""

    name: Name
    value: str
    """Validated when it was written, so a reader never has to ask whether it means anything."""

    actor: str
    ts: float
