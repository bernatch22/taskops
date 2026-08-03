"""The standing context over HTTP: what the PROJECT has decided, and what one CARD is handed.

Its own module rather than two more rows in `api`, and the reason is the second endpoint: a slice
is not a smaller overview. The overview answers "what has this project already decided" and is
read once for the whole board; a slice answers the same question about ONE card, with the card's
holder and its subject deciding what survives the filter. Two readers, two shapes, one concept —
so they live together and away from the board endpoints.

Same pattern as every endpoint here: a use case call, a serialisation, and nothing else.
"""

from __future__ import annotations

from pathlib import Path

from ...usecases._contextviews import context_for
from ...usecases._contextviews import show as context_show
from ...usecases.policy import show as policy_show
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["get_context", "get_task_context"]


def get_context(root: Path, request: Request) -> Reply:
    """The standing facts and the settings, in ONE call.

    Together because they are one question on screen — "what has this project already decided" —
    and two calls would be two spinners for a panel the UI keeps open all the time. They stay two
    concepts in the payload: `decisions` is prose a person weighs, `policies` are values the
    engine obeys, and the panel says which is which.
    """
    return guarded(lambda: json_reply({**context_show(root), "policies": policy_show(root)}))


def get_task_context(root: Path, request: Request) -> Reply:
    """The slice ONE card gets — exactly what a worker is injected with when it claims it.

    Exactly that, and it is the point: a person reading a card must see what the agent on it is
    working under, not a differently-filtered approximation of it. So this is `context_for`
    verbatim, the same call the MCP tool and `SessionStart` make.

    No policies here, unlike the overview. A policy is a project-wide setting the engine obeys —
    it is not narrowed by a card, so repeating it on every card would be a per-card copy of a
    fact that does not vary per card.
    """
    task_id = request.param("id")
    if not task_id:
        return error_reply(400, "?id=<task> is required", "bad_request")
    return guarded(lambda: json_reply(context_for(root, task_id)))
