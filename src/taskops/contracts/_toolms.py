"""`taskops_milestone`'s parameters — the chapter, and the one verb an agent may not finish.

Its own module for the same reason `_toolctx` is: a tool whose shape carries an argument, and the
argument here is about WHO. `create`, `start`, `update` and `review` are an agent's job — planning
one, beginning it, working under it and reporting it finished. `done`, `reject` and `cancel` are
refused to an `agent:` actor by `engine.milestones`, because `done` on a card already requires
somebody who is not its author and this is that rule one level up: no count of closed cards can
mean "we shipped it".

**A bare call answers with EVERY active chapter.** Several are active on any real board, and the
orchestrator is the one reader that chooses between them — it plans into one and dispatches from
one, and it cannot do either blind. `milestone=<id>` answers with that chapter's facts AND its
cards, which is what makes "how do I reach its cards" one call rather than two.
"""

from __future__ import annotations

from typing import Annotated

from . import _factfields as g
from . import _fields as f
from .tools import Target

__all__ = ["MilestoneParams"]


class MilestoneParams(Target, total=False):
    """Read the chapters, or move one. Every field costs every connected agent context on every
    call, so this holds what an agent acts on and nothing a person would only ever type."""

    milestone: Annotated[str, g.MS_READ]
    actor: f.Actor

    create: Annotated[str, g.MS_CREATE]
    goal: Annotated[str, g.MS_GOAL]
    horizon: Annotated[str, g.MS_HORIZON]
    planned: Annotated[bool, g.MS_PLANNED]

    start: Annotated[str, g.MS_START]
    update: Annotated[str, g.MS_UPDATE]
    title: Annotated[str, g.MS_TITLE]

    review: Annotated[str, g.MS_REVIEW]
    done: Annotated[str, g.MS_DONE]
    reject: Annotated[str, g.MS_REJECT]
    cancel: Annotated[str, g.MS_CANCEL]
    m: Annotated[str, g.MS_NOTE]

    carry: Annotated[str, g.MS_CARRY]
    into: Annotated[str, g.MS_INTO]
