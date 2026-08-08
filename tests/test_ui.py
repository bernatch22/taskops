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

Three waves of `.tsx`-only cards have now been rebuilt into that bundle, and
each left its own row of markers below: `VIEWS` (tk-fadcdc — the Worktrees tab,
the milestone picker, the Chapter pane's criteria), `GITHUB_VISIBLE` (tk-0bc9fa
— the GitHub anchors, a commit's `+/-`, the Event stream's real rows and pager,
the dev carrying a worktree, the picker's landed chapters) and `OWN_CLONE`
(tk-e5a340 — Files changed and the four steps of the diff cascade). All three
lists are the check that the bundle is the CURRENT source's output and not the
previous wave's: none of those strings existed in the bundle its chapter-close
replaced, so a close that forgot to run `node build.mjs` fails here.

The one marker that had to be RETIRED rather than added is the Event stream's
`"no events verb"`. It was true while nothing returned the log; `verbs/events.py`
made it false, so this file asserts its ABSENCE — an empty pane now means an
empty log and says so.
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

#: What the GITHUB-VISIBLE chapter added, on the same terms as `VIEWS`: each is
#: a `data-testid` written by exactly one card of that wave, and none of the six
#: is in the bundle this chapter-close rebuilt over. They are the markers that
#: say the bundle is THIS chapter's output — the anchors (`links.tsx`), the
#: per-file +/- of a commit event, the Event stream's real rows and its pager,
#: the dev who carries a worktree, and the landed chapters in the picker.
GITHUB_VISIBLE = (
    "commit-link",  # the sha, linking to github.com/<slug>/commit/<sha>
    "card-compare",  # the card as a PR: /compare/ms...tk
    "chapter-compare",  # the chapter's own diff
    "worktree-compare",  # the same link from the Worktrees table
    "event-numstat",  # the +/- a commit event now carries
    "event-more",  # the Event stream's keyset pager
    "worktree-owner",  # the dev carrying the tree
    "milestone-landed",  # the picker's landed-chapters section
)

#: What the OWN-CLONE chapter added — the Files-changed section and the patch
#: renderer, on the same terms as the two rows above: every one of the twelve is
#: a `data-testid` written by exactly one card of this wave (`links.tsx`'s
#: cascade drawn by `components/card/Patch.tsx`), and none of them is in the
#: bundle this chapter-close rebuilt over. They are also the four steps of the
#: cascade, so a rebuild that lost the fallback path — not just the happy one —
#: fails here too.
OWN_CLONE = (
    "files-changed",  # the card as a PR: the file list
    "changed-file",  # one row of it, foldable
    "changed-none",  # …and the range where nothing differs
    "patch",  # the unified diff itself
    "patch-empty",  # a range whose patch text is empty
    "patch-loading",  # step 1: reading the diff from this host's clone
    "patch-forge",  # step 3: no clone here — read it on the forge
    "patch-forge-link",
    "patch-none",  # step 4: no clone, no slug, one honest sentence
    "patch-truncated",  # a cut patch SAYS it was cut…
    "patch-truncated-link",  # …and offers the whole of it when it can
    "patch-toggle",  # the fold on a commit row
)


def a_clone(root: Path) -> Path:
    """A real two-branch repo, so the /git door has something true to answer.

    Built here rather than mocked for the same reason `tests/test_git.py` builds
    one: git is the point. `main` moves after the branch is cut, which is what
    makes merge-base(main, feature) → feature a different answer from `main
    ..feature` and keeps the compare honest.
    """
    from taskops.gitwork import run

    root.mkdir(parents=True)
    run.must("init", "-q", "-b", "main", str(root))
    run.must("config", "user.email", "test@example.com", cwd=root)
    run.must("config", "user.name", "Test", cwd=root)
    (root / "tax.py").write_text("RATE = 0.22\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "first", cwd=root)
    run.must("checkout", "-q", "-b", "tk-a11111", cwd=root)
    (root / "tax.py").write_text("RATE = 0.22\nREDUCED = 0.10\n", encoding="utf-8")
    (root / "pdf.py").write_text("def render() -> None: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "the reduced rate", cwd=root)
    return root


def a_diff(root: Path) -> dict[str, Any]:
    """The /git door's OWN answers — the payload half of this chapter.

    Both cases come from `http/gitdoor.py::answer`, not from `gitwork/diff.py`
    directly and not from a shape written by hand: the words of the no-repo
    refusal are what `links.tsx::noteGitRefusal` matches on, so a smoke test that
    invented them would pass while the real cascade never flipped.
    """
    from taskops.http import gitdoor
    from taskops._errors import NotFound

    clone = a_clone(root)
    compare = gitdoor.answer(clone, "compare/main...tk-a11111", "")
    try:
        gitdoor.answer(None, "compare/main...tk-a11111", "")
    except NotFound as refusal:
        no_repo = str(refusal)
    else:  # pragma: no cover - the door must refuse a host with no repo
        no_repo = ""
    return {"compare": compare, "no_repo": no_repo}


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

    # A chapter that already LANDED, and its own board payload. Built by the
    # server, like everything else here: `plan`, then `merged milestone=` — the
    # verb the orchestrator's own landing goes through (`verbs/record.py`), which
    # is what writes `status: "landed"` through the fold. It is landed
    # immediately so the board is left with exactly one OPEN chapter and every
    # other assertion in this file sees the payload it always saw.
    past = dev.call(
        "plan",
        {
            "milestone": "Nova, panel by panel",
            "goal": "the dashboard, pane by pane",
            "rules": ["ts-only diffs, the chapter-close rebuilds"],
            "criteria": ["every pane is filled"],
            "tasks": [{"title": "the Chapter pane", "spec": "goal, rules, branch"}],
        },
    )
    dev.call("merged", {"milestone": past["milestone"]["id"], "into": "main", "sha": "beef1234"})

    fixture: dict[str, Any] = {
        # `window=` is what makes `hours` exist at all (verbs/pulse.py::run), and
        # `useBoard` passes it on every call so Throughput draws real bars.
        "board": dev.call("board", {"window": "14d", "tz": "UTC"}),
        # The SAME verb, focused on the chapter that landed — the read that used
        # to be unreachable, since `milestones` sent only the open ones and the
        # picker could not name this id.
        "board_landed": dev.call(
            "board", {"milestone": past["milestone"]["id"], "window": "14d", "tz": "UTC"}
        ),
        # What the landed chapter must still be able to say for itself.
        "expect_landed": [
            "Nova, panel by panel",
            "the dashboard, pane by pane",
            "ts-only diffs, the chapter-close rebuilds",
            "every pane is filled",
        ],
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
        # The /git door's own answer over a real clone, and its own refusal on a
        # host that has none — the two ends of the cascade (ARCHITECTURE.md §16).
        "git": a_diff(root.parent / "clone"),
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
    for testid in VIEWS + GITHUB_VISIBLE + OWN_CLONE:
        assert f'"{testid}"' in app, f"{testid} is not in the committed bundle — rebuild it"
    # The pane that used to say "no events verb" no longer can: the verb exists
    # (`verbs/events.py`), so an empty pane now means an empty LOG and says that.
    assert "no events verb" not in app
    assert "The log is empty." in app
    # The anchor host, verbatim in the bytes — without it no link renders at all.
    assert "github.com" in app


_ = T0, _clock
