"""`taskops land <id>` — the RETRY, by card id.

Split from `land` on its budget, and the seam is real: that module is git and knows nothing
about cards; this one turns a card id into the branch git needs. Closing already lands once —
this exists for the case that matters, which is after a `taskops-fixer` resolved a conflict and
somebody has to say "now".
"""

from __future__ import annotations

from pathlib import Path

from ..engine import branch_for
from ._project import locate
from .ask import ask
from .land import Landing, land

__all__ = ["land_task"]


def land_task(start: Path | str, task_id: str) -> tuple[str, Landing]:
    """The card, and what happened when its branch met the trunk."""
    card = ask(start, task_id)["task"]
    return card["id"], land(locate(start), branch_for(card))
