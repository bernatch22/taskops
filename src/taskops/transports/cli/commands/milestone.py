"""`taskops milestone` — the chapter a board is in, and the four moves that end one.

One noun and one verb per move, because the moves are not symmetric and a flag would hide that:
`review` is a REPORT any agent may file, `done` is a VERIFICATION only a person may make. The
engine refuses the second either way (`engine.milestones`), so this is about the shape a reader
learns from `--help` rather than about safety.

Bare `taskops milestone` shows every ACTIVE chapter with its counts. Several are worked at once
on a real board, so "the chapter" is not a property of the board — a card belongs to exactly one,
and a person choosing what to plan into has to see all of them.
"""

from __future__ import annotations

import argparse

from ....render.milestones import render_chapter, render_chapters
from ....usecases import milestone as ms
from ....usecases._contextviews import chapters
from ....usecases._project import project
from ._shared import add_actor, add_target, repo_of

__all__ = ["register", "run"]

VERBS = ("show", "new", "start", "edit", "review", "done", "reject", "cancel", "list")


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("milestone", help="the chapter this board is in, and its moves")
    add_target(parser)
    add_actor(parser)
    parser.add_argument("verb", nargs="?", default="", choices=("", *VERBS))
    parser.add_argument("what", nargs="?", default="", help="the text for `new`, else an id")
    parser.add_argument("-m", "--message", default="", help="why — required to reject or cancel")
    parser.add_argument("--horizon", default="", help="when it should be reached: YYYY-MM-DD")
    parser.add_argument("--text", default="", help="with edit: the new wording")
    parser.add_argument("--planned", action="store_true", help="write it down without starting it")
    parser.add_argument("--carry", default="", help="with done: card ids to move to the next one")
    parser.add_argument("--into", default="", help="with done: which chapter they move to")
    parser.add_argument("--all", action="store_true", help="with list: closed chapters too")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where, who, what = repo_of(args), str(args.actor), str(args.what)
    if args.verb in ("", "list"):
        return _listing(args, where)
    if args.verb == "new":
        moved = ms.open_chapter(where, what, horizon=str(args.horizon),
                               planned=bool(args.planned), actor=who)
    elif args.verb == "edit":
        moved = ms.edit(where, what, text=str(args.text), horizon=str(args.horizon), actor=who)
    elif args.verb == "show":
        return _one(where, what)
    else:
        moved = _move(args, where, who, what)
    return _one(where, moved["id"])


def _move(args: argparse.Namespace, where: str, who: str, what: str) -> dict:  # type: ignore[type-arg]
    """The four state changes. `reject` and `start` are one op in the machine — the chapter ends up
    in force either way — but they are two words here because they are two intentions."""
    note = str(args.message)
    if args.verb == "start":
        return dict(ms.start(where, what, actor=who))
    if args.verb == "review":
        return dict(ms.hand_over(where, what, note=note, actor=who))
    if args.verb == "done":
        carry = tuple(part.strip() for part in str(args.carry).split(",") if part.strip())
        return dict(ms.verify(where, what, carry=carry, into=str(args.into), actor=who))
    if args.verb == "reject":
        return dict(ms.send_back(where, what, note=note, actor=who))
    return dict(ms.abandon(where, what, note=note, actor=who))


def _one(where: str, wanted: str) -> str:
    """One chapter with its cards — the receipt after every move, because the question after each
    of them is "and how far along is it now"."""
    found = ms.chapter(where, wanted)
    with project(where) as store:
        cards = [dict(t) for t in store.tasks.all() if t["milestone"] == found["id"]]
        return render_chapter(found, chapters(store).counts.get(found["id"], {}), cards=cards)


def _listing(args: argparse.Namespace, where: str) -> str:
    """Active and planned, or with `--all` the whole record. The record is what answers "what have
    we shipped", and it is unanswerable from the chapters still open."""
    with project(where) as store:
        found = chapters(store)
        if not args.all:
            return render_chapters(found.active, found.planned, found.counts)
        every = ms.listing(where)["milestones"]
        return "\n".join(render_chapter(m, found.counts.get(m["id"], {}), cards=[])
                         for m in every) or "no milestone yet"
