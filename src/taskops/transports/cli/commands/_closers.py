"""The four moves a person makes on a card by hand — `done`, `release`, `reject`, `cancel`.

All four are `update` with the status already chosen, spelled as the ACTIONS they are instead
of a flag value somebody has to recall. Split from `_tasks_args` when the fourth one would not
fit the code budget, and the split reads true: that module wires argparse, this one says what
these four verbs MEAN, which is the part worth reading twice.
"""

from __future__ import annotations

import argparse

from . import update as update_cmd

__all__ = ["CLOSERS", "add_closers"]

CLOSERS = (
    ("done", "finish a task", "done", False),
    ("release", "hand a task back, unfinished", "released", False),
    ("reject", "send a card in review back to its worker, with findings", "ready", True),
    ("cancel", "close a task nobody will do — the nearest thing to deleting one",
     "cancelled", True),
)
"""name, help, the status it sets, and whether a REASON is mandatory.

`reject` is the human half of the review loop: a card in `review` goes back to `ready` with its
findings and — because it is a `ready` and not a `release` — KEEPS its assignee, so the worker
that wrote it is the one who picks it up. `release` means the other thing entirely: I am giving
this up, anybody take it.

`cancel` is what "delete this card" means here, and the difference is not pedantry: the log is
append-only and has no eraser, so a deleted card would be a hole in a history every report is
derived from. Cancelling closes it — it stops blocking its dependents exactly as `done` does —
and keeps the REASON, which is what somebody wants three weeks later when the same idea returns.

The two that demand a reason are the two that END something for somebody else. A rejection with
no finding is a card bounced with nothing to act on: the worker reads "not good enough" and
guesses, which is how a card goes round twice for no reason. A cancellation with no reason is a
card the next person with the same idea simply recreates.
"""


def add_closers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]",
                flags: object) -> None:
    """Register all four. `flags` is `_tasks_args._flags`, passed in rather than imported so
    this module stays about meaning and that one keeps owning the argparse plumbing."""
    for name, help_text, status, reason in CLOSERS:
        parser = flags(sub.add_parser(name, help=help_text), update_cmd.run)  # type: ignore[operator]
        parser.add_argument("task", help="the task id")
        parser.add_argument("-m", "--comment", default="", required=reason,
                            help=("why — the finding, or why it will not be done" if reason
                                  else "what happened, for the thread"))
        parser.add_argument("--no-code", action="store_true", dest="no_code",
                            help="this task legitimately produces no commit")
        if status == "done":
            # Without these the CLI could not close a card carrying acceptance criteria AT ALL:
            # the engine demands evidence, no flag could carry it, and the only way through was
            # the MCP tool. Found by running the two-person simulacro — a person verifying
            # somebody else's card is the most ordinary close there is, and it was the one door
            # that had no handle.
            parser.add_argument("--evidence", default="",
                                help="which criteria you met and what proves each — a test, a "
                                     "command, a run")
            parser.add_argument("--no-evidence", dest="no_evidence", default="",
                                help="why the criteria no longer apply")
        parser.set_defaults(status=status, mentions="", blocked_on="",
                            no_code=reason and status == "cancelled")
