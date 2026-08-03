"""`taskops policy` — the project settings the engine acts on.

Next to `context` because they answer adjacent questions, and separate from it because they
answer them for different readers: `context` is prose a WORKER weighs, `policy` is a value the
ENGINE obeys. The one that used to live inside the other could not be validated, so a typo was
a setting that recorded and did nothing.

The verb IS the setting name (`taskops policy reviewer peer`), the same shape `context` uses
for its sorts, because the caller is usually an agent turning a sentence somebody said into a
command. With no value it reads instead of writing, so `policy reviewer` answers "what is it
set to" without the caller having to know a second word for that.
"""

from __future__ import annotations

import argparse

from ....contracts.policy import NAMES, Policy
from ....usecases.policy import set_policy, show
from ._shared import add_actor, add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("policy", help="the project settings: what a card gets by default")
    add_target(parser)
    add_actor(parser)
    parser.add_argument("name", nargs="?", default="show", choices=("show", *NAMES),
                        help="the setting to read or write")
    parser.add_argument("value", nargs="?", default=None,
                        help="the value to set; omit to read it, `none` to clear it")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where, name, value = repo_of(args), str(args.name), args.value
    if name == "show":
        return "\n".join(_line(p) for p in show(where)) or "nothing set — every default is off"
    if value is None:
        found = [p for p in show(where) if p["name"] == name]
        return _line(found[0]) if found else f"{name}  (not set)"
    return f"set {_line(set_policy(where, name, str(value), actor=str(args.actor)))}"


def _line(policy: Policy) -> str:
    """The value is what the reader came for, so it leads; who set it trails as provenance.

    An empty value prints as `(none)` rather than as nothing — a blank right-hand side reads as
    a rendering bug, and "explicitly no default" is a real state somebody chose.
    """
    return f"{policy['name']:<10} {policy['value'] or '(none)'}   · {policy['actor']}"
