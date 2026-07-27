"""What a dispatch returns: the workers that started, and the cards that did not.

Its own module because the reader is in a different situation from every other result — they have
just launched processes they cannot see, so what this owes them is where to look.

The Protocols are here rather than an import of `usecases.dispatch`, because that would point layer 4
at layer 5. An architecture test enforces it, and that is how the first version got caught: a
`TYPE_CHECKING` guard hides an import from the runtime but not from the rule, and the rule is right.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ._text import table

__all__ = ["render_dispatch", "DispatchLike", "Worker"]


class Worker(Protocol):
    """One launched worker, structurally.

    Read-only properties rather than plain attributes: a mutable Protocol attribute is invariant, so
    it would only match a class whose annotations are identical — and `Launched` assigns in
    `__init__`. Rendering never writes to these anyway.
    """

    @property
    def actor(self) -> str: ...
    @property
    def task(self) -> str: ...
    @property
    def pid(self) -> int: ...
    @property
    def branch(self) -> str: ...


class DispatchLike(Protocol):
    # `Sequence` and not `list`: list is INVARIANT, so `list[Launched]` does not satisfy
    # `list[Worker]` even though `Launched` satisfies `Worker`. Sequence is covariant, and a renderer
    # has no business writing to it.
    @property
    def launched(self) -> Sequence[Worker]: ...
    @property
    def skipped(self) -> Sequence[str]: ...


def render_dispatch(result: DispatchLike) -> str:
    """The workers that were launched, and the cards that were not.

    The skipped list is not an afterthought: a dispatch that quietly started three of five would leave
    a planner believing five agents are working, and the two cards nobody started would look assigned
    and never move. It ends with where to look, because a detached process nobody can find is a
    process nobody trusts.
    """
    if not result.launched and not result.skipped:
        return ("nothing to dispatch — no ready, unassigned card. Plan some work, or check "
                "`taskops_report board` for what is blocked")
    rows = [[w.actor, w.task, str(w.pid), w.branch] for w in result.launched]
    parts = [f"# dispatched {len(result.launched)} worker(s)", "",
             table(["worker", "task", "pid", "branch"], rows)]
    if result.skipped:
        parts += ["", f"⚠ NOT started: {', '.join(result.skipped)}",
                  "_Not ready, already assigned, or the process failed to start._"]
    if result.launched:
        parts += ["", "They are detached and running now. Watch them with "
                  "`taskops_report fleet`; their output is in .taskops/workers/."]
    return "\n".join(parts)
