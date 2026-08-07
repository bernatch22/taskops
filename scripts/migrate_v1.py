#!/usr/bin/env python3
"""Migrate a v1 board's events.jsonl into a fresh v2 board.

    uv run python scripts/migrate_v1.py <v1 events.jsonl> <new board dir> \\
        --milestone "axion — imported from taskops v1" \\
        --goal "history migrated from the pre-v2 board; see MIGRATION.md"

v1 stored more kinds than v2 does. The mapping, and why:

    claimed, comment, commit          → same kind, same shape
    done, status(to=done|dropped)     → status                 (v1 split "done" out; v2 doesn't)
    status(to=ready|backlog|claimed)  → released                (v1's "back to the pool" was a status; v2's is its own kind)
    blocked {"on": <task>}            → edited(after=[...])     (v1 stored blocking as a fact; v2 DERIVES it from `after` — this
                                                                   is the one mapping that changes MEANING, not just shape: a v1
                                                                   `blocked` never un-derives itself if the blocker is dropped
                                                                   instead of closed, this one does)
    handoff {"assigned_to", "mentions"}→ edited(assignee=…)     (v1's dispatch marker; the original plan said to drop this —
                                          + comment(mentions)      kept instead, see MENTIONS.md §5. Assignment already
                                                                   says "this is yours", so the assignee needs no mention; anybody
                                                                   ELSE the handoff looped in gets a companion comment, or that
                                                                   second person is silently dropped — which is what v1 did here)
    message {"text": …, "mentions"}   → comment {text, mentions}(both kept: v2 carries mentions as an extra key on a `comment`
                                                                   body, and `core/mentions.py` derives what is still unanswered)
    branch, activity                  → DROPPED (the v1 anti-patterns v2 exists to not have: a slug baked into a branch name,
                                          and local-only activity timestamps that undercounted hours on every rebuild)
    acceptance, policy, context,      → DROPPED (v1's review-gate machinery; v2 has no reviewer role, see CLAUDE.md)
    landed, review, eval, inferred

Every card lands in ONE new milestone (v1 let a card have none; v2 requires
one) — pass --milestone/--goal or accept the default. Unknown kinds are
counted and reported, never silently eaten.
"""

from __future__ import annotations

import sys
import json
import argparse
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from taskops._ids import new_milestone_id  # noqa: E402
from taskops.core.event import make  # noqa: E402
from taskops.core.types import PROJECT, Event, slugify  # noqa: E402
from taskops.store.stores import Stores  # noqa: E402

# v1 kind -> what to do. A function takes (body, ctx) and yields v2 (kind, body) pairs.
DROP_SILENT = {"branch", "activity", "acceptance", "policy", "context", "landed",
                "review", "eval", "inferred", "unblocked"}


class Ctx:
    """Per-task running state the mapping needs (v1's list-valued facts arrive
    as one-shot events; v2's `edited` replaces the WHOLE list, so we track it)."""

    def __init__(self) -> None:
        self.after: dict[str, list[str]] = collections.defaultdict(list)


def mentions_of(body: dict) -> list[str]:
    """v1's `mentions`, kept. It was dropped here, which is the only place the
    fact existed — a board migrated before this fix owes replies it cannot name."""
    raw = body.get("mentions") or []
    return [m for m in raw if isinstance(m, str) and m.strip()] if isinstance(raw, list) else []


def map_event(v1: dict, ctx: Ctx, counts: collections.Counter) -> list[tuple[str, dict]]:
    kind = v1["kind"]
    task = v1["task"]
    body = v1.get("body") or {}
    counts[kind] += 1

    if kind == "created":
        card = dict(body.get("card") or body)
        return [("created", {"card": card})]
    if kind in ("claimed", "comment"):
        return [(kind, body)]
    if kind == "commit":
        out = {"sha": body.get("sha", ""), "subject": body.get("subject", "")}
        if body.get("files"):
            out["files"] = body["files"]
        return [("commit", out)]
    if kind == "done":
        return [("status", {"to": body.get("to", "done")})]
    if kind == "status":
        to = body.get("to", "")
        if to in ("done", "dropped", "open"):
            return [("status", {"to": to})]
        if to in ("ready", "backlog", "claimed"):
            return [("released", {"note": ""})]
        counts[f"status(to={to}) — dropped, no v2 equivalent"] += 1
        return []
    if kind == "released":
        return [("released", {"note": body.get("note", "") or body.get("reason", "")})]
    if kind == "blocked":
        on = body.get("on")
        if not on:
            return []
        current = ctx.after[task]
        if on not in current:
            current.append(on)
        return [("edited", {"field": "after", "to": list(current)})]
    if kind == "handoff":
        to = body.get("assigned_to")
        out: list[tuple[str, dict]] = [("edited", {"field": "assignee", "to": to})] if to else []
        looped_in = [m for m in mentions_of(body) if m != to]
        if looped_in:
            out.append(("comment", {"text": "", "mentions": looped_in}))
        return out
    if kind == "message":
        text = {"text": body.get("text", "")}
        if mentions_of(body):
            text["mentions"] = mentions_of(body)
        return [("comment", text)]
    if kind in DROP_SILENT:
        return []
    counts[f"unknown kind {kind!r} — dropped"] += 1
    return []


def migrate(source: Path, board: Path, milestone_title: str, goal: str) -> collections.Counter:
    lines = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines.sort(key=lambda e: e["ts"])
    counts: collections.Counter[str] = collections.Counter()
    ctx = Ctx()

    ms_id = new_milestone_id()
    first_ts = lines[0]["ts"] - 1.0 if lines else 0.0
    events: list[Event] = [
        make(
            PROJECT,
            "taskops",
            "milestone",
            {
                "op": "create",
                "id": ms_id,
                "title": milestone_title,
                "goal": goal,
                "branch": f"ms/{slugify(milestone_title)}",
                "status": "open",
            },
            first_ts,
        )
    ]

    for v1 in lines:
        task, actor, ts = v1["task"], v1["actor"], v1["ts"]
        for kind, body in map_event(v1, ctx, counts):
            if kind == "created":
                card = dict(body["card"])
                card["milestone"] = ms_id
                card.setdefault("after", [])
                body = {"card": card}
            events.append(make(task, actor, kind, body, ts))

    stores = Stores(board)
    try:
        stores.write(events)
    finally:
        stores.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="a v1 board's events.jsonl")
    parser.add_argument("board", type=Path, help="output directory for the new v2 board")
    parser.add_argument("--milestone", default="imported from taskops v1")
    parser.add_argument("--goal", default="history migrated from the pre-v2 board")
    args = parser.parse_args()

    counts = migrate(args.source, args.board, args.milestone, args.goal)
    print(f"wrote {args.board}")
    print()
    for kind, n in counts.most_common():
        print(f"{n:5d}  {kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
