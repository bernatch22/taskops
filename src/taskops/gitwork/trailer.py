"""prepare-commit-msg — stamp `Task: tk-…` and never, ever refuse.

The trailer is the one link between a commit and its card that survives a
squash, a rebase and a cherry-pick. It goes after a BLANK LINE, because that is
what makes git parse it as a real trailer; v1 appended it flush against the
body and `git log --grep`/`--format=%(trailers)` never saw it.

If anything here fails, the commit still happens — without a trailer, with the
reason on stderr. A hook that can block a commit is a hook that will, on the
worst possible day (v1's `pre-commit`, bricking commits when the venv moved).
"""

from __future__ import annotations

from pathlib import Path

from .._ids import is_task_id

KEY = "Task:"


def card_of(branch: str) -> str:
    """`tk-a1b2c3` → the card. A milestone or trunk branch has no card."""
    name = branch.rpartition("/")[2]
    return name if is_task_id(name) else ""


def stamped(message: str, card: str) -> str:
    """Idempotent: re-running the hook (git commit --amend) adds nothing twice."""
    if not card:
        return message
    body = message.rstrip("\n")
    for line in body.splitlines():
        if line.strip() == f"{KEY} {card}":
            return message
    separator = "\n\n" if body and not body.endswith("\n\n") else ""
    return f"{body}{separator}{KEY} {card}\n"


def stamp_file(path: Path, branch: str) -> bool:
    """Rewrite the commit message file in place. True if a trailer was added."""
    card = card_of(branch)
    if not card:
        return False
    original = path.read_text(encoding="utf-8")
    updated = stamped(original, card)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def card_in(message: str) -> str:
    """Read the trailer back — this is how post-commit knows which card to bind."""
    for line in reversed(message.splitlines()):
        if line.startswith(KEY):
            candidate = line[len(KEY) :].strip()
            if is_task_id(candidate):
                return candidate
    return ""
