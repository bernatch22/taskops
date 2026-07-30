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
from . import update as update_cmd
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

    _close(sub, "done", "finish a task", "done")
    _close(sub, "release", "hand a task back, unfinished", "released")
    _close(sub, "cancel", "close a task nobody will do — the nearest thing to deleting one",
           "cancelled", reason=True)

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


def _close(sub: "argparse._SubParsersAction[argparse.ArgumentParser]", name: str,
           help_text: str, status: str, *, reason: bool = False) -> None:
    """`done`, `release` and `cancel` are `update` with the status already chosen — the
    transitions a person makes by hand, spelled as the actions they are instead of a flag value
    to recall. The rest of `update`'s namespace is defaulted here, because its `run` reads the
    whole of it.

    `cancel` is what "delete this card" means here, and the difference is not pedantry: the log
    is append-only and has no eraser, so a deleted card would have to be a hole in a history
    every report is derived from. Cancelling closes it — it stops blocking its dependents
    exactly as `done` does, leaves the board, and stays readable. What it also does is keep the
    REASON, which is the thing somebody wants three weeks later when the same card gets
    proposed again.

    `reason` makes `-m` mandatory for that one: a cancelled card with no explanation is a card
    that will be recreated by the next person who has the idea.
    """
    parser = _flags(sub.add_parser(name, help=help_text), update_cmd.run)
    parser.add_argument("task", help="the task id")
    parser.add_argument("-m", "--comment", default="", required=reason,
                        help="why it will not be done, for the thread" if reason
                             else "what happened, for the thread")
    parser.add_argument("--no-code", action="store_true", dest="no_code",
                        help="this task legitimately produces no commit")
    parser.set_defaults(status=status, mentions="", blocked_on="", no_code=reason or False)
