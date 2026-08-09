"""`taskops board push` — this repo's local board becomes the hosted one.

    taskops board push                     the recorded host, the recorded name, the
                                           discovered key (`cli/remote.py`)
    taskops board push https://taskops.example.com/facturador --key ~/.ssh/id_ed25519

What this replaces is a README paragraph that said "scp the events.jsonl to the
box": storage leaked into UX, and nothing verified anything. You copied a file
and hoped; a short copy was found out days later, from a board missing a week.

**THE ORDER IS THE SAFETY, and the config flips LAST.** Nothing here changes
until the server has the history and the counts have been compared, so a failure
at ANY point above leaves the repo as it was — still local, still the only copy,
and the command is run again:

    1  the target exists and is EMPTY          (the server answers; `http/ingest.py`)
    2  no live lease here                      nobody is mid-work during the move
    3  stream the log through `board.ingest`   idempotent ids make a retry a no-op
    4  verify: the count and the count per KIND  a mismatch STOPS, config untouched
    5  only now: board.json + remote.json, and `.taskops/board/` is ARCHIVED

Step 5 archives and never deletes: the directory it came from is the last thing
that proves what was pushed, so it is renamed and left where somebody finds it.

**Retry is by construction, not by bookkeeping.** An event id is `sha256` of its
own canonical bytes, so re-sending the whole log after an interruption writes
only what is missing and the second run reports `already_held` — no resume cursor
to get wrong, and no state anywhere saying where the last attempt stopped.
"""

from __future__ import annotations

import argparse
from typing import Any
from pathlib import Path
from collections import Counter

from . import enrol, remote, operate
from .. import _clock, identity
from .._json import as_object
from ..board import DIR, find_root, read_config
from .._errors import TaskopsError
from ..store.log import read as read_log
from ..core.event import to_line
from ..core.types import Event
from ..gitwork.install import write_config

ALREADY_REMOTE = (
    "this repo is already joined to {url} — there is no local history here to promote. "
    "`board push` moves a LOCAL board onto a host, and it happens once."
)
NOTHING_LOCAL = (
    "no local board with any events in {path} — `taskops init` starts one, and "
    "`taskops join <url>` is how you connect to a board that already exists"
)
QUARANTINED = (
    "{n} line(s) of {path} do not match their own content. Nothing was pushed: a "
    "promotion that silently dropped events would be worse than no promotion. Run any "
    "taskops command here first — the reader quarantines them beside the log — then push."
)
STILL_WORKING = (
    "somebody is holding a lease on this board right now ({who}) — a push moves a "
    "history, and a card being worked on is a fact that has not finished happening. "
    "Wait for them, or let the lease lapse, then push."
)
NO_KEY = (
    "no session for {host}, and no ssh key to make one with — tried {tried}. Say which "
    "key signs you in: taskops board push <host>/<name> --key <path> "
    "(add --invite <token> the first time, so the host registers it)"
)
MISMATCH = (
    "STOP — {host}/{name} did not come back with what was sent:\n{table}\n"
    "Nothing in this repo was changed: it is still the local board, and it is still "
    "the only copy. Investigate the server before running this again."
)


def run(args: argparse.Namespace) -> int:
    """The five steps, in the one order that is safe to fail in."""
    host, name = remote.named(str(args.target))
    root = find_root(Path.cwd())
    config = read_config(root)
    if config.get("url"):
        raise TaskopsError(ALREADY_REMOTE.format(url=config["url"]))

    local = root / DIR / "board"
    events, rejected = read_log(local / "events.jsonl")
    if rejected:
        raise TaskopsError(QUARANTINED.format(n=len(rejected), path=local / "events.jsonl"))
    if not events:
        raise TaskopsError(NOTHING_LOCAL.format(path=local))
    _idle(local)

    token, door = _session(root, config, f"{host}/{name}", str(args.key), str(args.invite))
    lines = [to_line(event) for event in events]
    print(f"pushing {len(lines)} events to {host}/{name} …")
    answer = operate.call(host, "board.ingest", {"board": name, "events": lines}, token)

    table = _compare(events, answer)
    if table is not None:
        raise TaskopsError(MISMATCH.format(host=host, name=name, table=table))
    held = int(answer.get("already_held", 0))
    retry = f" ({held} were already there — this was a retry)" if held else ""
    print(f"  verified: {answer.get('landed')} landed, seq {answer.get('seq')}{retry}")
    _flip(root, host, name, token, door)
    return 0


def _idle(local: Path) -> None:
    """Step 2. `live.sqlite` does not travel — it is a fact about processes that
    are running, and none will run against the new host. So the check is not
    "copy the leases", it is "there must be none to lose"."""
    from ..store.live import Live

    live = Live(local / "live.sqlite")
    try:
        held = live.held(_clock.now())
    finally:
        live.close()
    if held:
        who = ", ".join(f"{lease['actor']} on {lease['task']}" for lease in held)
        raise TaskopsError(STILL_WORKING.format(who=who))


def _session(
    root: Path, config: dict[str, Any], target: str, key: str, invite: str
) -> tuple[str, dict[str, str] | None]:
    """Step 3's credential, and the `login` block step 5 will write beside it.

    A repo with a LOCAL board has never joined anything, so there is usually
    nothing in `remote.json` to sign with — `--key` is how the push says who it
    is, and `--invite` registers that key first, through the SAME redemption
    `taskops join --key` runs (`enrol.redeem`).

    Signing in caches the token in `remote.json`, and that is NOT the config flip:
    `board.json` still names no url, so `open_board` still opens the local board
    and every step above still fails into a repo that decides what it did before.
    So the `login` block comes back UNWRITTEN and step 5 places it — this is the
    one caller of `identity.establish` that has an order to keep, and the reason
    that helper returns the block rather than caching it (`operate.py` does).
    """
    from . import commands

    host = target.rpartition("/")[0]
    if invite and not key:
        raise TaskopsError("--invite registers a KEY — pass --key ~/.ssh/id_ed25519 with it")
    who = identity.principal_for(config, "", commands.principal())
    if key and invite:
        enrol.redeem(target, invite, who, enrol.pubkey(key))
    return identity.establish(root, host, config, key, who, refusal=NO_KEY)


def _compare(events: list[Event], answer: dict[str, Any]) -> str | None:
    """Step 4, and `None` means every row agreed. Per KIND and not just a total:
    a total that matches while the mix does not is the interesting failure.

    The remote side is READ BACK from the server's store and counts the events of
    THIS push only — a board created for one already holds its own birth
    certificate, and possibly a visibility or a remote set before it was filled
    (`http/ingest.py::_configuration`), so comparing the board's whole size
    against this log's would be off by one on every correct push there is."""
    mine = Counter(event["kind"] for event in events)
    theirs = {str(k): int(v) for k, v in as_object(answer.get("kinds")).items()}
    rows = [("events", len(events), int(answer.get("landed", 0)))]
    rows += [(kind, mine.get(kind, 0), theirs.get(kind, 0)) for kind in sorted(mine | theirs)]
    table = "\n".join(f"  {label:<18} local {a:>6}   remote {b:>6}" for label, a, b in rows)
    return None if all(a == b for _, a, b in rows) else table


def _flip(root: Path, host: str, name: str, token: str, door: dict[str, str] | None) -> None:
    """Step 5, and the only step that changes what this repo reads. The `login`
    block travels with it whenever there is one, so the session that carried the
    push keeps refreshing itself afterwards — without it the token in the file
    would be a standing one nobody can renew, and the first thing this repo did
    after being promoted would be to expire."""
    expires = float(read_config(root).get("token_expires", 0.0) or 0.0)
    write_config(root, f"{host.rstrip('/')}/{name}", token, door, expires)
    archived = archive(root / DIR / "board")
    print(f"{root / DIR}/board.json now points at {host}/{name}")
    print(f"  the local board is archived at {archived} — nothing was deleted")


def archive(local: Path) -> Path:
    """`.taskops/board/` → `.taskops/board.local-<date>/`, never a delete. Shared
    with `taskops join --discard-local` (`commands.py`), the same moment from the
    other side: a local history about to stop being the one this repo reads."""
    if not local.exists():
        return local
    stamp = _clock.datestamp(_clock.now())
    for suffix in ("", *(f"-{n}" for n in range(2, 100))):
        target = local.with_name(f"{local.name}.local-{stamp}{suffix}")
        if not target.exists():
            local.rename(target)
            return target
    raise TaskopsError(f"cannot archive {local}: 99 archives from today are already beside it")
