"""`taskops attention` — what the board is waiting for. The verb a session opens with."""

from __future__ import annotations

import argparse

from ....render import render_attention
from ....usecases import attention as sweep_board
from ._shared import add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("attention", help="the cards waiting on a decision, and the "
                                              "move each one needs")
    add_target(parser)
    parser.add_argument("--actor", default="",
                        help="who is asking — a review this actor could never close is not "
                             "listed for them")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    return render_attention(sweep_board(repo_of(args), actor=str(args.actor)))
