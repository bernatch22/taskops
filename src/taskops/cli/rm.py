"""`taskops board rm` — the only command in taskops that destroys a history.

    taskops board rm                       the recorded host and board (`cli/remote.py`)
    taskops board rm facturador            refuses unless this checkout holds that history
    taskops board rm facturador --discard-history      destroy it anyway

It is its own module for the reason `push.py` is: the verb is one call, and
everything around it is the guardrail. What this command sends is not an
instruction, it is an ANSWER — the event ids this checkout can still read, so the
host can decide for itself whether removing the board would lose anything
(`http/removal.py` makes the judgement; `core/holding.py` is the comparison both
halves of this chapter share).

**The ids come from the LOCAL board, `.taskops/board/events.jsonl`** — the same
file `board push` promotes and the file `taskops board pull` writes. A checkout
that is joined to the hosted board has none of them: it reads the board over the
wire and holds nothing, which is true and is exactly what the refusal says.

**No `--force`, and not as an alias either** (ARCHITECTURE.md §11): a flag that
does not name what it overrides is how somebody destroys a history they meant to
keep. `--discard-history` names it, and the host is what enforces it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import remote, operate
from ..board import DIR, find_root
from ..store.log import read as read_log


def run(args: argparse.Namespace) -> int:
    """One call, and the refusal comes back in the HOST's own words."""
    host, name = remote.named(str(args.target))
    root = find_root(Path.cwd())
    sent = {
        "board": name,
        "held": held(root),
        "discard_history": bool(getattr(args, "discard_history", False)),
    }
    answer = operate.call(host, "board.remove", sent, operate.signed_in(host, args))
    print(f"{answer['board']} is GONE from {host} — {answer['events']} event(s) went with it")
    if answer.get("held_elsewhere"):
        print(f"  {answer.get('gap')} — this checkout still reads them, and it is now the copy")
    else:
        print(f"  --discard-history: {answer.get('gap')}. Those events are nowhere now")
    return 0


def held(root: Path) -> list[str]:
    """The event ids this checkout can still read for itself.

    Read from the log rather than from the cache: `cache.sqlite` is derived and
    disposable, and the question being answered is "what would survive if the
    host's copy stopped existing" — which only the truth on disk answers. A
    quarantined line is not held (`store/log.py` drops it), and that is the right
    side to be wrong on: a removal that counted a corrupt line as safe is the
    failure this whole card exists to prevent.
    """
    events, _ = read_log(root / DIR / "board" / "events.jsonl")
    return [event["id"] for event in events]
