"""The sentence a project reads the moment its board stops being local.

Said once, by every door that attaches a remote, because the change it announces is invisible
and permanent: from that point every write executes in the server's store and every read comes
from it, so `.taskops/events.jsonl` — the file the whole architecture calls TRUTH — stops
growing. It does not become wrong; it becomes a FOSSIL of everything up to the migration, and a
person who opens it next month reads a board that ended the day they went remote.

Nothing is deleted here, and that is deliberate. The log is the only copy of the pre-remote
history until `push` has run, `.taskops/` may hold reports somebody wrote, and a tool that
removes a committed file to tidy up is a tool nobody trusts twice. What it does instead is say
what changed and name the one command that makes git stop tracking a cache — which is what
every project whose board lives on a server ends up doing, and what the topology test itself
does, because a clone permanently dirty is a clone `land` and `git switch` refuse to work in.
"""

from __future__ import annotations

__all__ = ["moved_note"]


def moved_note(url: str) -> str:
    """What to print under a `remote add` or a `board create`."""
    return "\n".join([
        "",
        f"  ⚠  this board now lives at {url}.",
        "     Every write goes there and every read comes from there — nothing to push, and",
        "     nothing to remember. But .taskops/events.jsonl STOPS growing here: it keeps the",
        "     history up to this moment and nothing after it. The server's log is the truth now.",
        "",
        "     Most projects stop tracking the cache once their board is hosted:",
        "         echo '.taskops/' >> .gitignore && git rm -r --cached .taskops",
        "     Keep it if you want the pre-remote history in git — it is still readable.",
    ])
