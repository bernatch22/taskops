"""post-commit — put the commit on its card, push the card's own branch.

The bind is what the `done` guard asks for, so losing one means a card that can
never close. In v1, when the server was down the bind was lost FOREVER; here it
lands in `.taskops/pending.jsonl` and the next call drains it. The events are
content-addressed, so draining twice costs nothing.

The push is `origin <tk-…>` — the card's own branch. Never `main`, never
`--force`. Integration is a separate, deliberate act by the orchestrator.
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from pathlib import Path

from . import run, trailer
from .._errors import TaskopsError

PENDING = Path(".taskops") / "pending.jsonl"


class Caller(Protocol):
    """Just enough of a board to record a fact — the hook never needs more."""

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]: ...


def commit_facts(repo: Path, ref: str = "HEAD") -> dict[str, Any] | None:
    """Everything about the commit that just happened. None only if it is not a
    commit at all. A commit with NO card is still facts — `task` is "" and the
    board records it at project level: nobody is forced to take a card to
    commit; taskops just knows that this sha happened outside any card."""
    raw = run.git("show", "-s", "--format=%H%n%ct%n%s", ref, cwd=repo)
    if not raw.ok:
        return None
    lines = raw.out.splitlines()
    if len(lines) < 3:
        return None
    sha, when, subject = lines[0], lines[1], lines[2]
    body = run.git("show", "-s", "--format=%B", ref, cwd=repo).out
    branch = run.branch_at(repo)
    card = trailer.card_in(body) or trailer.card_of(branch)
    files = run.git("show", "--name-only", "--format=", ref, cwd=repo).out.splitlines()
    return {
        "task": card,
        "sha": sha,
        "subject": subject,
        "files": [f for f in files if f],
        "branch": branch,
        "ts": float(when),
    }


def record(board: Caller, repo: Path, facts: dict[str, Any]) -> bool:
    """Tell the board. Queue instead of losing it — and say so on stderr."""
    try:
        board.call("bind", facts)
    except TaskopsError as err:
        queue(repo, facts)
        raise TaskopsError(
            f"taskops: the board did not take {facts['sha'][:8]} ({err}). "
            f"It is queued in {PENDING} and the next taskops call will send it."
        ) from err
    return True


def queue(repo: Path, facts: dict[str, Any]) -> None:
    path = repo / PENDING
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(facts) + "\n")


def drain(board: Caller, repo: Path) -> int:
    """Send whatever the queue holds. Called by every MCP tool, cheap when empty."""
    path = repo / PENDING
    if not path.exists():
        return 0
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    left: list[str] = []
    sent = 0
    for line in lines:
        try:
            facts: Any = json.loads(line)
            board.call("bind", facts)
            sent += 1
        except TaskopsError:
            left.append(line)  # still unreachable: keep it for the next call
        except ValueError:
            continue  # a corrupt line is not worth keeping forever
    if left:
        path.write_text("\n".join(left) + "\n", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return sent


def push_card(repo: Path, branch: str) -> bool:
    """Publish the card's branch so a PR (or the orchestrator) can see it."""
    if not trailer.card_of(branch):
        return False
    return run.git("push", "--set-upstream", "origin", branch, cwd=repo).ok
