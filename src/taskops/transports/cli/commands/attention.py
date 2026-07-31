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
    parser.add_argument("--wait", action="store_true",
                        help="block until something IS waiting, then print it and exit — run "
                             "it in the background and keep working; when it returns, sweep")
    parser.add_argument("--every", type=float, default=20.0,
                        help="seconds between checks while waiting (default 20)")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    view = sweep_board(repo_of(args), actor=str(args.actor))
    if args.wait:
        view = _until_something(repo_of(args), str(args.actor), view,
                                every=max(2.0, float(args.every)))
    return render_attention(view)


def _until_something(repo: object, actor: str, view: object, *, every: float) -> object:
    """Poll until the board wants a decision from this actor, then hand the answer back.

    A live session INVENTED this: told there was nothing to do while another developer's
    workers were mid-flight, it wrote itself a bash loop around `taskops attention` and slept
    in it — and the continuous flow everybody liked was that improvisation. This is the same
    loop as a verb, so the next session does not have to be clever: one blocking call, run in
    the background, that exits precisely when there is something to act on.

    Polling and not push, deliberately. The channel exists for push and stays optional; this
    works today, over the same read the session already trusts, with no flags and no policy.
    """
    import time

    while not view["waiting"]:      # type: ignore[index]
        time.sleep(every)
        view = sweep_board(repo, actor=actor)      # type: ignore[arg-type]
    return view
