"""The UI, run for real.

The page is plain JS with no build step, so it is testable the same way
everything else here is: give it the exact payload the board returns, run it,
and click every card. Without this the failure mode is the worst one there
is — a click that silently does nothing, which nobody can debug from a log.

`node` is used because it is what runs JavaScript. If it is missing the test
skips rather than pretending.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any
from pathlib import Path

import pytest

from taskops import _clock
from taskops.board import LocalBoard
from tests.conftest import T0

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "ui_harness.js"
PAGE = ROOT / "ui" / "index.html"

pytestmark = [
    pytest.mark.usefixtures("clock"),
    pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed"),
]


def test_the_page_draws_the_board_and_opens_every_card(tmp_path: Path) -> None:
    dev = LocalBoard(tmp_path / "board", "dev:berna")
    cards = dev.call(
        "plan",
        {
            "milestone": "MVP facturador",
            "goal": "read a bank CSV and issue invoices with VAT",
            "tasks": [
                {
                    "title": "VAT",
                    "spec": "the whole tax",
                    "files": ["src/tax.py"],
                    "labels": ["backend"],
                },
                {
                    "title": "the reduced rate",
                    "parent": 0,
                    "spec": "10% for food",
                    "criteria": ["Decimal, never float"],
                    "files": ["src/tax.py"],
                },
                {"title": "PDF", "spec": "render", "files": ["src/pdf.py"], "after": 1},
            ],
        },
    )["cards"]
    dev.call("assign", {"tasks": [cards[0]["id"]]})
    worker = LocalBoard(tmp_path / "board", "agent:berna/w2")
    worker.call("take", {"task": cards[1]["id"]})
    worker.call("bind", {"task": cards[1]["id"], "sha": "a3f9c21b", "subject": "feat: rates"})
    worker.call(
        "update",
        {"task": cards[1]["id"], "comment": "Decimal or float?", "mentions": ["dev:berna"]},
    )
    worker.call(
        "update",
        {"task": cards[1]["id"], "status": "released", "comment": "got to the rounding"},
    )

    fixture: dict[str, Any] = {
        "board": dev.call("board", {}),
        "card": dev.call("card", {"task": cards[1]["id"]}),
        # The board this credential is looking at owes it an answer, and the
        # page must say so — a mention row carries what was said, not a title.
        "expect_board": ["Mentions — addressed to you, not yet answered", "Decimal or float?"],
        # Everything the panel promises to show. A missing section fails here.
        "expect": [
            "the reduced rate",
            "10% for food",  # the spec
            "1. Decimal, never float",  # the criteria
            "got to the rounding",  # the previous worker's note
            "VAT",  # the epic, resolved
            "a3f9c21b",  # the commit, with its subject
        ],
    }
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    done = subprocess.run(
        ["node", str(HARNESS), str(PAGE), str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    dev.close()
    worker.close()
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "opened" in done.stdout


_ = T0, _clock
