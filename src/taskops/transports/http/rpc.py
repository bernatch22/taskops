"""`POST /api/rpc` — every verb a remote clone runs HERE, through one door.

This endpoint is what "the server is the source of truth" means mechanically. Before it, two
verbs ran on the server (`next`, `update`) and everything else ran on the clone and synced —
and every synced verb grew its own mirror, cursor and replay rule, each of which broke in its
own way the first time three clones shared a board. One door, one registry (`_verbs`), and a
new verb is a ROW there instead of a bespoke endpoint plus a client method plus a sync path.

The actor always arrives IN THE BODY, resolved by the caller — the same trust decision
`agentapi` documents: this server cannot know a remote machine's git config, so the project
token is the boundary and the shape is still enforced (`identity.parse` refuses nonsense).
"""

from __future__ import annotations

from pathlib import Path

from ._verbs import VERBS
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["post_rpc"]


def post_rpc(root: Path, request: Request) -> Reply:
    payload = request.payload()
    verb = str(payload.get("verb", "")).strip()
    handler = VERBS.get(verb)
    if handler is None:
        return error_reply(400, f"`{verb}` is not a verb this server runs — it knows "
                                f"{', '.join(sorted(VERBS))}", "bad_request")
    args = payload.get("args")
    return guarded(lambda: json_reply(handler(root, args if isinstance(args, dict) else {})))
