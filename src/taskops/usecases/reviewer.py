"""Who may close a card — reading the name, and the project's default for it.

**The answer lives ON THE CARD**, written when the card is created and printed by
`taskops tasks show`. That is the field the engine reads at close time, and changing your mind
is `taskops tasks edit <id> --reviewer <who>` — which is also how you take over a card somebody
else planned on a shared board.

What a card gets when nobody said is a project SETTING, and it has its own verb:

    taskops policy reviewer peer

It used to be a `reviewer:` prefix parsed out of a free-text `context decision`, and every
complaint about that was right. A decision is prose written for a model to weigh, so it cannot
refuse anything: `reviewer: tsetr` matched no specialist, degraded to "nobody named", and every
card came out unreviewed in silence — indistinguishable from never having stated it. A policy
is a value the engine acts on, so it is validated by `named` below, the same function the
card's own field goes through. One validator, so the two can never disagree.

Read at CREATION and stamped, never resolved at close time — see `usecases.policy`.

**A bare name must be registered, a prefixed id must not** — the same split the assign
endpoint already makes, and for the same reason: `reviewer: tsetr` is a card nothing can ever
close and nothing on the board says why, while `dev:ana` addresses a person who was never
going to be in a registry.
"""

from __future__ import annotations

from .._errors import BadRequest
from .._types import HUMAN, PEER
from ..storage import Store
from ..storage.policy import in_force
from .agents import registry

__all__ = ["named", "for_new"]


def named(store: Store, value: str) -> str:
    """Validate one reviewer as written, or refuse it naming the specialists this project has.

    "" is legal and means "nobody named" — that is how `tasks edit` clears a reviewer, and it
    is what every card written before this existed already says.

    `none` and `nobody` normalise to it. They exist because "" is what somebody has to type on
    a command line to mean "no reviewer", and `--reviewer ""` reads as a mistake next to
    `--reviewer none`.
    """
    wanted = value.strip()
    if wanted.lower() in ("none", "nobody"):
        return ""
    if not wanted or wanted in (HUMAN, PEER):
        return wanted
    if ":" in wanted:
        # A person or an ad-hoc worker. Left free-form on purpose, exactly as assignment
        # leaves it: the claim fence treats an actor it does not know as unrestricted too.
        return wanted
    known = [spec["name"] for spec in registry(store.root)]
    if wanted not in known:
        raise BadRequest(
            f"`{wanted}` is not a specialist this project registered — it knows "
            f"{', '.join(known) or 'none'}. For a person, use `human`, `dev:<name>` or "
            f"`agent:<dev>/<name>`; for \"anybody but the author\", `peer`.")
    return wanted


def for_new(store: Store, value: str | None) -> str:
    """The reviewer a card is created with: what was ASKED FOR, else the project's policy.

    `None` means the field was absent and the policy applies; anything else — including "" —
    was stated and is honoured. That distinction is the whole point: with a project-wide
    `reviewer: human`, a card that could not say "nobody" would have no way to be a text fix,
    and an empty string was indistinguishable from an omission.

    The policy was validated when it was set, so it needs no second check here. Re-validating
    would also be wrong: a specialist deleted from `.claude/agents/` after the policy was set
    would start failing every `plan` call, and taking the board down is never the right answer
    to a stale setting.
    """
    return in_force(store, "reviewer") if value is None else named(store, value)
