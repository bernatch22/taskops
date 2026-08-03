"""`taskops_context`'s parameters — the one tool whose shape carries a security argument.

Its own module because `tools` filled up holding thirteen of these and this is the one that
grew, and because the reasoning below is about a RULE rather than about a field list: the write
half exists here, and what stops a worker using it does not.
"""

from __future__ import annotations

from typing import Annotated, Literal

from . import _fields as f
from .tools import Target

__all__ = ["ContextParams"]


class ContextParams(Target, total=False):
    """Reading the standing facts, and — for the session that PLANS — stating them.

    The write half was left off once, and that protected nothing: a worker holds `Bash`, so
    `taskops context objective …` was always one call away, while the orchestrator — the one
    caller with any business setting an objective — had to shell out for it. The fence is in
    the use case instead, where `Bash` cannot walk around it: an `agent:` actor is refused, a
    `dev:` one is not, which is the line between a worker and the session that planned its work.

    `--horizon`, `--owner` and `--files` stay CLI-only; every field here costs every connected
    agent context on every call. `mine` stands in for the only one a session reaches for —
    nobody types their own id to say "this is mine".
    """

    task: Annotated[str, f.CONTEXT_TASK]
    # WITHOUT this the fence could never fire: a caller that cannot name itself resolves from
    # git config, so every worker would arrive as the developer and state whatever it liked.
    actor: f.Actor
    state: Annotated[Literal["objective", "invariant", "decision", "note"], f.STATE]
    text: Annotated[str, f.TEXT]
    labels: Annotated[str, f.SCOPE]
    mine: Annotated[bool, f.MINE]
    retire: Annotated[str, f.RETIRE]
