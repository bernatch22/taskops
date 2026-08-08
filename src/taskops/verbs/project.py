"""project — a fact about the REPO, recorded once by the side that has it.

The board never reads a repo (the chapter's first rule): a git fact enters as
an EVENT, written by whoever holds the clone. `taskops init` and `taskops join`
already hold it and are already touching the board, so that is where the
repo's web home is read from `origin` and sent here — local or remote, through
the same `Board.call` door, because a remote dashboard has no repo to ask.

There is exactly one op today, `remote`, and its value is `{host, slug, url}`
(the argument is in `gitwork/remote.py`). Ops are how this grows: a second
board-level fact is a value here, not a second event kind and a second fold.

**Recording the same value twice writes nothing.** The event id is a hash of
its content and its timestamp, so an unchanged re-run WOULD append a fresh
event every time somebody re-ran `init` — noise in a log that is replayed
forever and has no delete. A CHANGED origin writes, and wins by being later.
"""

from __future__ import annotations

from typing import Any

from . import _args
from .. import _clock
from .._errors import BadRequest
from ..core.event import make
from ..core.types import PROJECT
from ..store.stores import Stores

OPS = ("remote",)


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    op = _args.text(args, "op", default="remote")
    if op not in OPS:
        raise BadRequest(f"op={op!r} is not a project fact — this board knows: {OPS}")
    value = _value(args)
    now = _clock.now()
    stores.live.renew(actor, now)
    if stores.state()["project"].get(op) == value:
        return {"op": op, "value": value, "recorded": False, "seq": stores.head()}
    seq = stores.write([make(PROJECT, actor, "project", {"op": op, "value": value}, now)])
    return {"op": op, "value": value, "recorded": True, "seq": seq}


def _value(args: _args.Args) -> dict[str, Any] | None:
    """`slug=""` means "there is no origin" — a legal value that clears the fact."""
    slug = _args.text(args, "slug", default="")
    if not slug:
        return None
    host = _args.text(args, "host", default="")
    return {
        "host": host,
        "slug": slug,
        "url": _args.text(args, "url", default="") or f"https://{host}/{slug}",
    }
