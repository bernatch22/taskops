"""`members.enroll` — a whole team enrolled in ONE call, by the OWNER, adding only.

    POST /rpc {"verb": "members.enroll", "args": {"members": [
        {"principal": "ana", "keys": ["ssh-ed25519 AAAA…", …]}, …]}}
    -> {"enrolled": ["ana"], "added": [{"principal": "ana", "fingerprint": "SHA256:…"}],
        "unchanged": ["berna"], "skipped": [{"principal": …, "fingerprint": …, "why": …}],
        "others": [{"principal": "leo", "role": "member", "keys": ["SHA256:…"]}],
        "signers": 3}

**This operation does not know what GitHub is.** It receives principals and ssh
key lines; who those people are, and how their keys were discovered, belongs to
the caller — `taskops board forge` asks a forge with the owner's own token and
that token dies with the outgoing call. Keeping the host ignorant is what keeps
the chapter's rule cheap: there is no token to store here because none arrives.

**The enrolment itself is `login.register`, called and not copied.** The invite
door, and this one, must leave the host in the same state or "how somebody got
in" becomes a second thing to reason about. `register` creates an unknown
principal as `member` and only ever ADDS a key to a known one, which is why a
re-run over the owner leaves the owner an owner (`store/server.py::enroll` is an
INSERT OR REPLACE on `principals`, so reaching past `register` to it would
silently rewrite a role — the bug pinned by
`test_a_re_join_never_demotes_the_owner_it_only_adds_a_key`).

**Idempotent, and by SKIPPING rather than by rewriting.** A key already live for
its principal is not written again: a batch re-run touches no row, so
`allowed_signers` — regenerated whole by the store on every key it does write —
comes out of the second run identical to the first. Two keys are deliberately
NOT written, and both are reported instead of being silently obeyed:

* a fingerprint the owner REVOKED. The next sync would otherwise resurrect it,
  which makes revocation a thing that lasts until the next cron run.
* a fingerprint another principal already holds. `pubkeys.fingerprint` is the
  primary key, so writing it would MOVE the key — the other person keeps their
  own principal, and the person it was taken from silently loses a key they sign
  with. A batch is not allowed to do that to somebody who is not in it.

**Nothing is ever revoked here**, and the reason is in the milestone's own goal:
a principal enrolled by invite has no reason to appear in a forge's collaborator
list, and a sync that never heard of them would revoke them for existing. So the
answer carries `others` — every principal this batch did NOT name, with their
live fingerprints — as the raw material for the caller's drift report, and the
decision to revoke stays a separate act by a human (`taskops revoke --key`).

The batch is validated WHOLE before a single row is written. A malformed key in
the tenth entry would otherwise leave nine enrolled and the command re-run
against a half-applied host.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from . import login
from .._json import as_rows, as_strings
from .scoped import Call
from .._errors import BadRequest
from ..store.server import ServerStore
from ..store.pubkeys import parse_key, fingerprint, principal_name

SHAPE = (
    'this call needs members=[{"principal": "<name on this host>", '
    '"keys": ["ssh-ed25519 AAAA…"]}, …] — one entry per person, keys never empty'
)


class Member(NamedTuple):
    """One validated entry: a legal principal name and its keys, already named."""

    principal: str
    keys: tuple[tuple[str, str], ...]  # (keyline, fingerprint)


def enroll(call: Call) -> dict[str, Any]:
    """Enrol every (principal, key) in the batch, and say what that changed."""
    batch = read(call.args)
    store = call.mounts.host.store()
    enrolled: list[str] = []
    added: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for entry in batch:
        _one(call, store, entry, enrolled, added, skipped)
    touched = {row["principal"] for row in added}
    return {
        "enrolled": enrolled,
        "added": added,
        "unchanged": [entry.principal for entry in batch if entry.principal not in touched],
        "skipped": skipped,
        "others": _others(store, {entry.principal for entry in batch}),
        "signers": len(store.keys()),
    }


def _one(
    call: Call,
    store: ServerStore,
    entry: Member,
    enrolled: list[str],
    added: list[dict[str, str]],
    skipped: list[dict[str, str]],
) -> None:
    """One person's keys. The verdict is taken against the store as it stands at
    THAT key, not against a snapshot, so the same key line twice inside one entry
    is written once and reported neither time."""
    known = store.principal(entry.principal) is not None
    for keyline, named in entry.keys:
        write, why = _verdict(store, entry.principal, named)
        if why:
            skipped.append({"principal": entry.principal, "fingerprint": named, "why": why})
        if not write:
            continue
        login.register(call.mounts.host, entry.principal, keyline, call.now)
        if not known:
            enrolled.append(entry.principal)
            known = True
        added.append({"principal": entry.principal, "fingerprint": named})


def _verdict(store: ServerStore, who: str, named: str) -> tuple[bool, str]:
    """(write it?, why not). A key already LIVE for this principal is
    `(False, "")` — nothing to do and nothing to report, which is exactly what
    makes a re-run of the same batch touch no row and rewrite no file."""
    for key in store.keys(live=False):
        if key.fingerprint != named:
            continue
        if key.principal != who:
            return False, (
                f"{key.principal} already holds this key on this host — writing it would "
                f"move the key off {key.principal}; two principals cannot share a fingerprint"
            )
        if key.revoked:
            return False, (
                "this key was revoked here, and a sync does not undo a revocation — "
                f"the owner re-adds it deliberately or {who} publishes a new one"
            )
        return False, ""
    return True, ""


def _others(store: ServerStore, named: set[str]) -> list[dict[str, Any]]:
    """Every principal the batch did NOT name — the caller's drift, reported and
    never acted on. Their live fingerprints travel too, because the command that
    retires one takes a fingerprint and a report you have to go and look things
    up for is a report nobody runs twice."""
    return [
        {
            "principal": held.name,
            "role": held.role,
            "keys": [key.fingerprint for key in store.keys(held.name)],
        }
        for held in store.principals()
        if held.name not in named
    ]


def read(args: dict[str, Any]) -> list[Member]:
    """The batch, validated WHOLE — names and key grammar — before anything is
    written. Refusing here is what makes a re-run safe after a typo."""
    rows = as_rows(args.get("members"))
    if not rows:
        raise BadRequest(SHAPE)
    batch: list[Member] = []
    for row in rows:
        who = principal_name(str(row.get("principal", "")).strip())
        lines = [line for line in as_strings(row.get("keys")) if line.strip()]
        if not lines:
            raise BadRequest(
                f"{who} came with no key, and a principal with no key can sign nothing — "
                f"leave them out of the batch and invite them: taskops invite {who}. {SHAPE}"
            )
        batch.append(Member(who, tuple((line, _named(line)) for line in lines)))
    return batch


def _named(keyline: str) -> str:
    """The fingerprint — and, on the way, the grammar check that refuses a
    private key or a paste of something that is not a key at all."""
    return fingerprint(parse_key(keyline)[1])
