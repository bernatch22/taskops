"""project — a fact about the REPO, recorded once by the side that has it.

The board never reads a repo (the chapter's first rule): a git fact enters as
an EVENT, written by whoever holds the clone. `taskops init` and `taskops join`
already hold it and are already touching the board, so that is where the
repo's web home is read from `origin` and sent here — local or remote, through
the same `Board.call` door, because a remote dashboard has no repo to ask.

Two ops today. `remote` is `{host, slug, url}` (the argument is in
`gitwork/remote.py`). `visibility` is `{"visibility": "public" | "private"}` —
GitHub's flag, and it is a board-level FACT for the same reason `remote` is:
an event in the log, folded newest-wins, so "when did this become public and
who did it" is answerable from the history rather than from a column somebody
overwrote. Ops are how this grows: a third board-level fact is a value here,
not a third event kind and a third fold.

**A board with no `visibility` event is PRIVATE**, which is what makes every
board that existed before this feature — and every board created after it —
behave exactly as it always did without a migration. `is_public` is the ONE
reader of the fact; the HTTP layer never reaches into `state()` for it.

It rides out on the `board` payload (`verbs/pulse.py`) rather than getting a
door of its own, so a viewer can say "you are reading this as nobody" from the
read it already made — a second call would be one more thing to be refused.

**Recording the same value twice writes nothing.** The event id is a hash of
its content and its timestamp, so an unchanged re-run WOULD append a fresh
event every time somebody re-ran `init` — noise in a log that is replayed
forever and has no delete. A CHANGED origin writes, and wins by being later.
"""

from __future__ import annotations

from typing import Any

from . import _args
from .. import _clock
from .._json import as_object
from .._errors import BadRequest
from ..core.event import make
from ..core.types import PROJECT
from ..store.stores import Stores

OPS = ("remote", "visibility")

PUBLIC = "public"
PRIVATE = "private"
VISIBILITIES = (PRIVATE, PUBLIC)


def visibility(stores: Stores) -> str:
    """`private` unless an owner said otherwise — the default is the whole model.

    Read through here and never as `state()["project"]["visibility"]`: an absent
    fact, a fact from a board older than the feature and a fact cleared back to
    `None` all have to mean the same thing, and three call sites would spell
    that three ways.
    """
    fact: object = stores.state()["project"].get("visibility")
    seen = str(as_object(fact).get("visibility", ""))
    return seen if seen in VISIBILITIES else PRIVATE


def is_public(stores: Stores) -> bool:
    return visibility(stores) == PUBLIC


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    op = _args.text(args, "op", default="remote")
    if op not in OPS:
        raise BadRequest(f"op={op!r} is not a project fact — this board knows: {OPS}")
    value = _visible(args) if op == "visibility" else _value(args)
    now = _clock.now()
    stores.live.renew(actor, now)
    if stores.state()["project"].get(op) == value:
        return {"op": op, "value": value, "recorded": False, "seq": stores.head()}
    seq = stores.write([make(PROJECT, actor, "project", {"op": op, "value": value}, now)])
    return {"op": op, "value": value, "recorded": True, "seq": seq}


def _visible(args: _args.Args) -> dict[str, Any]:
    """`public` or `private`, and NOTHING between them.

    There is no third state and there must never be one: "public read, keyed
    write" is the whole model, so an `unlisted` or a `read-only-for-members`
    would be a second wall to keep in step with the first. A value outside the
    pair is refused by name rather than defaulted — defaulting a typo would
    silently make a board somebody meant to publish stay private, or worse.
    """
    wanted = _args.text(args, "visibility", default="")
    if wanted not in VISIBILITIES:
        raise BadRequest(
            f"visibility={wanted!r} — a board is {PRIVATE!r} or {PUBLIC!r}, and nothing else: "
            "public means anonymous READ, and writing always needs a registered key"
        )
    return {"visibility": wanted}


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
