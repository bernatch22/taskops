"""The nine tools. A tool is not a verb: a verb is one write on the board; a
tool is what an agent should be able to think in one move. The two handlers
that run git live in `gitmoves.py` — every git invocation happens in the
client, where the caller's filesystem actually is.
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple
from pathlib import Path

from . import render, dossier, gitmoves
from ..board import Board
from .schema import SCHEMAS
from .._errors import BadRequest
from ..gitwork import bind

Args = dict[str, Any]
Handler = Callable[[Board, Path, Args, float], str]


class Tool(NamedTuple):
    name: str
    description: str
    schema: dict[str, Any]
    run: Handler


# ── handlers ────────────────────────────────────────────────────────────────


def _board(board: Board, repo: Path, args: Args, now: float) -> str:
    """A pure read. There is nothing to repair: a card whose worker stopped
    renewing is STALLED by derivation, and the move is to hand it to somebody."""
    return render.board(board.call("board", args), now)


def _card(board: Board, repo: Path, args: Args, now: float) -> str:
    data = board.call("card", args)
    return render.matches(data) if "matches" in data else dossier.card_view(data, now)


def _plan(board: Board, repo: Path, args: Args, now: float) -> str:
    return render.plain(board.call("plan", args))


def _take(board: Board, repo: Path, args: Args, now: float) -> str:
    return dossier.card_view(board.call("take", args), now)


def _review(board: Board, repo: Path, args: Args, now: float) -> str:
    data = board.call("review", args)
    return dossier.card_view(data, now) if "history" in data else render.plain(data)


def _comment(board: Board, repo: Path, args: Args, now: float) -> str:
    """Saying something is not changing something, so it is not the same tool.

    One verb underneath (`update` — one write path for everything that happens
    to a card after it exists, which is the lesson v1 paid for), two tools on
    top: an agent that wants to talk should not be reading about `no_code` and
    `after` to find out how. The board's own asymmetry is what this surfaces —
    ANY open card can be written on, while taking and closing are the owner's.
    """
    args["comment"] = args.pop("text", "")
    return render.plain(board.call("update", args))


def _update(board: Board, repo: Path, args: Args, now: float) -> str:
    """`note=` is the reason for a status change, never a way to talk: a note
    with no status would be a comment written through the wrong door, and two
    doors to the same thread is how a card ends up with half its conversation
    filed as status reasons."""
    note = str(args.pop("note", ""))
    if note and not args.get("status"):
        raise BadRequest(
            'note= explains a status change. To say something: taskops_comment task=… text="…" '
            "(any open card, mentions=[…] to address somebody)."
        )
    if note:
        args["comment"] = note  # the verb files it inside the status event
    return render.plain(board.call("update", args))


# ── the table ───────────────────────────────────────────────────────────────


def _tool(name: str, description: str, run: Handler) -> Tool:
    return Tool(name, description, SCHEMAS[name], run)


TOOLS: list[Tool] = [
    _tool(
        "taskops_board",
        "THE pulse: what the board is waiting for, grouped by the move each card needs "
        "(MERGE, MENTIONS, REVIEW, CHANGES, STALLED, TAKE, DOING, REVIEWING, BLOCKED). "
        "Open every turn with this.",
        _board,
    ),
    _tool(
        "taskops_card",
        "One card in full — spec, the whole thread, the graph, file collisions, its "
        "worktree. Or query=<text> to search titles and specs.",
        _card,
    ),
    _tool(
        "taskops_plan",
        "Write the tree in ONE call: a milestone and its cards, dependencies included. "
        "`after` and `parent` take an index into this call's tasks. Orchestrator only.",
        _plan,
    ),
    _tool(
        "taskops_assign",
        "Assign cards to workers, cut one worktree each, and return a paste-ready brief "
        "per card. Spawn one sub-agent per brief, all in one message. Orchestrator only.",
        gitmoves.assign,
    ),
    _tool(
        "taskops_merge",
        "Integrate a DONE card into its milestone branch (--no-ff, in the integration "
        "worktree). A conflict aborts clean. main is never touched. Orchestrator only.",
        gitmoves.merge,
    ),
    _tool(
        "taskops_take",
        "Claim your card and get everything back: the milestone's goal, the spec, the "
        "whole thread, the previous worker's note, collisions, your worktree. Workers only.",
        _take,
    ),
    _tool(
        "taskops_review",
        "THE verifier's one door: taskops_review task=… CLAIMS a submitted card (one "
        "verifier per card, full dossier back, the worker's lease untouched); with "
        "verdict=pass|changes and note= it judges it — the note reaches the worker "
        "verbatim. You may never judge your own work.",
        _review,
    ),
    _tool(
        "taskops_update",
        "Change the CARD: close it (done needs a commit, or no_code=true), hand it in for "
        "review (status=review on a card that requires it), hand it back (status=released, "
        "note= how far you got), drop it (note= why), retitle, rewrite the spec or criteria, "
        "re-prioritise, declare a dependency. To say something: taskops_comment.",
        _update,
    ),
    _tool(
        "taskops_comment",
        "Say something on ANY open card — including one somebody else holds, on another team. "
        "mentions=[…] addresses it to them and reaches them on their very next call. THE channel "
        "between agents in parallel: when your files meet theirs, say so on their card.",
        _comment,
    ),
]

BY_NAME = {tool.name: tool for tool in TOOLS}


def call(board: Board, repo: Path, name: str, args: Args, now: float) -> str:
    tool = BY_NAME.get(name)
    if tool is None:
        raise BadRequest(f"unknown tool {name!r} — this server has: {', '.join(BY_NAME)}")
    bind.drain(board, repo)  # cheap when empty; this is what un-strands a queued commit
    return tool.run(board, repo, dict(args), now)
