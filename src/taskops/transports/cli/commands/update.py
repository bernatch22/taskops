"""A transition, a comment, a mention — the write path, reached from `taskops tasks`.

`taskops update` was the agent's spelling and left with the rest of the agent protocol; the
FUNCTION could not leave, because `tasks done` and `tasks release` are this call with the
status already chosen. A second door onto `done` that skipped this is exactly what the guard
in `usecases.update` exists to prevent.

`evidence` is read with `getattr` because only the closers declare it: `blocked_on` and a bare
comment have nothing to evidence, and giving every caller the flag would advertise a field that
does nothing on four of the five paths through here.
"""

from __future__ import annotations

import argparse

from ....render import render_update
from ....usecases import update as apply
from ._shared import repo_of

__all__ = ["run"]


def run(args: argparse.Namespace) -> str:
    mentions = tuple(p.strip() for p in str(args.mentions).split(",") if p.strip())
    return render_update(apply(repo_of(args), str(args.task), actor=args.actor,
                               status=args.status, comment=args.comment,
                               mentions=mentions, blocked_on=args.blocked_on,
                               no_code=bool(args.no_code),
                               evidence=str(getattr(args, "evidence", "") or ""),
                               no_evidence=str(getattr(args, "no_evidence", "") or "")))
