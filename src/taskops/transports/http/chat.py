"""The two endpoints behind the sidebar: read the conversation, say one thing.

Its own module rather than two more functions in `api.py`, for the reason `assigning.py` is one:
this write has a rule of its own — WHERE a message with no card is filed — and a rule deserves a
docstring where the reader is already looking. `usecases.chat` holds it and the argument for it.

Nothing here notifies anybody. `record()` publishes to the bus, `usecases.follow` tails it and
`/api/live` frames it, so a chat line reaches the open session down the path every other event
already takes — verified by a test rather than assumed, and no parallel notification exists to
drift from it.
"""

from __future__ import annotations

from pathlib import Path

from ...usecases.chat import say, thread
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["get_chat", "post_chat"]


def get_chat(root: Path, request: Request) -> Reply:
    """The thread, oldest first — a chat is read from the bottom."""
    return guarded(lambda: json_reply(thread(root)))


def post_chat(root: Path, request: Request) -> Reply:
    """Say one line. `card` is optional and is CONTEXT: what the board happened to be showing.

    Optional because the whole point of the sidebar is that it opens over anything, including a
    view with no card in it — requiring one would make the feature a per-card reply box again.
    """
    payload = request.payload()
    text = str(payload.get("text", "")).strip()
    if not text:
        return error_reply(400, "`text` is required", "bad_request")
    card = str(payload.get("card", ""))
    # `source` is read from the request and the actor is not, and the asymmetry is the point:
    # naming an actor would let a browser speak as somebody's agent, while naming a door can at
    # worst mislabel a line of your own conversation.
    source = str(payload.get("source", ""))
    return guarded(lambda: json_reply(say(root, text, card=card, source=source)))
