"""`taskops land <id>` — the RETRY, by card id.

Split from `land` on its budget, and the seam is real: that module is git and knows nothing
about cards; this one turns a card id into the branch git needs. Closing already lands once —
this exists for the case that matters, which is after a worker resolved a conflict and
somebody has to say "now".
"""

from __future__ import annotations

from pathlib import Path

from ..engine import branch_for
from ._project import locate
from .ask import ask
from .land import Landing, land

__all__ = ["land_task"]


def land_task(start: Path | str, task_id: str, *, push: bool = True) -> tuple[str, Landing]:
    """The card, and what happened when its branch met the trunk.

    The card's COMMITS travel with the guessed name, because this is the retry — the path a person
    reaches after the automatic landing failed, and the one where a name computed by a different
    clone is most likely to be why. `ask` already read the card's thread, so the shas cost nothing.
    """
    view = ask(start, task_id)
    card = view["task"]
    shas = tuple(commit["sha"] for commit in view["commits"] if commit["sha"])
    return card["id"], land(locate(start), branch_for(card), shas=shas, push=push)
