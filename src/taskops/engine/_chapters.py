"""What a refused milestone move SAYS. Split from `milestones.py` because it is a second thing.

The machine decides; this decides the sentence, and the sentence is not decoration. Every refusal
this repository ever wrote that said only "no" cost a session: the useful one is not "no" but
"this one is Ana's", so each text below names the actor, the reason and the exact next command.

Text and not logic, so it lives beside the table rather than inside it — and the module budget
saying `milestones.py` would not fit was the invariant pointing at exactly this seam.
"""

from __future__ import annotations

from ..contracts.milestone import MilestoneState

__all__ = ["illegal", "needs_a_person", "needs_findings"]


def _named(milestone: str) -> str:
    """The subject of the sentence. A refusal about an unnamed chapter is a refusal a caller
    cannot act on, and the id is what every way out below takes as its argument."""
    return f"milestone {milestone}" if milestone else "this milestone"


def illegal(milestone: str, state: MilestoneState, to: MilestoneState,
            allowed: tuple[MilestoneState, ...]) -> str:
    """The arrow does not exist. Name the state it is IN and every state it may reach.

    Without the second half the caller guesses at the next arrow and gets refused again — the
    card machine learned this the same way, and its message has listed the legal targets since.
    """
    where = ", ".join(allowed) if allowed else "nowhere — it is closed"
    return (f"{_named(milestone)} is {state}, so it cannot become {to}. From {state} it may "
            f"only go to: {where}.")


def needs_a_person(actor: str, verb: str, milestone: str) -> str:
    """An agent tried to verify, send back or abandon a chapter.

    The way out is the whole message. An agent told only that it may not close falls into
    explaining that it cannot — watched live on a card, for four turns — so this names the verb
    it CAN use, who does the closing, and that nothing happens on its word.
    """
    # The verb is quoted as the COMMAND it is: "may not done milestone x" is not a sentence, and
    # the three words this takes (`done`, `reject`, `cancel`) are argument spellings, not English.
    return (f"{actor} may not `{verb}` {_named(milestone)} — verifying is not reporting, and an "
            f"agent that closed the chapter it worked under would be moving the goalposts it is "
            f"judged against. `done` on a card already requires somebody who is not its author; "
            f"this is that rule one level up, because no count of closed cards can mean \"we "
            f"shipped it\". Report it instead: taskops_milestone review={milestone or '<id>'} "
            f"m=\"what is finished and what shows it\". A person verifies from there, and "
            f"nothing is archived on your word.")


def needs_findings(milestone: str) -> str:
    """A rejection with no reason is a chapter bounced with nothing to act on.

    Whoever reported it reads "not finished", guesses, and reports it again unchanged — which is
    a card going round twice, one level up and with a whole chapter's worth of work behind it.
    """
    return (f"{_named(milestone)} is going back in force with no findings — say what is missing "
            f"(a card still open, a criterion nothing meets, a run that fails). A chapter "
            f"returned with nothing to act on comes back to review unchanged.")
