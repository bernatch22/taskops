"""`taskops tasks` — everything a person does to the task list, under one name.

Almost nothing here is new behaviour: the subcommands reach `run` functions that already
existed, and the two exceptions (`list`, `add`) are thin over `usecases.board` and
`usecases.plan`. The grouping is for the reader of `--help`, which had grown to nineteen
commands mixing three audiences — a person's task list, an agent's claim/update protocol,
and the git and session plumbing that only a hook ever types. A person had to know which
was which before they could find the one command they wanted.

`taskops tasks` with no subcommand lists, because the list is what you want nine times out
of ten and a group name that prints usage is a name that costs a second turn.
"""

from __future__ import annotations

import argparse
from typing import Any

from ...._errors import BadRequest
from ...._types import STATUSES
from ....render import render_edit, render_plan, render_tasklist
from ....usecases import board
from ....usecases import edit as rewrite
from ....usecases import plan as create
from ._shared import add_actor, add_target, repo_of
from ._tasks_args import add_list_flags, add_subcommands

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("tasks", help="list, read, create and close tasks")
    add_target(parser)
    add_actor(parser)
    add_list_flags(parser)
    parser.set_defaults(run=run_list, subcommand="")
    add_subcommands(parser, listing=run_list, adding=run_add, editing=run_edit)


def run_list(args: argparse.Namespace) -> str:
    """The list, filtered by what was asked for.

    `--status` is validated HERE and not by argparse `choices`, so the refusal reads like
    every other one in the package — the name that was rejected, then the legal values —
    rather than argparse's usage dump, which buries the answer under the whole grammar.
    """
    status = getattr(args, "status", None)
    if status is not None and status not in STATUSES:
        raise BadRequest(f"`{status}` is not a status — use one of {', '.join(STATUSES)}")
    return render_tasklist(board(repo_of(args)),
                           show_all=bool(getattr(args, "all", False)), status=status)


def run_add(args: argparse.Namespace) -> str:
    """One card through the batch door.

    `plan` stays the only creator even for a single task, so a card typed at a terminal
    carries exactly the event body a planned one does — a second insert path here is how the
    log would start holding two shapes of `created`, one of which another machine cannot
    replay. The flags are read into the same dict `plan` takes from JSON, so `_entry` keeps
    owning what every field means.
    """
    entry: dict[str, Any] = {
        "title": str(args.title), "spec": str(args.spec),
        "labels": str(args.labels), "files": str(args.files),
        "after": [part.strip() for part in str(args.after).split(",") if part.strip()],
        "reviewer": getattr(args, "reviewer", None)}
    if args.priority is not None:
        entry["priority"] = int(args.priority)
    return render_plan(create(repo_of(args), [entry], actor=str(args.actor)))


def run_edit(args: argparse.Namespace) -> str:
    """Rewrite a card. `None` means "not passed" all the way down, which is why the flags
    default to it rather than to "": an empty spec is a legitimate edit (somebody clearing a
    brief that was wrong), and a default of "" could not tell that from silence."""
    return render_edit(rewrite(
        repo_of(args), str(args.task), title=args.title, spec=args.spec,
        priority=None if args.priority is None else int(args.priority),
        reviewer=args.reviewer, actor=str(args.actor)))
