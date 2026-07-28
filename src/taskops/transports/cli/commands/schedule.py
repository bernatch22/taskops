"""`taskops schedule install|status` — the daily sweep's prompt file, honestly reported.

The output is shaped around the one thing this command cannot do. It writes a SKILL.md; the
cadence lives inside Claude Code and is set by asking Claude for it. So every successful run
prints what was WRITTEN and, underneath, what REMAINS — the exact sentence to say — and the
word "installed" is never applied to a schedule.
"""

from __future__ import annotations

import argparse

from ....usecases.schedule import NAME, ScheduleFile, install_schedule, read_schedule
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("schedule",
                            help="the daily report's scheduled-task file for Claude Code")
    add_target(parser)
    parser.add_argument("action", nargs="?", default="status", choices=("install", "status"))
    parser.add_argument("--name", default=NAME, help="the scheduled task's folder name")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where = repo_of(args)
    name = str(args.name)
    if args.action == "install":
        return _installed(install_schedule(where, name=name))
    return _status(read_schedule(where, name=name))


def _installed(found: ScheduleFile) -> str:
    return "\n".join([
        f"wrote {found['path']}",
        "",
        "That file is the PROMPT. Claude Code keeps the schedule itself, so nothing runs "
        "yet — say this to Claude:",
        "",
        f"  {found['ask']}",
    ])


def _status(found: ScheduleFile) -> str:
    """A missing file and a present one are both answers, and neither is an error."""
    if not found["exists"]:
        return "\n".join([
            f"no scheduled task at {found['path']}",
            "run `taskops schedule install` to write it",
        ])
    return "\n".join([
        f"{found['path']} exists",
        "whether it has a TIME is Claude Code's to say — this file only holds the prompt.",
        "if the reports are not appearing, say to Claude:",
        "",
        f"  {found['ask']}",
    ])
