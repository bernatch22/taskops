"""What every wiring subcommand's parser repeats.

`--repo` defaults to the cwd because the callers are hooks: git runs them from inside the
repository, and Claude Code runs them from the project directory, so requiring the path would
make every hook line longer for no information.

A copy of `cli/commands/_shared` rather than an import of it: a transport that imported
another transport would make the developer's CLI a dependency of git's wiring, which is the
coupling this whole module exists to remove. It is four lines, and they do not drift because
`test_hook_wiring` runs the real installed hook.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

__all__ = ["add_target", "repo_of", "committer_is_agent", "unclaimed_is_allowed"]

ESCAPE = "TASKOPS_ALLOW_UNCLAIMED"


def add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".",
                        help="path in the repository (default: the current directory)")
    parser.add_argument("--actor", default="", help="who is calling")


def repo_of(args: argparse.Namespace) -> Path:
    return Path(str(args.repo))


def committer_is_agent(actor: str = "") -> bool:
    """Is the committer an AGENT rather than a person at a terminal?

    Read from the environment rather than from the board, and that is the point: this is not a
    question about tasks, it is a question about who started this git process. A transport is
    exactly the layer that knows how it was invoked.

    The signal is the IDENTITY — what the caller passed, else `$TASKOPS_ACTOR`, which is what
    the plugin exports per session when `$CLAUDECODE` is set. `CLAUDECODE` on its OWN was
    tried and rejected, and the reason is not convenience:

    - it is exported into every descendant of a session, so `pytest` run inside Claude Code
      inherits it and so does every `git` that pytest spawns. Five existing end-to-end tests
      went red as "unclaimed agent commits" the moment the gate believed it. Anything with
      that failure mode also fires on a developer's own terminal commit inside a session.
    - worse, it is INCOHERENT with the verdict. With no `$TASKOPS_ACTOR` the identity taskops
      resolves is `dev:<git email>`, so the refusal printed would read "dev:berna holds no
      lease" while the gate insisted the committer was an agent. Refusing an actor the same
      breath calls a human is the asymmetry contradicting itself.

    So an agent is an actor that SAYS it is one, which is also the door another harness comes
    through: export `TASKOPS_ACTOR=agent:you/name` and the gate applies, with no code here.
    """
    stated = actor.strip() or os.environ.get("TASKOPS_ACTOR", "").strip()
    return stated.startswith("agent:")


def unclaimed_is_allowed() -> bool:
    """`TASKOPS_ALLOW_UNCLAIMED=1` — the escape hatch, and why one has to exist.

    A rule with no honest exit does not get obeyed, it gets bypassed by lying: `--no-verify`
    skips every hook and leaves nothing behind to look at. An exit that is NAMED is an exit
    somebody can grep for in CI config, which is the difference between a known exception and
    an invisible one.
    """
    return os.environ.get(ESCAPE, "").strip() not in ("", "0")

def cwd(payload: dict[str, Any]) -> str:
    """Where the session is. Defaults to "." so a hand-run hook still works."""
    return str(payload.get("cwd") or ".")


def session_of(payload: dict[str, Any]) -> str:
    return str(payload.get("session_id") or "")
