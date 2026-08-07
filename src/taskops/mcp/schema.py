"""The JSON Schema of each tool, written by hand.

Not generated from the TypedDicts: the DESCRIPTION of an argument is what stops
a wrong call from being made at all, and a generator has nothing useful to say
about `after: <an index into this very call>`. This is the first line of
defence; `verbs/_args.py` is the second. Neither one coerces.
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

SCHEMAS: dict[str, dict[str, Any]] = {
    "taskops_board": _object(
        {
            "milestone": _text("ms-… to focus one chapter; default: the open one"),
            "window": _text('hours over the last N calendar days, e.g. "7d"'),
            "tz": _text("timezone for those days, e.g. Europe/Madrid (default UTC)"),
        }
    ),
    "taskops_card": _object(
        {
            "task": _text("tk-…"),
            "query": _text("search titles and specs instead"),
        }
    ),
    "taskops_plan": _object(
        {
            "milestone": _text("a title to open a chapter, or an existing ms-… id"),
            "goal": _text("WHY this milestone exists — it travels into every take"),
            "rules": _list(
                "what holds for EVERY card of this chapter, e.g. "
                '["Decimal, never float", "no migrations in this milestone"]. Shown above '
                "the spec in every take: a rule read after building is a rewrite."
            ),
            "criteria": _list(
                "what the CHAPTER is accepted against — every card can be green while the "
                "milestone is not. Shown at taskops_merge milestone=, refused until answered."
            ),
            "reviews": _flag(
                "chapter default: cards get review=true — OPTIONAL; a per-card review= wins"
            ),
            "tasks": {"type": "array", "description": "the cards, in order", "items": CARD},
        },
        ["tasks"],
    ),
    "taskops_assign": _object(
        {
            "tasks": _list("the cards to hand out"),
            "workers": _list("names for them; default w1, w2, … (the free ones)"),
            "worktrees": _flag("cut one worktree per card (default true)"),
        },
        ["tasks"],
    ),
    "taskops_merge": _object(
        {
            "task": _text("a DONE card → into its milestone branch"),
            "milestone": _text(
                "ms-… → land the WHOLE milestone into the trunk. Refused while any card "
                "of it is open or unintegrated. The human's call — never do this with "
                "raw git in the shared checkout; the board must record the landing."
            ),
            "criteria_met": _flag(
                "with milestone=: the human's answer to its criteria — recorded, never judged"
            ),
        }
    ),
    "taskops_take": _object(
        {
            "task": _text("tk-… — yours; empty takes what is assigned to you"),
            "title": _text("create AND claim a card you found mid-work"),
            "spec": _text("with title=: what done means"),
            "criteria": CRITERIA,
            "files": _list("with title=: the edit surface"),
            "labels": LABELS,
            "milestone": _text("with title=: which chapter it belongs to"),
        }
    ),
    "taskops_review": _object(
        {
            "task": _text("a submitted tk-… (its card has review=true)"),
            "verdict": {
                "enum": ["pass", "changes"],
                "description": "pass: ready for the orchestrator to close. changes: back to "
                "the worker. Omit it to CLAIM the review and read everything first.",
            },
            "note": _text(
                "required with a verdict — what was checked, or what to change. The worker "
                "is shown it verbatim."
            ),
        },
        ["task"],
    ),
    "taskops_comment": _object(
        {
            "task": _text("tk-… — ANY open card, including one somebody else holds"),
            "text": _text("what you want to say. The thread is never truncated."),
            "mentions": _list(
                "address it to somebody: dev:<name> or agent:<dev>/<name>. They see it in the "
                "pulse line of their very next call, and it clears itself when they write on "
                "the card — there is nothing to mark as read."
            ),
        },
        ["task", "text"],
    ),
    "taskops_update": _object(
        {
            "task": _text("tk-…"),
            "note": _text(
                "why THIS status change — released and dropped require it, and the next "
                "worker is shown a released note verbatim. To just say something, or to "
                "address somebody, use taskops_comment."
            ),
            "status": {
                "enum": ["done", "review", "released", "dropped", "open"],
                "description": "done needs a commit (or no_code); review hands the card in "
                "for its verdict (note= says what you did); released needs a note; "
                "dropped needs a reason",
            },
            "review": _flag("this card must pass review before it closes (flip after planning)"),
            "no_code": _flag("closing with no commit — say what happened instead"),
            "after": _text("tk-… this card waits for"),
            "milestone": _text("move the card — or, with no task=, update the milestone"),
            "title": _text("rename"),
            "spec": _text("rewrite the spec"),
            "criteria": CRITERIA,
            "priority": PRIORITY,
            "files": _list("replace the edit surface"),
            "labels": LABELS,
            "goal": _text("with milestone= and no task=: rewrite the goal"),
            "rules": _list("with milestone= and no task=: replace the chapter's rules, whole"),
            "reviews": _flag(
                "with milestone= and no task=: change the chapter's review DEFAULT — it "
                "applies to cards planned after it, never retro-flags one"
            ),
        }
    ),
}

# Every tool takes actor= — identity is per CALL, not per process, because the
# host runs one MCP server per session and every sub-agent shares it.
for _schema in SCHEMAS.values():
    _schema["properties"]["actor"] = ACTOR
