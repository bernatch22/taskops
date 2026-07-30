"""One sha, one binding.

Split from `ingest` on its budget, and the split is honest: that module reads git and decides
what to record, this answers whether it was recorded already.
"""

from __future__ import annotations

from ..storage import Store

__all__ = ["already_bound"]


def already_bound(store: Store, task: str, sha: str) -> bool:
    """Has this exact commit already been bound to this card?

    ONE sha, ONE binding. Two doors lead here — the installed `post-commit` hook and an
    explicit call — and `--no-verify` closes only the first of them, so the two fire together
    more often than not. The events are content-hashed but carry a timestamp, so two
    recordings a second apart are two different ids and the board counted the same commit
    twice: `done` then has "evidence" it never earned, and a diff-size roll-up doubles.
    """
    return any(event["body"].get("sha") == sha
               for event in store.events.of_task(task, kinds=("commit",)))


