"""Which chapter a CARD is in — a different question from what the chapters are.

`milestone.py` folds the chapters out of the log. This answers the one thing every surface then
asks about a card, and it is separate because the module budget said so: the fold is about the
board's chapters, this is about one card's place among them, and the two grew apart the moment a
board that predated chapters had to be read at all.

**A card with no chapter is not a state this should carry.** The model's first sentence is that
every card belongs to exactly one milestone; `plan` and `capture` refuse to create one without.
What is left is history — cards written before chapters existed — and for most boards that is not
ambiguous at all.
"""

from __future__ import annotations

from ..contracts import Task
from .milestone import milestones
from .store import Store

__all__ = ["sole", "chapter_of"]


def sole(store: Store) -> str:
    """The chapter every card belongs to when this board has ever had exactly ONE. Else `""`.

    A card written before chapters existed carries no milestone, and `engine.replay` leaves it that
    way on purpose: attaching it to whichever chapter happens to be OPEN on this clone would invent
    a fact about the past and differ from one machine to the next.

    That argument is about a CHOICE. With one chapter in the board's whole life there is none —
    every clone folds the same log to the same id, so nothing is invented and the card can be
    resolved instead of carried as an exception for ever. Which matters because the model's first
    sentence is that every card belongs to exactly one milestone, and a permanent bucket for the
    ones that do not is that sentence being false on every board that existed before 0.5.0.

    Several chapters answers `""` deliberately: there, guessing IS inventing, so those cards stay
    loose and every surface says so — the honest answer to a question the record cannot settle.
    """
    every = milestones(store)
    return every[0]["id"] if len(every) == 1 else ""


def chapter_of(task: Task, only: str) -> str:
    """Which chapter a card is in, resolving a legacy one against `sole`.

    One function because three readers ask — the board payload, the counts and a worker's slice —
    and three copies of `task["milestone"] or only` is how two of them end up disagreeing about
    which chapter a card is in. Deliberately NOT used by `_snapshot`: that reproduces the card's
    own event on another machine, so it has to say what the event says.
    """
    return task["milestone"] or only
