"""The UI, run for real.

The page is a React bundle now, built from `ui/` by `ui/build.mjs` and COMMITTED
to `src/taskops/ui/`. It is tested from both ends, and the two tests below are
those two ends:

1. `test_the_pages_draw_the_board_and_the_dossier` builds a real board with
   `LocalBoard`, hands the server's own `board` and `card` payloads to
   `ui/smoke/run.mjs`, and that harness renders the very modules `src/main.tsx`
   bundles — through `react-dom/server`, with no browser and no jsdom. What it
   proves is the list this file has always been: the eight Monitor panes, a
   pane with no verb showing its empty state instead of a zero, the Board's
   columns, the acceptance criteria in the dossier (the hole v1 never closed),
   the comment box posting `update` and nothing else, the draft surviving a
   refusal, and Escape closing the top-most overlay only.

2. `test_the_committed_bundle_carries_the_dashboard` reads the COMMITTED bundle
   itself. The first test runs the source; this one is what notices that
   `src/taskops/ui/app.js` is not that source's output — a `pip install
   taskops` serves these bytes and nothing else, so a pane missing HERE is a
   pane missing in production. Its whole-tree counterpart is `npm run check`,
   whose `git diff --exit-code ../src/taskops/ui` clause fails on any drift.

`node` runs the harness because it is what runs JavaScript, and the harness
compiles TypeScript with the project's own esbuild — so it needs
`ui/node_modules` (`npm ci` in `ui/`, twelve packages, gitignored). Missing
either, the first test SKIPS rather than pretending; the second needs neither
and always runs.

The wave of `.tsx`-only cards that this file's TODO used to name is rebuilt
(tk-fadcdc), so `VIEWS` below now asserts what only the finished code emits:
the Worktrees tab, the header's milestone picker, and the Chapter pane's
criteria list. Those three are the check that the bundle is the CURRENT source's
output and not the previous wave's — none of them exists in the bundle this card
replaced, so a chapter-close that forgot to run `node build.mjs` fails here.
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
UI = ROOT / "ui"
HARNESS = UI / "smoke" / "run.mjs"
BUNDLE = ROOT / "src" / "taskops" / "ui"

#: The eight panes Monitor draws — `ui/src/components/monitor/panels.ts`.
PANES = (
    "pane-leases",
    "pane-throughput",
    "pane-health",
    "pane-dag",
    "pane-files",
    "pane-chapter",
    "pane-mentions",
    "pane-events",
)

#: What only the FINISHED code emits — the markers a stub never carried.
#:
#: A subtitle proves nothing here: the eight pane stubs shipped with Nova's
#: subtitle strings already in them, so `PANES` alone passes against a bundle
#: built before any panel had content. Each of these is a `data-testid` that
#: exists in exactly one component written by this wave, and none of the five
#: is in the bundle this chapter-close rebuilt over.
VIEWS = (
    "worktrees",  # the third tab (pages/Worktrees.tsx)
    "worktree-commits",  # its per-branch commit cell
    "milestone-menu",  # the header's picker, open (chrome/MilestonePicker.tsx)
    "chapter-criteria",  # the chapter's criteria list (monitor/Chapter.tsx)
    "standing",  # Live leases' three-figure empty state
)

needs_node = pytest.mark.skipif(
    shutil.which("node") is None or not (UI / "node_modules").is_dir(),
    reason="the harness needs node and `npm ci` in ui/",
)


def a_board(root: Path) -> dict[str, Any]:
    """A board with something of every kind on it, and the payloads it answers with.

    The fixture is the SERVER'S OWN answer, never a hand-written shape: a UI that
    renders a payload the board would never send is a UI that renders nothing in
    production. `expect` and `expect_board` travel with it — this side names the
    strings it put on the board, the harness proves they reached the screen.
    """
    dev = LocalBoard(root, "dev:berna")
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
    worker = LocalBoard(root, "agent:berna/w2")
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
        # `window=` is what makes `hours` exist at all (verbs/pulse.py::run), and
        # `useBoard` passes it on every call so Throughput draws real bars.
        "board": dev.call("board", {"window": "14d", "tz": "UTC"}),
        "card": dev.call("card", {"task": cards[1]["id"]}),
        # The board this credential is looking at owes it an answer, and the
        # page must say so — a mention row carries what was said, not a title.
        "expect_board": ["Addressed to you", "Decimal or float?"],
        # Everything the dossier promises to show. A missing section fails here.
        "expect": [
            "the reduced rate",
            "10% for food",  # the spec
            "Criteria · 1",  # the section, counted
            "Decimal, never float",  # the criterion itself
            "got to the rounding",  # the previous worker's note
            "VAT",  # the epic, resolved
            "a3f9c21b",  # the commit, with its subject
        ],
    }
    dev.close()
    worker.close()
    return fixture


@needs_node
@pytest.mark.usefixtures("clock")
def test_the_pages_draw_the_board_and_the_dossier(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(a_board(tmp_path / "board")), encoding="utf-8")

    done = subprocess.run(
        ["node", str(HARNESS), str(path)],
        cwd=UI,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "smoke ok" in done.stdout
    # The harness prints one `ok <claim>` per assertion; naming a few here means
    # a harness that silently stopped asserting them still fails this test.
    for claim in ("ok criteria are on screen", "ok the draft survives a refusal"):
        assert claim in done.stdout, done.stdout
    for pane in PANES:
        assert f"ok pane {pane}" in done.stdout, done.stdout


def test_the_committed_bundle_carries_the_dashboard() -> None:
    """What `pip install taskops` actually serves.

    Not a substitute for the harness above — it reads bytes, it does not run
    them — but it is the only assertion that is about the SHIPPED artefact, and
    a minifier keeps string literals, so a pane that lost its `data-testid` or a
    bundle rebuilt from a tree without a panel fails here.
    """
    page = (BUNDLE / "index.html").read_text(encoding="utf-8")
    assert "app.js" in page and "style.css" in page
    assert (BUNDLE / "style.css").read_text(encoding="utf-8").strip()

    app = (BUNDLE / "app.js").read_text(encoding="utf-8")
    for pane in PANES:
        assert f'"{pane}"' in app, f"{pane} is not in the committed bundle"
    for testid in ("monitor", "board", "criteria", "comment-box"):
        assert f'"{testid}"' in app, f"{testid} is not in the committed bundle"
    for testid in VIEWS:
        assert f'"{testid}"' in app, f"{testid} is not in the committed bundle — rebuild it"
    # The empty state of the pane with no verb behind it, verbatim in the bytes.
    assert "no events verb" in app


_ = T0, _clock
