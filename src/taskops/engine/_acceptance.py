"""The second half of the `done` guard: a card with criteria must say what MET them.

Its own module and not three more lines in `machine`, for the reason every rule here is a
pure function of data: the machine owns the TABLE of who may go where, and a guard that needs
its own vocabulary — criteria, what proves them, the argued exemption — is a rule about
evidence rather than about transitions.

The commit guard next door asks "is there code". This asks "does anybody know what the code
was supposed to do". They are different questions and a card can pass one and fail the other:
a commit bound to a card proves an agent typed, not that the thing the card promised happened.

The exemption is the same shape as `no_code` and exists for the same reason. A criterion can
turn out to be wrong mid-flight, and a rule with no honest way out is a rule that gets
satisfied by a sentence somebody made up — so the way out is explicit, requires a reason, and
that reason is written into the `done` event where a review will read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Evidence", "evidenced"]


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the closing agent offered against what the card promised."""

    criteria: tuple[str, ...] = ()
    """The card's acceptance criteria. Empty is the ordinary case for every card written
    before criteria existed, and it makes this guard a no-op — which is what keeps an old
    board closable."""

    given: str = ""
    """Which criteria were met and what proves it: a test name, a command, a run."""

    waived: str = field(default="")
    """The reason evidence was skipped. Present means the caller passed the escape hatch."""


def evidenced(evidence: Evidence | None) -> str | None:
    """None when this close is honest; otherwise the sentence the stuck agent needs.

    Order matters: evidence beats a waiver, so an agent that offers both is not scolded for
    the waiver it did not need.
    """
    if evidence is None or not evidence.criteria:
        return None
    if evidence.given.strip() or evidence.waived.strip():
        return None
    return (f"this card has {len(evidence.criteria)} acceptance criteria and nothing says "
            f"they were met. Pass `evidence` naming which ones and what proves each — a "
            f"test, a command, a run — or `no_evidence` with the reason they no longer "
            f"apply. First: {evidence.criteria[0][:70]}")
