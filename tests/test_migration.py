"""scripts/migrate_v1.py — the v1 facts that survive the crossing.

Only the mapping that was losing data is pinned here: v1 carried `mentions` on
`message` and `handoff`, this script dropped both, and a dropped mention is a
reply somebody is owed that no board can name afterwards.
"""

from __future__ import annotations

import json
import collections
from typing import Any
from pathlib import Path

from scripts import migrate_v1

from taskops.verbs import _facts
from taskops.store.stores import Stores

BERNA = "dev:berna"
W1 = "agent:berna/w1"


def _mapped(kind: str, body: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    event = {"kind": kind, "task": "tk-aaaaaa", "actor": W1, "ts": 100.0, "body": body}
    return migrate_v1.map_event(event, migrate_v1.Ctx(), collections.Counter())


def test_a_v1_message_keeps_who_it_was_addressed_to() -> None:
    got = _mapped("message", {"text": "which rate?", "mentions": [BERNA]})
    assert got == [("comment", {"text": "which rate?", "mentions": [BERNA]})]
    assert _mapped("message", {"text": "nobody in particular"}) == [
        ("comment", {"text": "nobody in particular"})
    ]


def test_a_handoff_loops_in_the_second_person_but_not_the_assignee() -> None:
    """Assignment already says "this is yours", so the assignee needs no mention
    — but a handoff that also looped in somebody else was dropping that person."""
    plain = _mapped("handoff", {"assigned_to": W1, "mentions": [W1]})
    assert plain == [("edited", {"field": "assignee", "to": W1})]

    looped = _mapped("handoff", {"assigned_to": W1, "mentions": [W1, BERNA]})
    assert looped == [
        ("edited", {"field": "assignee", "to": W1}),
        ("comment", {"text": "", "mentions": [BERNA]}),
    ]


def test_a_migrated_mention_is_still_owed_a_reply_on_the_new_board(tmp_path: Path) -> None:
    """End to end: the fact crosses, and `pending()` on the v2 board can name
    who is owed an answer — which is the whole point of carrying it over."""
    card = {"id": "tk-aaaaaa", "title": "invoice model", "status": "open"}
    lines = [
        {"kind": "created", "task": "tk-aaaaaa", "actor": BERNA, "ts": 100.0, "body": {"card": card}},
        {
            "kind": "message",
            "task": "tk-aaaaaa",
            "actor": W1,
            "ts": 200.0,
            "body": {"text": "Decimal or float?", "mentions": [BERNA]},
        },
    ]
    source = tmp_path / "events.jsonl"
    source.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    migrate_v1.migrate(source, tmp_path / "board", "imported from v1", "history")

    stores = Stores(tmp_path / "board")
    try:
        owed = _facts.pending_mentions(stores, BERNA)
        assert [(m["task"], m["by"], m["text"]) for m in owed] == [
            ("tk-aaaaaa", W1, "Decimal or float?")
        ]
        assert _facts.pending_mentions(stores, W1) == []
    finally:
        stores.close()
