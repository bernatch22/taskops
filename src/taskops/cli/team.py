"""The forge SYNC: the repo's collaborators become principals, in one batch.

    taskops board forge bernatch22/taskops
      -> declares the fact (the board's event) …and then syncs the team:
         GET /repos/…/collaborators?permission=push   (the owner's token, once)
         GET github.com/<login>.keys                  (public, per person)
         POST /rpc members.enroll {members: [...]}     (one call, adds only)

**Declaring and syncing are one command because they are one intention.** The
owner who names the repo means "these people work here"; a second verb to make
that true would be a second thing to forget, and re-running this one is how a
team stays in step — the batch is idempotent by SKIPPING (`http/members.py`), so
a sync that changes nothing writes nothing and says so.

**Nothing is ever revoked from here, and that is the milestone's own decision.**
A principal enrolled by an invite has no reason to appear in a collaborator
list, so a sync that pruned would revoke `ana` for having been introduced the
other way. What this prints instead is the DRIFT — every principal the host
holds that the batch did not name, with the exact `taskops revoke --key` beside
it — and a human decides. The owner is never in that list: they are the person
running the command.

**Nobody is dropped in silence.** A collaborator whose GitHub account publishes
no ssh key cannot be enrolled — there is nothing to enrol — and is NAMED with
`taskops invite <login>`, because a team of nine reported as eight is a bug
somebody finds three weeks later. The same holds for a bot, which is not a
person and has no key to publish.

The token never appears here at all: `github.py` reads it, spends it on the
collaborator pages, and this module only ever sees logins.
"""

from __future__ import annotations

from typing import Any, Callable

from . import github
from .._json import as_rows, as_object, as_strings

Send = Callable[[str, dict[str, Any]], dict[str, Any]]
"""How this module reaches the host: `operate.call` with the host and the
session already bound. Passed in rather than imported so the sync knows nothing
about transport, sessions or `--key`, and `operate.py` keeps its own budget."""


def sync(fact: dict[str, Any], send: Send) -> None:
    """Ask GitHub who works here, enrol them, print what that changed."""
    repo, need = str(fact["repo"]), str(fact["need"])
    logins = [name.lower() for name in github.collaborators(repo, need, github.token())]
    batch: list[dict[str, Any]] = []
    keyless: list[str] = []
    for login in sorted(set(logins)):
        keys = github.keys_of(login)
        (batch.append({"principal": login, "keys": keys}) if keys else keyless.append(login))
    print(f"  {len(logins)} collaborator(s) with {need} on {repo}")
    done = send("members.enroll", {"members": batch}) if batch else {}
    _enrolled(as_object(done))
    _keyless(keyless)
    _drift(as_rows(done.get("others")))


def _enrolled(done: dict[str, Any]) -> None:
    """What the host did, in its own words. `unchanged` is printed because a
    re-run whose whole output was blank reads as a command that did not work."""
    added = as_rows(done.get("added"))
    for name in ("enrolled", "unchanged"):
        who = as_strings(done.get(name))
        if who:
            print(f"  {name:<9} {', '.join(who)}")
    if added:
        print(f"  keys      {len(added)} added")
    for row in as_rows(done.get("skipped")):
        print(f"  skipped   {row.get('principal')} {row.get('fingerprint')} — {row.get('why')}")


def _keyless(keyless: list[str]) -> None:
    """The people GitHub knows and this host cannot: named, with the way in."""
    if not keyless:
        return
    print(f"  no ssh key published on GitHub — {len(keyless)}, not enrolled:")
    for login in keyless:
        print(f"    {login:<24} github.com/{login}.keys is empty — taskops invite {login}")


def _drift(others: list[dict[str, Any]]) -> None:
    """Reported, never acted on. The owner is skipped: the account running this
    sync is not drift, and a `revoke` line beside it is an invitation to lock
    yourself out of your own host."""
    rows = [row for row in others if str(row.get("role", "")) != "owner"]
    if not rows:
        return
    print(f"  on this host but NOT a collaborator any more — {len(rows)}, nothing revoked:")
    for row in rows:
        for fingerprint in as_strings(row.get("keys")):
            print(f"    {row.get('principal'):<24} taskops revoke --key {fingerprint}")
    print("    a principal introduced by invite belongs here legitimately — revoking is yours")
