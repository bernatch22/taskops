"""The one thing `status` needs from the context layer: the objective, as a line of text.

A separate module for two lines, and not a cheap import inside `status.py`, because the code
budget is the invariant that keeps that file about ONE question. `status` is the screen every
other feature wants a row on; without a hard line somewhere it becomes the module that knows
about everything, which is exactly what a status command turns into if nobody stops it.

Returning `""` rather than raising when no objective was ever stated is the contract the
renderer already expects: a project that has not written down what it is chasing renders no
row at all, never an error and never a placeholder telling somebody off for it.
"""

from __future__ import annotations

from ..storage import Store
from ..storage.context import facts
from ._contextslice import winner

__all__ = ["objective_of"]


def objective_of(store: Store) -> str:
    """The objective in force, or empty. Same `(ts, id)` winner the context layer elects, by
    calling it rather than restating it — two places deciding which objective is current is
    two answers the day a tie happens."""
    current = winner([fact for fact in facts(store) if fact["sort"] == "objective"])
    return current["text"] if current else ""
