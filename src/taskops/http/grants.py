"""The server-scope verbs that hand a credential out, or take one back.

Split off `admin.py` at the 200-line budget, and the seam is a noun and not a
line count: everything here is about a GRANT — an invite minted, an invite
revoked, a key revoked — while what is left there is about BOARDS: created,
listed, published, ingested. The registry stays whole in `admin.py`, which is
the file's own rule (one table, one refusal per operation); these are the
implementations it points at.

Both revocations check FIRST and refuse by name. An `UPDATE` that matches
nothing is a silent success in SQL, so a mistyped id or fingerprint used to
print `revoked` and leave the credential live — the worst possible answer to
"has this key stopped working".
"""

from __future__ import annotations

from typing import Any

from .scoped import Call, text
from .._errors import Refused
from ..store.creds import WEEK


def mint(call: Call) -> dict[str, Any]:
    """The same mint the on-box `taskops invite` runs — reached over the API.
    The board is checked FIRST, so an invite is never minted for a name this host
    does not serve: that token would be handed to a teammate and fail at their
    `join`, a day later and a machine away from the typo."""
    who, board = text(call.args, "who"), text(call.args, "board")
    call.mounts.check(board)
    token, credential = call.mounts.credentials.mint(
        f"invite:{who}", board, call.now, ttl=WEEK, once=True
    )
    return {
        "id": credential.id,
        "token": token,
        "board": board, "who": who, "expires": call.now + WEEK,
    }



def revoke_key(call: Call) -> dict[str, Any]:
    """A key stops signing anybody in, and `allowed_signers` is rewritten whole
    by the store — so revoking is one row and the file follows."""
    wanted = text(call.args, "key")
    store = call.mounts.host.store()
    held = [key for key in store.keys(live=False) if key.fingerprint == wanted]
    if not held:
        raise Refused(
            f"no key {wanted!r} on this host — `taskops board ls` names the host; "
            "a fingerprint is what `ssh-keygen -lf <path.pub>` prints (SHA256:…)"
        )
    store.revoke_key(wanted)
    return {"fingerprint": wanted, "principal": held[0].principal, "revoked": True}


def revoke_invite(call: Call) -> dict[str, Any]:
    """An UPDATE that matches nothing is a silent success, so the id is checked
    first: a typo used to print `revoked` and leave the credential live."""
    ident = text(call.args, "invite")
    subject = call.mounts.credentials.subject_of(ident)
    if not subject:
        raise Refused(
            f"this host minted no credential {ident!r} — the id is the one "
            "`taskops invite` printed beside the link"
        )
    call.mounts.credentials.revoke(ident)
    return {"id": ident, "subject": subject, "revoked": True}
