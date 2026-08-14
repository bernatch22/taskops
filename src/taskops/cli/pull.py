"""`taskops board pull` — a hosted board comes DOWN, and the host keeps everything.

    taskops board pull                     the recorded host, the recorded name
    taskops board pull https://taskops.example.com/facturador --key ~/.ssh/id_ed25519

`board push` run backwards, and asymmetrical in one place: a push ARCHIVES the
local history it promoted, and a pull removes nothing at all. The board on the
server is untouched, byte for byte — only this checkout's `board.json` changes,
and only once every event id has been proved to be here.

**What lands is a SNAPSHOT, and it stops moving.** Nothing syncs afterwards: a
card taken on the server ten seconds later never appears here, and nothing
anywhere says so. A reader who assumes otherwise is wrong for days without
noticing, which is why the command prints that sentence itself, every time,
instead of leaving it in a document somebody read once.

**THE ORDER IS THE SAFETY, and the config flips LAST** — `cli/push.py`'s five
steps reversed, holding the same rule: a failure at ANY point above leaves the
repo as it was, still reading the host, and the command is simply run again.

    1  no FOREIGN local history here    it would be merged into this one
    2  page the whole log down          the `events` verb, the one that exists
    3  write through `Stores.write`     journal → index → fold, the store's order
    4  verify EVERY ID arrived          a gap STOPS, and the config is untouched
    5  only now: board.json goes local, and remote.json is left alone

**Step 1 is judged BY ID, and that is what makes an interrupted run re-runnable.**
"Is there a local board here" is the obvious guard and it is the wrong one: a
pull that died after step 3 leaves exactly that, so the retry would refuse
itself and the checkout would be stranded between two boards with nothing able
to finish the job. What must be refused is a local history *the host does not
hold* — that one would really be merged, two histories in one log — so the local
ids are checked against the host's (`core/holding.py`) and a partial copy of the
board being pulled is recognised as the resumed pull it is. Step 3 then writes
only what is missing: the CACHE ignores a repeated id and the log does not.

**Two checks, and neither substitutes for the other.** `total` on the answer is
the log's real length and it guards the PAGING — a page silently lost would
shrink both sides of the comparison and agree with itself. The ID SET guards the
write, because a count agreeing proves nothing about WHICH events arrived.

**No new server verb, and that is what makes this safe to add at all.**
Replication between clones is banned (ARCHITECTURE §11) and this is not it: the
log is read through `events`, the same paged read the dashboard's Event pane
uses, by a client with no more rights than any reader. Nothing is kept in step,
no cursor is stored anywhere, and a second run is a no-op instead of a copy.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import paging, remote, operate, commands
from ..core import holding
from ..board import DIR, RemoteBoard, find_root
from .._errors import TaskopsError
from ..store.log import read as read_log
from ..core.types import Event
from ..store.stores import Stores
from ..gitwork.install import write_local

PARKED = (
    "{n} line(s) of {path} do not match their own content. Nothing was pulled: writing a "
    "host's history into a log that is already untrusted would make the two indistinguishable. "
    "Run any taskops command here first — the reader quarantines them beside the log — then pull."
)
FOREIGN = (
    "there is a LOCAL board in {path} with {n} event(s) that {target} does not hold, and "
    "pulling would write the host's history into that same log — two histories in one board, "
    "with an order they never had. Nothing was changed. Two ways forward, both explicit:\n"
    "  taskops join {target} --discard-local   archive this history beside itself, then pull\n"
    "  taskops board pull {target}   in a checkout with no local board of its own\n"
    "(--discard-local renames the directory; nothing is ever deleted.)"
)
MOVED = (
    "{target} reports {total} event(s) and this read came back with {read} — the board moved "
    "while it was being read, or a page was lost. Nothing was written here. Run it again: "
    "a pull takes a snapshot, so it needs one that stopped for the length of the read."
)
SHORT = (
    "STOP — {target} did not arrive whole: {gap}\n"
    "This checkout still reads {target} and its config is untouched. What did arrive is in "
    "{path}, so running the pull again writes only the rest — nothing is duplicated."
)


def run(args: argparse.Namespace) -> int:
    """The five steps, in the one order that is safe to fail in."""
    host, name = remote.named(str(args.target))
    target = f"{host.rstrip('/')}/{name}"
    root = find_root(Path.cwd())
    local = root / DIR / "board"

    mine, rejected = read_log(local / "events.jsonl")
    if rejected:
        raise TaskopsError(PARKED.format(n=len(rejected), path=local / "events.jsonl"))

    board = RemoteBoard(target, operate.signed_in(host, args), commands.actor())
    print(f"reading {target} …")
    theirs, total = paging.whole_log(board, target)
    if len(theirs) != total:
        raise TaskopsError(MOVED.format(target=target, total=total, read=len(theirs)))
    _one_history(local, mine, theirs, target)

    fresh, state = _land(local, theirs)
    if not state["complete"]:
        raise TaskopsError(SHORT.format(target=target, gap=holding.phrase(state), path=local))
    print(f"  {fresh} new event(s) written · {holding.phrase(state)}")
    _flip(root, local, target)
    return 0


def _one_history(local: Path, mine: list[Event], theirs: list[Event], target: str) -> None:
    """Step 1, and it can only be decided once step 2 has the host's ids.

    The question is never "is there a board here" but "would anything be lost" —
    `core/holding.py`'s own direction, asked the other way round: is every event
    HERE one the host holds? Yes means a partial copy of the board being pulled,
    i.e. an interrupted run, which is finished rather than refused. No means a
    second history, and `join`'s orphan refusal is the sentence family because it
    is the same accident from the other side.
    """
    if not mine:
        return
    state = holding.compare([e["id"] for e in mine], [e["id"] for e in theirs])
    if not state["complete"]:
        raise TaskopsError(FOREIGN.format(path=local, n=state["missing"], target=target))


def _land(local: Path, theirs: list[Event]) -> tuple[int, holding.Holding]:
    """Steps 3 and 4: write what is missing, then ask what is held.

    Only what is missing, and that is not an optimisation. `Stores.write` appends
    everything it is handed to `events.jsonl` while the cache ignores a repeated
    id, so re-running a pull with the whole log would leave duplicate LINES in
    the truth and one row in the index — the trap `http/ingest.py` documents from
    the pushing side. The verification is then read back OUT of the store, never
    inferred from what was sent.
    """
    stores = Stores(local)
    try:
        held = stores.ids()
        landing = [e for e in theirs if e["id"] not in held]
        stores.write(landing)
        return len(landing), holding.compare([e["id"] for e in theirs], stores.ids())
    finally:
        stores.close()


def _flip(root: Path, local: Path, target: str) -> None:
    """Step 5, the only step that changes what this repo reads — and it touches
    `board.json` alone. `remote.json` keeps its `login` on purpose: the host is
    still where `board create` and `board push` go, and a checkout made to name a
    key again to reach the server it just pulled from would have lost something a
    pull has no business taking."""
    write_local(root)
    print(f"{root / DIR}/board.json now reads the local copy in {local}")
    print(f"  {target} still holds every one of those events — a pull destroys nothing,")
    print("  and remote.json keeps its login: board create / board push still go there.")
    print("  This copy is a SNAPSHOT and it STOPS MOVING: nothing syncs from here on, so")
    print(f"  anything done on {target} after this second will never appear in it.")
