"""`taskops sync` — reconcile with what git brought in. Called from post-merge."""

from __future__ import annotations

import argparse

from ....usecases import sync as reconcile
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("sync", help="import and export the committed event log")
    add_target(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    report = reconcile(repo_of(args))
    unblocked = (f", {len(report.unblocked)} now ready" if report.unblocked else "")
    return (f"synced: {report.imported} event(s) in, {report.exported} out{unblocked}")
