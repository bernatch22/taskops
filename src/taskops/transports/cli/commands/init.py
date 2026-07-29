"""`taskops init` — make a repository coordinated, and say what actually happened."""

from __future__ import annotations

import argparse

from ....usecases import InitReport
from ....usecases import init as setup
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("init", help="create .taskops/ and install the git hooks")
    add_target(parser)
    parser.add_argument("--no-hooks", action="store_true", dest="no_hooks",
                        help="skip the git hooks (the MCP tools work without them)")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    report = setup(repo_of(args), install_git_hooks=not args.no_hooks)
    return _describe(report)


def _describe(report: InitReport) -> str:
    """Report the SKIPPED hooks too. An init that quietly installed two of three would
    leave a project whose commits are only sometimes recorded, which is worse than none.

    And say that re-running is the REPAIR. Hooks live in `.git/hooks`, which is untracked, so
    a fresh clone has none — and a repository set up before the wiring moved to
    `taskops.transports.hooks` has hook lines naming a command that no longer exists. Every
    hook line ends in `|| true`, so that failure is completely silent; the only thing a person
    can act on is knowing that `taskops init` again fixes it.
    """
    lines = [f"{'created' if report.created else 'already a'} taskops project at "
             f"{report.root}"]
    if report.adopted:
        lines.append(f"adopted {report.adopted} change(s) from the committed log")
    if report.hooks:
        lines.append(f"hooks installed: {', '.join(report.hooks)}")
    for skipped in report.skipped:
        lines.append(f"hook skipped — {skipped}")
    lines.append("")
    lines.append("Register the MCP server with:")
    lines.append("  taskops setup      # the shell alias that opens a session with the board channel")
    return "\n".join(lines)
