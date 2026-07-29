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

from ...usecases.chat import open_conversation, say, thread
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["get_chat", "post_chat", "post_conversation"]


def get_chat(root: Path, request: Request) -> Reply:
    """The conversation in force, oldest first — a chat is read from the bottom.

    `?all=1` returns every conversation instead. A new session must not open onto yesterday's
    argument, and yesterday's argument must not be gone; those are two requirements, not one,
    and this parameter is where they stop fighting.
    """
    everything = request.param("all") in ("1", "true")
    return guarded(lambda: json_reply(thread(root, everything=everything)))


def post_conversation(root: Path, request: Request) -> Reply:
    """Start a new conversation. Nothing is deleted — the old one stops being shown.

    This is what "clear the chat" means in an append-only log, and the difference matters the
    first time somebody wants back the thing they cleared. The channel calls it when a session
    starts; the sidebar's button calls the same route, because they are the same act.
    """
    return guarded(lambda: json_reply({"conversation": open_conversation(root)}))


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
