"""The subcommands of `taskops tasks`: the names, their flags, and which `run` each reaches.

Split from `tasks.py` for the file budget, and the seam is the honest one: that module holds
the two behaviours this group adds (the compact list, creating one card), this one holds the
wiring. Most subcommands point straight at a `run` that already exists, which is the whole
point of the group — `taskops tasks done` and `taskops update --status done` are one code
path, so they cannot start answering differently.

Every subparser inherits `--repo` and `--actor` rather than owning them, so both orders work:
`taskops tasks --repo /x list` and `taskops tasks list --repo /x`. See `_shared._default`.
"""

from __future__ import annotations

import argparse
from typing import Callable

from . import ask as ask_cmd
from . import log as log_cmd
from . import plan as plan_cmd
from ._closers import add_closers
from ._shared import add_actor, add_target

__all__ = ["add_subcommands", "add_list_flags"]

Runner = Callable[[argparse.Namespace], str]


def add_list_flags(parser: argparse.ArgumentParser) -> None:
    """What the list shows. On BOTH `taskops tasks` and `taskops tasks list`, because the
    bare group name IS the list — a flag that worked on only one of the two spellings would
    be a flag whose absence looks like the feature is missing.

    `--status` takes any string rather than argparse `choices` so the refusal can be the
    package's own sentence; see `tasks.run_list`.
    """
    parser.add_argument("--all", action="store_true",
                        help="show closed tasks too, after the open ones")
    parser.add_argument("--status", default=None, metavar="<status>",
                        help="show only tasks in this status")


def add_subcommands(parent: argparse.ArgumentParser, *, listing: Runner,
                    adding: Runner, editing: Runner) -> None:
    sub = parent.add_subparsers(dest="subcommand", metavar="<subcommand>")
    add_list_flags(_flags(sub.add_parser("list", help="one line per open task"), listing))

    _edit_flags(_flags(sub.add_parser("edit", help="rewrite a task's title, spec or priority"),
                       editing))

    show = _flags(sub.add_parser("show", help="read one task in full"), ask_cmd.run)
    show.add_argument("what", metavar="task", help="the task id")

    _add_flags(_flags(sub.add_parser("add", help="create one task"), adding))

    from_json = _flags(sub.add_parser("plan", help="create tasks from JSON (a file, or -)"),
                       plan_cmd.run)
    from_json.add_argument("source", help="path to a JSON array of tasks, or - for stdin")

    add_closers(sub, _flags)

    entries = _flags(sub.add_parser("log", help="the agent's conversation for a card"),
                     log_cmd.run)
    entries.add_argument("task", help="the task id")
    entries.add_argument("--limit", type=int, default=0,
                         help="entries to keep, newest last (default 400)")

    found = _flags(sub.add_parser("search", help="search titles and specs"), ask_cmd.run)
    found.add_argument("what", metavar="text", help="what to look for")


def _flags(parser: argparse.ArgumentParser, run: Runner) -> argparse.ArgumentParser:
    add_target(parser, inherit=True)
    add_actor(parser, inherit=True)
    parser.set_defaults(run=run)
    return parser


def _add_flags(parser: argparse.ArgumentParser) -> None:
    """One card's worth of `plan`'s JSON, as flags. Anything with a graph in it stays JSON —
    `after` here takes ids only, because an index refers to a batch this command cannot have."""
    parser.add_argument("title", help="what the task is")
    parser.add_argument("--spec", default="", help="the brief: what done looks like")
    parser.add_argument("--after", default="", help="comma-separated ids this waits on")
    parser.add_argument("--files", default="", help="comma-separated edit surface")
    parser.add_argument("--priority", type=int, default=None, help="0 urgent … 3 whenever")
    parser.add_argument("--label", default="", dest="labels", help="comma-separated labels")
    # `None` is ABSENT, so the project's default applies; anything typed is honoured, and
    # `none` is how somebody says nobody without the shell swallowing an empty string.
    parser.add_argument("--reviewer", default=None,
                        help="who may close it: `human`, `dev:<name>`, a registered agent, or "
                             "`none` to skip review on this card (default: the project's)")


def _edit_flags(parser: argparse.ArgumentParser) -> None:
    """The three fields a card can be corrected in. All default to `None` — "not passed" —
    so that `--spec ""` clears a brief instead of being indistinguishable from not saying it.
    Requiring at least one is the use case's job, not argparse's: the CLI is one of three
    surfaces, and a rule only argparse knows is a rule the other two do not have."""
    parser.add_argument("task", help="the task id")
    parser.add_argument("--title", default=None, help="what the task is")
    parser.add_argument("--spec", default=None, help="the brief: what done looks like")
    parser.add_argument("--priority", type=int, default=None, help="0 urgent … 3 whenever")
    parser.add_argument("--reviewer", default=None,
                        help="who may close it; pass '' to clear and fall back to the verifier")


_CLOSERS = (
    ("done", "finish a task", "done", False),
    ("release", "hand a task back, unfinished", "released", False),
    ("reject", "send a card in review back to its worker, with findings", "ready", True),
    ("cancel", "close a task nobody will do — the nearest thing to deleting one",
     "cancelled", True),
)
"""The four moves a person makes by hand, as data — see `_close` for what each one means."""


