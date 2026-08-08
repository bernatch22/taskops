#!/usr/bin/env python3
"""Migrate a v1 board's events.jsonl into a fresh v2 board.

    uv run python scripts/migrate_v1.py <v1 events.jsonl> <new board dir> [--dry-run]

v1 stored more kinds than v2 does. The mapping, and why:

    claimed, comment, commit          → same kind, same shape
    done, status(to=done|dropped)     → status                 (v1 split "done" out; v2 doesn't)
    status(to=cancelled)              → status(to=dropped)     (v1's cancelled IS v2's dropped — unmapped, the
                                                                  card resurrects as OPEN and the board lies)
    status(to=review)                 → submitted              (history-only; core/review.py folds it. The card
                                                                  whose FINAL v1 status is `review` also keeps
                                                                  `review: true`, so it still renders as handed in)
    status(to=ready|backlog|claimed)  → released               (v1's "back to the pool" was a status; v2's is its own kind)
    released {"text": …}              → released {note: text}  (v1 wrote `text`; reading note/reason zeroed 12 of 12)
    edited                            → edited                 (v1's `from` dropped; `field=milestone` REWRITTEN to the
                                                                  new milestone id; `field=reviewer` is not in EDITABLE
                                                                  and is dropped by name)
    milestone {"op": "create|update"} → milestone {op: create|edit}
                                        (the v1 milestone's identity is its OWN create event's id — the body
                                         carries none — so an explicit `id` ("ms-" + v1_id[:6]) is written, or
                                         replay._milestone would mint one milestone PER EVENT. `update` becomes
                                         `edit`; `branch` is the slug of the FINAL title, stored once; `title`/
                                         `goal` are emitted only when the v1 body carries them, or an edit
                                         would blank them; v1's horizon/planned have no v2 field)
    acceptance {"criteria": […]}      → edited(criteria=[…])   (Card.criteria is a first-class v2 field, rendered
                                                                  under the spec in every take. What v2 banned is
                                                                  v1's GATE — done demanding evidence per criterion —
                                                                  never the criteria themselves; conflating the two
                                                                  is exactly how this data got dropped)
    context sort=rule level=project   → milestone edit {rules} (Milestone.rules is the home; each edit carries the
                                                                  CUMULATIVE list — rules is a whole-list field)
    blocked {"on": <task>}            → edited(after=[...])     (v1 stored blocking as a fact; v2 DERIVES it from `after`)
    handoff {"assigned_to","mentions"} → edited(assignee=…)     (+ a companion comment for anybody ELSE the handoff
                                                                  looped in — MENTIONS.md §5; the assignee's own
                                                                  mention is carried by the assignment itself)
    message {"text", "mentions"}      → comment {text, mentions}

Dropped BY NAME — every drop is counted and explained in the report, never
silently eaten (see DROPPED_BY_DESIGN below). The four filesystem concepts
with no v2 destination (reports/, workers/, stop-blocks.json, sweep.stamp) are
archived next to the v1 board, not migrated; the report names them too.
"""

from __future__ import annotations

import sys
import json
import argparse
import collections
from typing import Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from taskops.core.event import make  # noqa: E402
from taskops.core.types import EDITABLE, Event, slugify  # noqa: E402
from taskops.store.stores import Stores  # noqa: E402

# v1 kinds with no v2 destination: dropped, counted, and NAMED in the report.
DROPPED_BY_DESIGN = {
    "branch": "v1's slug-in-branch — the anti-pattern v2 exists to not have",
    "activity": "local-only activity timestamps that undercounted hours on every rebuild",
    "landed": "v1's per-card landing marker; the ok/failed split is archived with the v1 board",
    "policy": "v2 has no policy layer (day_zone=Europe/Madrid affects per-day views of imported history)",
    "review": "v1's reviewer-role machinery (the gate, not the criteria — those migrate)",
    "eval": "v1's reviewer-role machinery",
    "inferred": "v1's reviewer-role machinery",
    "unblocked": "v2 derives blocked from `after`; the un-blocking is the blocker closing",
}

# The four v1 concepts that live NEXT TO the log, not in it. Archive, never migrate.
ARCHIVE_ONLY = ("reports", "workers", "stop-blocks.json", "sweep.stamp")


class Ctx:
    """What the mapping must know before the first event is mapped.

    v1's list-valued facts arrive as one-shot events while v2's `edited`
    replaces the WHOLE list (LIST_FIELDS), so `after` and the milestone
    `rules` are accumulated. The milestone ids and the final title need a
    pre-pass (`prepare`): the v1 milestone's identity is its create EVENT's
    id, and `branch` must be the slug of the title the chapter ENDED with.
    """

    def __init__(self) -> None:
        self.after: dict[str, list[str]] = collections.defaultdict(list)
        self.ms_ids: dict[str, str] = {}  # v1 create-event id -> "ms-" + id[:6]
        self.ms_default = ""  # the board's (single) milestone; every card lands in it
        self.ms_final_title: dict[str, str] = {}  # new id -> last title written
        self.rules: dict[str, list[str]] = collections.defaultdict(list)
        self.review_final: set[str] = set()  # cards whose FINAL v1 status is "review"


def prepare(lines: list[dict[str, Any]]) -> Ctx:
    """One pass over the sorted v1 lines before mapping starts."""
    ctx = Ctx()
    last_status: dict[str, str] = {}
    for v1 in lines:
        body = v1.get("body") or {}
        if v1["kind"] == "milestone":
            op = body.get("op")
            if op == "create":
                new = "ms-" + str(v1["id"])[:6]
                ctx.ms_ids[str(v1["id"])] = new
                ctx.ms_default = ctx.ms_default or new
                ctx.ms_final_title[new] = str(body.get("title", ""))
            else:
                new = ctx.ms_ids.get(str(body.get("milestone", "")), ctx.ms_default)
                if new and body.get("title"):
                    ctx.ms_final_title[new] = str(body["title"])
        elif v1["kind"] == "done":
            last_status[v1["task"]] = "done"
        elif v1["kind"] == "status":
            last_status[v1["task"]] = str(body.get("to", ""))
    ctx.review_final = {task for task, to in last_status.items() if to == "review"}
    return ctx


def mentions_of(body: dict[str, Any]) -> list[str]:
    raw = body.get("mentions") or []
    return [m for m in raw if isinstance(m, str) and m.strip()] if isinstance(raw, list) else []


def map_event(
    v1: dict[str, Any], ctx: Ctx, counts: collections.Counter[str]
) -> list[tuple[str, dict[str, Any]]]:
    kind = v1["kind"]
    task = v1["task"]
    body = v1.get("body") or {}
    counts[kind] += 1

    if kind == "created":
        card = dict(body.get("card") or body)
        card.pop("reviewer", None)  # v1-only column; v2 has no reviewer role
        card["milestone"] = ctx.ms_ids.get(str(card.get("milestone", "")), ctx.ms_default)
        card.setdefault("after", [])
        if task in ctx.review_final:
            # The one honest flag this migration adds: a card v1 shows as
            # awaiting a verdict keeps rendering that way in v2.
            card["review"] = True
        return [("created", {"card": card})]
    if kind in ("claimed", "comment"):
        return [(kind, body)]
    if kind == "commit":
        out = {"sha": body.get("sha", ""), "subject": body.get("subject", "")}
        if body.get("files"):
            out["files"] = body["files"]
        return [("commit", out)]
    if kind == "done":
        if body.get("evidence"):
            counts["done evidence — dropped, no v2 home (the closing sentence; archived with v1)"] += 1
        return [("status", {"to": body.get("to", "done")})]
    if kind == "status":
        to = body.get("to", "")
        if to == "cancelled":
            to = "dropped"  # v1's cancelled IS v2's dropped
        if to in ("done", "dropped", "open"):
            return [("status", {"to": to})]
        if to == "review":
            return [("submitted", {"note": str(body.get("evidence", "") or "")})]
        if to in ("ready", "backlog", "claimed"):
            return [("released", {"note": ""})]
        counts[f"status(to={to}) — dropped, no v2 equivalent"] += 1
        return []
    if kind == "released":
        note = body.get("text", "") or body.get("note", "") or body.get("reason", "")
        # v1's leftovers/never_started/recovered_from are sweep output whose
        # content `text` already carries verbatim; dropping the keys loses nothing.
        return [("released", {"note": note})]
    if kind == "blocked":
        on = body.get("on")
        if not on:
            return []
        current = ctx.after[task]
        if on not in current:
            current.append(on)
        return [("edited", {"field": "after", "to": list(current)})]
    if kind == "edited":
        field = str(body.get("field", ""))
        if field == "milestone":
            to = ctx.ms_ids.get(str(body.get("to", "")), ctx.ms_default)
            return [("edited", {"field": "milestone", "to": to})]
        if field in EDITABLE:
            return [("edited", {"field": field, "to": body.get("to")})]
        counts[f"edited(field={field}) — dropped, not in EDITABLE (a net no-op in this log)"] += 1
        return []
    if kind == "acceptance":
        criteria = [str(c) for c in body.get("criteria") or [] if c]
        return [("edited", {"field": "criteria", "to": criteria})]
    if kind == "milestone":
        op = body.get("op")
        if op == "create":
            new = ctx.ms_ids[str(v1["id"])]
            return [("milestone", {
                "op": "create",
                "id": new,
                "title": str(body.get("title", "")),
                "goal": str(body.get("goal", "")),
                "branch": "ms/" + slugify(ctx.ms_final_title.get(new) or str(body.get("title", ""))),
                "status": "open",
            })]
        new = ctx.ms_ids.get(str(body.get("milestone", "")), ctx.ms_default)
        out = {"op": "edit", "id": new}
        for field in ("title", "goal"):  # only what v1 wrote — "" would blank the chapter
            if body.get(field):
                out[field] = str(body[field])
        return [("milestone", out)]
    if kind == "context":
        sort, level = body.get("sort"), body.get("level")
        if sort == "rule" and level == "project" and ctx.ms_default:
            ctx.rules[ctx.ms_default].append(str(body.get("text", "")))
            return [("milestone", {"op": "edit", "id": ctx.ms_default,
                                   "rules": list(ctx.rules[ctx.ms_default])})]
        counts[f"context {sort}/{level} — dropped, dated snapshot with no v2 home (archived with v1)"] += 1
        return []
    if kind == "handoff":
        to = body.get("assigned_to")
        out2: list[tuple[str, dict[str, Any]]] = [("edited", {"field": "assignee", "to": to})] if to else []
        looped_in = [m for m in mentions_of(body) if m != to]
        if looped_in:
            out2.append(("comment", {"text": "", "mentions": looped_in}))
        return out2
    if kind == "message":
        text: dict[str, Any] = {"text": body.get("text", "")}
        if mentions_of(body):
            text["mentions"] = mentions_of(body)
        return [("comment", text)]
    if kind in DROPPED_BY_DESIGN:
        counts[f"{kind} — dropped by design: {DROPPED_BY_DESIGN[kind]}"] += 1
        return []
    counts[f"unknown kind {kind!r} — dropped"] += 1
    return []


def build(source: Path) -> tuple[list[Event], collections.Counter[str], dict[str, int]]:
    """Read, sort (ts only, STABLE — ties keep file order), map, make."""
    lines = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines.sort(key=lambda e: e["ts"])
    ctx = prepare(lines)
    counts: collections.Counter[str] = collections.Counter()
    events: list[Event] = []
    v1_mentions = handoff_only = 0
    for v1 in lines:
        body = v1.get("body") or {}
        if mentions_of(body):
            v1_mentions += 1
            if v1["kind"] == "handoff" and mentions_of(body) == [body.get("assigned_to")]:
                handoff_only += 1
        for kind, out in map_event(v1, ctx, counts):
            events.append(make(v1["task"], v1["actor"], kind, out, v1["ts"]))
    surviving = sum(1 for e in events if e["body"].get("mentions"))
    stats = {"v1_mentions": v1_mentions, "handoff_only": handoff_only, "surviving": surviving}
    return events, counts, stats


def report(source: Path, events: list[Event], counts: collections.Counter[str], stats: dict[str, int]) -> None:
    total_in = sum(n for key, n in counts.items() if " " not in key)
    dropped = sum(n for key, n in counts.items() if "dropped" in key and "evidence" not in key)
    print(f"v1 events in: {total_in} · v2 events out: {len(events)} · dropped and named: {dropped}"
          f" · {len(events)} written ⇒ kept + dropped = {total_in - dropped} + {dropped} = {total_in}")
    print("\nv2 events by kind:")
    for kind, n in collections.Counter(e["kind"] for e in events).most_common():
        print(f"{n:5d}  {kind}")
    print("\nv1 kinds seen, and every drop with its reason:")
    for kind, n in counts.most_common():
        print(f"{n:5d}  {kind}")
    print(f"\nmentions: {stats['v1_mentions']} v1 events carried mentions; {stats['handoff_only']} were"
          " handoffs whose only mention was the assignee (carried by the assignment itself, MENTIONS.md §5)"
          f" → {stats['surviving']} survive as comment mentions. That is correct, not data loss.")
    print("\narchive-only concepts next to this log (archived with the v1 board, never migrated):")
    for name in ARCHIVE_ONLY:
        sibling = source.parent / name
        if sibling.exists():
            size = sum(f.stat().st_size for f in sibling.rglob("*") if f.is_file()) \
                if sibling.is_dir() else sibling.stat().st_size
            print(f"  {name}: present, {size} bytes — NOT migrated, archive it with the v1 board")
        else:
            print(f"  {name}: not present next to this log")


def _only_new(board: Path, events: list[Event]) -> list[Event]:
    """Ids are content hashes, so a re-run maps to the same events — but
    `log.append` appends blindly; the dedupe must happen here or a second run
    doubles the log instead of no-op'ing (MIGRATION.md §4G)."""
    path = board / "events.jsonl"
    if not path.exists():
        return events
    known = {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    return [e for e in events if e["id"] not in known]


def migrate(source: Path, board: Path) -> collections.Counter[str]:
    events, counts, _ = build(source)
    stores = Stores(board)
    try:
        stores.write(_only_new(board, events))
    finally:
        stores.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="a v1 board's events.jsonl")
    parser.add_argument("board", type=Path, help="output directory for the new v2 board")
    parser.add_argument("--dry-run", action="store_true", help="map and report; write nothing")
    args = parser.parse_args()

    events, counts, stats = build(args.source)
    if not args.dry_run:
        stores = Stores(args.board)
        try:
            stores.write(_only_new(args.board, events))
        finally:
            stores.close()
        print(f"wrote {args.board}\n")
    report(args.source, events, counts, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
