"""Minting and redeeming invites — the per-person way into a board with no GitHub behind it.

Server-side, both halves, because they are one rule read from two ends: what makes a code valid
is what makes it disappear. Splitting them would be two definitions of "used".

**Redeeming mints an ordinary session.** That is the whole reason this is small: sessions
already exist, already expire, already carry a name and a list of boards, and the mount already
swaps one for the board's token before any route sees it. An invite is therefore a way to GET a
session, not a fourth kind of credential — nothing downstream learns a new word.

**Pruned on every write, never on a timer.** Same discipline as the sessions file: an expired
invite is invisible the moment it is old enough and leaves the disk the next time anybody mints
one. No sweeper, no daemon, and "an expired invite is refused" stays true on a server nobody
has written to in a month.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from .._clock import now
from .._errors import BadRequest
from ..contracts.invite import INVITE_FILE, INVITE_TTL, Invite
from ._sessions import mint

__all__ = ["offer", "redeem", "withdraw", "pending", "CODE_BYTES"]

CODE_BYTES = 16
"""128 bits, hex — the same size the board token uses, and for the same reason: short enough to
paste into a message, long enough that the 404 is the only way to look for one."""


def offer(board: Path, who: str, by: str) -> str:
    """Mint an invite for `who` and return the code — the ONLY time it exists in plain text.

    Re-inviting the same person REPLACES their pending code rather than adding a second, so a
    person who lost the message gets a working one instead of two live doors with one name.
    """
    name = who.strip().lstrip("@")
    if not name or "/" in name or ":" in name:
        raise BadRequest(f"`{who}` is not a name to invite — a bare handle, like `ana`. The "
                         f"board will record them as `dev:{name or '<name>'}`.")
    code = secrets.token_hex(CODE_BYTES)
    live = [i for i in pending(board) if i["who"] != name]
    live.append(Invite(who=name, digest=_digest(code), by=by, created=now()))
    _write(board, live)
    return code


def redeem(root: Path, name: str, code: str) -> dict[str, str]:
    """Spend an invite: returns `{login, session}`, or refuses without saying which part failed.

    An unknown code and an expired one get ONE answer on purpose. Telling them apart says
    whether a guessed string was ever real, which is the only thing a guesser learns from.
    """
    board = root / name
    wanted = _digest(code.strip())
    found = next((i for i in pending(board) if i["digest"] == wanted), None)
    if found is None:
        raise BadRequest("that invite is not valid — it may have been used already, withdrawn, "
                         "or expired. Ask whoever invited you for a fresh one.")
    _write(board, [i for i in pending(board) if i["digest"] != wanted])   # single use
    return {"login": found["who"], "session": mint(root, found["who"], [name])}


def withdraw(board: Path, who: str) -> bool:
    """Take back an invite before it is spent. True when there was one."""
    live = pending(board)
    left = [i for i in live if i["who"] != who.strip()]
    if len(left) == len(live):
        return False
    _write(board, left)
    return True


def pending(board: Path) -> list[Invite]:
    """Every invite still live — unexpired, unredeemed. Never the codes: they are not here."""
    try:
        raw = json.loads((board / INVITE_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw if isinstance(raw, list) else []
    fresh = now() - INVITE_TTL
    return [Invite(who=str(r.get("who", "")), digest=str(r.get("digest", "")),
                   by=str(r.get("by", "")), created=float(r.get("created", 0)))
            for r in rows if isinstance(r, dict) and float(r.get("created", 0)) > fresh]


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _write(board: Path, live: list[Invite]) -> None:
    """`0600` at CREATION, like every other secret-adjacent file here: a `write_text` followed
    by a `chmod` publishes the contents to every account on the box for one syscall."""
    path = board / INVITE_FILE
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(json.dumps(live, indent=1) + "\n", encoding="utf-8")
