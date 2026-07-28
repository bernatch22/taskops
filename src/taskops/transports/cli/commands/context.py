"""`taskops context` — the standing facts a worker needs and its card cannot carry.

The verbs read as sentences (`context objective "ship 0.4 by Friday"`) because the caller is
usually an agent composing a command from a sentence a human said. `show` is the default: the
question asked most often is "what am I working under right now".

Rendering lives here rather than in `render/` while the shape is still settling — three lists
of one-liners, and the useful part is the id, which is what `retire` takes.
"""

from __future__ import annotations

import argparse

from ....contracts.context import SORTS, ContextSlice, Fact
from ....usecases.context import context_for, history, retire, show, state
from ._shared import add_actor, add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("context", help="the standing objective, invariants and decisions")
    add_target(parser)
    add_actor(parser)
    parser.add_argument("verb", nargs="?", default="show",
                        choices=("show", *SORTS, "log", "retire"))
    parser.add_argument("text", nargs="?", default="",
                        help="the fact to state, or the id to retire")
    parser.add_argument("--labels", default="", help="comma-separated scope for a decision")
    parser.add_argument("--files", default="", help="comma-separated edit surface")
    parser.add_argument("--horizon", default="", help="when an objective expires")
    parser.add_argument("--owner", default="", help="whose call this is")
    parser.add_argument("--task", default="", help="with show: the slice for one card")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where, who = repo_of(args), str(args.actor)
    if args.verb == "log":
        return "\n".join(_line(f) for f in history(where)) or "nothing stated yet"
    if args.verb == "retire":
        return f"retired {retire(where, str(args.text), actor=who)['id']}"
    if args.verb in SORTS:
        return f"stated {_line(_state(args, who))}"
    return _slice(context_for(where, str(args.task)) if args.task else show(where))


def _state(args: argparse.Namespace, who: str) -> Fact:
    return state(repo_of(args), str(args.verb), str(args.text), labels=_list(args.labels),
                 files=_list(args.files), horizon=str(args.horizon), owner=str(args.owner),
                 actor=who)


def _list(raw: str) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _slice(view: ContextSlice) -> str:
    """Objective first, invariants next, decisions last — the order a worker should read them
    in, since the invariants are the ones it may not weigh against anything else."""
    lines = ["# objective", _line(view["objective"]) if view["objective"] else "(none set)",
             "", "# invariants"]
    lines += [_line(f) for f in view["invariants"]] or ["(none)"]
    lines += ["", "# decisions"]
    lines += [_line(f) for f in view["decisions"]] or ["(none)"]
    return "\n".join(lines)


def _line(fact: Fact) -> str:
    scope = ", ".join(fact["labels"] + fact["files"])
    tail = f"  [{scope}]" if scope else ""
    return f"{'~' if fact['retired'] else '·'} {fact['id'][:8]}  {fact['text']}{tail}"
