"""POST /rpc — the SERVER's own verbs: create a board, list them, invite, revoke.

    {"verb": "board.create", "args": {"name": "facturador"}}
    -> {"ok": true, "seq": 0, "data": {...}}          the SAME envelope as a board call

The anomaly this file closes: until it existed, every admin act escaped the CLI
into an ssh session. The machinery was already right (`store/creds.py` mints,
`Mounts.create` makes a board); what was missing was a DOOR onto it that a key
could open from a laptop. The on-box commands survive as break-glass (README).
`board.ingest` — a whole local history, once — lives in `ingest.py`, because
its preconditions are longer than the verb; `board.remove` lives in `removal.py`
for the same reason, and because it is the only one of these that destroys.

**Why the root `/rpc` and not `/admin/rpc`.** A board name is `[a-z0-9-]`
(`mounts.py::NAME`), so `admin` is a legal board and `/admin/rpc` would be that
board's own door, character for character — and the day somebody created one
called `admin` the server scope would quietly shadow it. A board call has TWO
segments; this door has one, so no board name can collide with it.

**Two registries, on purpose, and this one is not `verbs/__init__.py`.** A board
verb answers "what may this ACTOR do to a card" (`core/actors.py`); these answer
"what may this PRINCIPAL do to the HOST" — `core/scope.py`'s question, owner /
member / anon. One table would mean one refusal naming two different walls.

Authentication is the session token alone: `/login` mints it against an ssh key
(`login.py`) scoped to board `*`, so a board-scoped invite token cannot open
this door — `check(token, "*", …)` can never match one.
"""

from __future__ import annotations

from typing import Any

from . import grants, ingest, mounts as _mounts, removal
from .. import verbs
from .auth import Credential
from ..core import scope
from .._json import as_object
from .mounts import Mounts
from .scoped import Call, Verb, text as _text
from .._errors import Refused, BadRequest
from ..core.event import make
from ..core.types import PROJECT

NO_SESSION = (
    "operating this host needs a SESSION, which an ssh key mints: join with "
    "`taskops join <url>?invite=… --key ~/.ssh/id_ed25519` and every call signs itself in"
)


def answer(mounts: Mounts, token: str, body: dict[str, Any], now: float) -> dict[str, Any]:
    """One server-scope call: authenticated, then authorized, then run.

    The order is the point — the credential proves WHO, the server store says what
    that principal IS here, and `scope.permit` decides AND words the refusal, so a
    member calling an owner verb is refused naming the role that may."""
    verb = _verb_of(body)
    who = _session(mounts, token, verb.need, now).subject
    role = mounts.host.store().role_of(who.partition(":")[2])
    scope.permit(verb.operation, role)
    return verb.run(Call(mounts, who, role, as_object(body.get("args", {})), now))


def _create(call: Call) -> dict[str, Any]:
    """THE way a board comes to exist, and the only one that records a creator.
    The refusal on an existing name is not politeness: `Mounts.create` is
    `mkdir(exist_ok=True)`, so without it "creating" a live board would answer ok
    and hand somebody else's history back as if it were new."""
    name = _mounts.named(_text(call.args, "name"))
    if (call.mounts.root / name).is_dir():
        raise Refused(
            f"this host already has a board named {name!r} — pick another name; "
            "a board is never created over one that exists"
        )
    stores = call.mounts.create(name)
    # WHO made it, as the board's first event. Nothing else ever records this:
    # a creator is not derivable from a log that starts after the creation.
    fact = {"op": "created", "value": {"by": call.actor}}
    stores.write([make(PROJECT, call.actor, "project", fact, call.now)])
    return {"board": name, "created_by": call.actor, "seq": stores.head()}


def _visibility(call: Call) -> dict[str, Any]:
    """PUBLIC or PRIVATE, GitHub's flag — recorded on the BOARD, not on the host.

    It goes through `verbs.call` and not through `make()` beside `_create`
    above, and that difference is deliberate: `verbs/project.py` owns the op
    table, the two legal values and the rule that re-recording an unchanged
    value writes NOTHING. Reaching past it would put a second spelling of
    "public" in this file, and the day they disagree a board is readable by one
    of them and not the other.
    """
    name = _mounts.named(_text(call.args, "board"))
    call.mounts.check(name)
    args = {"op": "visibility", "visibility": _text(call.args, "visibility")}
    out = verbs.call(call.mounts.stores(name), "project", call.actor, args)
    wanted = as_object(out.get("value")).get("visibility")
    return {"board": name, "visibility": wanted, "recorded": out.get("recorded"), "by": call.actor}


def _list(call: Call) -> dict[str, Any]:
    """Everything, for the owner; a member's own boards, for a member.
    "Their own" is DERIVED and not a membership table: a board somebody holds a
    live credential for is a board they are on (`store/creds.py::boards`)."""
    mine = call.mounts.credentials.boards(call.actor)
    held = call.mounts.root.iterdir()
    names = sorted(p.name for p in held if p.is_dir() and _mounts.NAME.match(p.name))
    if call.role != scope.ROLE_OWNER:
        names = [name for name in names if name in mine]
    return {"boards": [_summary(call.mounts, name) for name in names], "role": call.role}


def _ingest(call: Call) -> dict[str, Any]:
    """A whole local history, moved onto an EMPTY board. `ingest.py` is the wall."""
    return ingest.run(call.mounts, call.args)


def _remove(call: Call) -> dict[str, Any]:
    """A board off this host, whole. `removal.py` is the wall — and this is the
    only verb here that destroys, which is why the guardrail (does anything else
    still hold this history?) is a module and not a line."""
    return removal.run(call.mounts, call.args, call.actor)


REGISTRY: dict[str, Verb] = {
    "board.create": Verb("board.create", "write", _create),
    "board.list": Verb("board.list", "read", _list),
    "board.visibility": Verb("board.visibility", "write", _visibility),
    "board.ingest": Verb("board.ingest", "write", _ingest),
    "board.remove": Verb("board.remove", "write", _remove),
    "invite.mint": Verb("invite.mint", "write", grants.mint),
    "key.revoke": Verb("key.revoke", "write", grants.revoke_key),
    "invite.revoke": Verb("invite.revoke", "write", grants.revoke_invite),
}


def _verb_of(body: dict[str, Any]) -> Verb:
    verb = body.get("verb")
    if not isinstance(verb, str) or verb not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise BadRequest(f"this host's own verbs are: {known}")
    return REGISTRY[verb]


def _session(mounts: Mounts, token: str, need: str, now: float) -> Credential:
    """A `*`-scoped session and nothing else. `Credentials.check` answers in a
    BOARD's words, so the way in is APPENDED rather than the reason replaced."""
    if not token:
        raise Refused(f"no credential — {NO_SESSION}")
    try:
        return mounts.credentials.check(token, "*", need, now)
    except Refused as err:
        raise Refused(f"{err}. {NO_SESSION}") from err


def _summary(mounts: Mounts, name: str) -> dict[str, Any]:
    """Enough to choose one from a list. `active` is the log's mtime — one stat,
    and the log is append-only."""
    stores = mounts.stores(name)
    active = stores.log_path.stat().st_mtime if stores.log_path.exists() else 0.0
    cards = len(stores.state()["cards"])
    return {"name": name, "cards": cards, "seq": stores.head(), "active": active}
