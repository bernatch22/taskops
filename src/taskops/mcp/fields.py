"""The argument shapes more than one tool declares, and the four builders.

Split out of `schema.py` when it outgrew the 200-line budget, and split HERE
because the seam was already there: below is vocabulary — what an `actor` is,
what a `card` looks like on the wire — and above it, in `schema.py`, is which
tool takes which of these. Two files that change for different reasons.

The DESCRIPTIONS are the point, not the types. A wrong call is stopped by the
sentence next to the argument, never by its JSON type; that is why none of this
is generated from the TypedDicts.
"""

from __future__ import annotations

from typing import Any


def _text(desc: str) -> dict[str, Any]:
    return {"type": "string", "description": desc}


def _list(desc: str) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "description": desc}


def _flag(desc: str) -> dict[str, Any]:
    return {"type": "boolean", "description": desc}


def _object(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
        "additionalProperties": False,
    }


PRIORITY = {"type": "integer", "minimum": 0, "maximum": 3, "description": "0 urgent … 3 idle"}

ACTOR = _text(
    "who is speaking, when it is not the session's own identity. Sub-agents share the "
    "session's ONE MCP server, so a spawned worker MUST pass the agent:<dev>/<name> its "
    "brief names on EVERY taskops call — without it the board hears the orchestrator."
)

CRITERIA = _list(
    "what this card is accepted against — the other half of the spec. The worker "
    "is shown these right under it; closing says which were met and what proves it."
)
LABELS = _list('routing and search hints, e.g. ["backend", "urgent"]')

CARD = _object(
    {
        "title": _text("a label — not the brief"),
        "spec": _text(
            "the brief, complete enough that a fresh agent reads it and needs nothing "
            "else: what done looks like, what must NOT change, and where to look"
        ),
        "criteria": CRITERIA,
        "files": _list("the edit surface; used to warn about collisions"),
        "labels": LABELS,
        "priority": PRIORITY,
        "after": {"description": "an index into this call's tasks, or a card id"},
        "parent": {"description": "the epic: an index into this call's tasks, or a card id"},
        "review": _flag(
            "this card must pass review before it closes. Default: the milestone's "
            "reviews= flag; the card's own value always wins."
        ),
    },
    ["title"],
)

REPO_PATH = _text(
    "another project's board, by any path inside it. Default: the board this "
    "server started in. The host runs ONE MCP server per session, pinned to the "
    "directory it opened, so without this a second project is unreachable and "
    "the work leaves through curl instead of the tools."
)
