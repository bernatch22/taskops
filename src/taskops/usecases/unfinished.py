"""What a stopping session still owes the board — the judgement behind the stop-time net.

An agent that claims a card, commits into it, and then simply ENDS leaves the board saying
"somebody is working on this" about nobody. The lease lapses fifteen minutes later and
`recover` returns the card, but everything the agent knew — what it did, what is left, what it
learned — dies with the turn. The cheapest moment to catch that is the stop itself, while the
agent is still there to answer.

This module only JUDGES. The hook transport turns the verdict into Claude Code's block shape;
nothing here knows what a hook is, which is what keeps it testable with a Store and a string.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._project import project

__all__ = ["owed", "should_block", "BLOCK_LIMIT", "COUNTS_FILE"]

BLOCK_LIMIT = 2
"""How many times one card may hold one session at the door. The third time it walks.

A block is a message to an agent, and an agent that has read it twice and still not acted is
not going to act on the third copy — it is confused, out of budget, or arguing. Holding it
forever would trade a stale board for a trapped session, which is a worse failure owned by us
instead of a smaller one owned by the agent. The walk-away is COMMENTED on the card, so the
board says "left without closing" instead of silently reading `claimed`."""

COUNTS_FILE = "stop-blocks.json"
"""Under `.taskops/`, beside `sweep.stamp` and covered by the same gitignore block: per-machine
bookkeeping, meaningless to a teammate, noise in a diff."""


def owed(start: Path | str, session: str, agent_type: str = "") -> list[dict[str, Any]]:
    """The cards this session still holds half-done: agent-held, claimed or in_progress.

    Keyed on the SESSION, not the actor, because the hook payload carries a session id and an
    agent type but never a taskops actor — and the lease already remembers which session
    stamped it (`track` writes it on every tool call precisely so conversations stay findable).

    `agent_type` narrows to the subagent that is actually stopping: workers run in parallel,
    and blocking a verifier over a WORKER's half-done card would hold the wrong door. A type
    that matches no lease means the stopper holds nothing — let it go.

    `dev:` leases are never listed. A person closes their terminal when they please.
    """
    with project(start) as store:
        held = store.leases.of_session(session)
        rows: list[dict[str, Any]] = []
        for lease in held:
            card = store.tasks.get(lease["task"])
            if card is None or card["status"] not in ("claimed", "in_progress"):
                continue
            if not lease["actor"].startswith("agent:"):
                continue
            if agent_type and not lease["actor"].rsplit("/", 1)[-1].startswith(agent_type):
                continue
            commits = store.events.of_task(card["id"], kinds=("commit",))
            rows.append({"task": card["id"], "actor": lease["actor"], "title": card["title"],
                         "status": card["status"], "commits": len(commits),
                         "branch": lease["branch"]})
        return rows


def should_block(start: Path | str, session: str, task_id: str) -> bool:
    """True while this card has held this session at the door fewer than BLOCK_LIMIT times.

    The count SURVIVES in a file rather than in memory because each hook invocation is a fresh
    process — an in-memory counter would reset on every check and block forever.
    """
    with project(start) as store:
        path = store.root / ".taskops" / COUNTS_FILE
        counts = _read(path)
        key = f"{session}:{task_id}"
        counts[key] = counts.get(key, 0) + 1
        path.write_text(json.dumps(counts), encoding="utf-8")
        return counts[key] <= BLOCK_LIMIT


def _read(path: Path) -> dict[str, int]:
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
    except (OSError, ValueError):
        return {}
