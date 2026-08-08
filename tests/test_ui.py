"""The UI, run for real.

The page is a React bundle now, built from `ui/` by `ui/build.mjs` and COMMITTED
to `src/taskops/ui/`. It is tested from both ends, and the two tests below are
those two ends:

1. `test_the_pages_draw_the_board_and_the_dossier` builds a real board with
   `LocalBoard`, hands the server's own `board` and `card` payloads to
   `ui/smoke/run.mjs`, and that harness renders the very modules `src/main.tsx`
   bundles — through `react-dom/server`, with no browser and no jsdom. What it
   proves is the list this file has always been: the nine Monitor panes, a
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

Ten waves of `.tsx`-only cards have now been rebuilt into that bundle, and
each left its own row of markers below: `VIEWS` (tk-fadcdc — the Worktrees tab,
the milestone picker, the Chapter pane's criteria), `GITHUB_VISIBLE` (tk-0bc9fa
— the GitHub anchors, a commit's `+/-`, the Event stream's real rows and pager,
the dev carrying a worktree, the picker's landed chapters), `OWN_CLONE`
(tk-e5a340 — Files changed and the four steps of the diff cascade) and
`WORKTREES_PR` (tk-b9c857 — the two-column index and the full-width diff page
that replaced the five-column table) and `SIDE_BY_SIDE` (tk-d0fc41 — the second
close of that same chapter: the page read side by side, with the card's own
thread on it, and Monitor's ninth pane) and `NOTHING_DRAWN` (tk-81c980 — a
column with nothing in it is not drawn at all, which is the one wave that also
RETIRED a marker of its own: see `RETIRED`) and `CHAPTERS_LISTED` (tk-13d115 —
several open chapters listed as foldable rows instead of apologised for, which
also retired a sentence: see `RETIRED_APOLOGY`) and `CLOSING_NOTE` (tk-a1b7f2 —
a close's transition and the note the worker signed off with) and `ACTORS`
(tk-5fc887 — the fourth view as a page about DEVS; it also RETIRED the six
markers of the draft it replaced) and `DATE_PANES` (tk-36b550 — the SECOND
redesign of what a dev opens into: a pane per calendar day with an hour that
folds open, which retired the lane-per-agent drawing and the hours bar panel
whole: see `RETIRED_TIMESHEET`). All ten lists are the check that the bundle is the CURRENT source's output and not
the previous wave's: none of those strings existed in the bundle its
chapter-close replaced, so a close that forgot to run `node build.mjs` fails
here.

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

#: The NINE panes Monitor draws — `ui/src/components/monitor/panels.ts`.
#:
#: `pane-swarm` is the ninth and the newest. It was added to the smoke harness's
#: own list by the card that built it (tk-74ace0) and deliberately NOT here,
#: because this tuple is asserted against the COMMITTED bundle and no card of
#: that wave was allowed to rebuild it — the marker would have been red from the
#: moment it was written until this close. It is here now, after the rebuild.
PANES = (
    "pane-leases",
    "pane-throughput",
    "pane-health",
    "pane-dag",
    "pane-files",
    "pane-chapter",
    "pane-mentions",
    "pane-events",
    "pane-swarm",
)

#: What only the FINISHED code emits — the markers a stub never carried.
#:
#: A subtitle proves nothing here: the eight pane stubs shipped with Nova's
#: subtitle strings already in them, so `PANES` alone passes against a bundle
#: built before any panel had content. Each of these is a `data-testid` that
#: exists in exactly one component written by this wave, and none of the five
#: is in the bundle this chapter-close rebuilt over.
#:
#: `worktree-commits` was a fifth marker here and is deliberately NOT: the
#: worktrees-as-pull-requests chapter rebuilt that view as two columns of tiles
#: and the per-branch commit CELL does not exist any more (it drew an em dash —
#: `WorktreeRow.commits` has never had a source). A marker for a deleted element
#: would fail the next rebuild and say nothing about the bundle. What it did for
#: this list — one string per card of the wave — the four below still do, and
#: the chapter that retired it paid its debt in `WORKTREES_PR`.
VIEWS = (
    "worktrees",  # the third tab (pages/Worktrees.tsx)
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

#: What the WORKTREES-AS-PULL-REQUESTS chapter added, on the same terms again:
#: the five-column table is gone and with it `worktree-commits` (see `VIEWS`),
#: so this row is what says the bundle carries the two screens that replaced it
#: — the two-column index with its sub-blocks and resolved chapter line, and the
#: second surface, a FULL-WIDTH diff page with its own chrome. None of the nine
#: is in the bundle this chapter-close rebuilt over; the last two are in it as
#: LITERALS even on a board with no slug and no clone, where neither can ever be
#: drawn — which is exactly what a byte-level check can say and a render cannot.
WORKTREES_PR = (
    "worktree-column",  # the index is two columns, In progress and Merged
    "worktree-block",  # …each split into its sub-blocks
    "worktree-chapter",  # the row's chapter, resolved to its title
    "worktree-diff",  # the second surface: the tree as a pull request
    "worktree-diff-back",  # the only way out of it
    "worktree-diff-range",  # base ← head
    "worktree-diff-dir",  # where the tree is on disk
    "worktree-diff-forge",  # …and out to the forge, when the board has a slug
    "files-changed-summary",  # the bar the diff PAGE adds to the file list
)

#: What the SECOND close of that same chapter added — the wave after `WORKTREES_PR`
#: landed, on the same terms once more. The index and the page existed; this wave
#: made the page READ like one (side by side, the card's own thread on it) and gave
#: Monitor its ninth pane. Every one of these nine is a `data-testid` written by
#: exactly one card of the wave, and none of them is in the bundle this close
#: rebuilt over — checked marker by marker against the previous `app.js` before
#: this list was written.
SIDE_BY_SIDE = (
    "patch-split",  # the diff, two columns
    "patch-split-row",  # …one paired line of it
    "worktree-diff-mode",  # unified ↔ split, on the page only
    "worktree-diff-thread",  # the CARD's thread, on the tree's page
    "swarm-graph",  # the ninth pane's ring
    "swarm-node",  # an actor or a card on it
    "swarm-edge",  # a lease, a lapsed lease, or a contested path
    "swarm-legend",  # the four actor kinds, as the mock draws them
    "swarm-count",  # nodes, and how many edges are contested
)

#: The THIRD close of that chapter, and it is one marker because it is one
#: decision reversed: a column with nothing in it is no longer drawn at all, so
#: the per-column empty state goes with the shells that carried it and the ONE
#: surviving sentence — both columns empty — is a message centred in the page.
#:
#: Both halves are asserted, and that is the point of a byte-level check here: a
#: rebuild that forgot this card would carry `worktrees-empty` and not
#: `worktrees-none`, and a source tree that kept the old empty state alongside
#: the new one would carry both. Only the swap passes.
NOTHING_DRAWN = ("worktrees-none",)  # the both-empty message, centred in the page

#: …and what the same change REMOVED. `worktrees-empty` was the dotted field
#: inside a column shell; it was in the bundle this close rebuilt over (checked),
#: and it must not be in the one that replaces it.
#:
#: The ACTORS row below retired six more, and for the same shape of reason: the
#: first draft of that page drew one tile per ACTOR with the detail revealed in
#: place, and tk-5fc887 replaced both with a dev card and a real overlay. A
#: source tree that kept the old page beside the new one would carry both sets,
#: so only the swap passes. `timesheet-cards` is the one this card exists for —
#: it is the list of card ids joined by dots that stood where a drawing belongs.
RETIRED = (
    "worktrees-empty",
    "actor-card",  # one tile per ephemeral sub-agent: sixty-seven of them
    "actor-card-open",
    "actor-pill",
    "actor-carried",
    "actor-history",
    "actor-timesheet-toggle",  # the in-place reveal, replaced by a full overlay
    "timesheet-cards",  # THE DEFECT: a timesheet drawn as a list of ids
)

#: The SEVENTH wave, and it is the Chapter pane's (tk-13d115). `_facts.in_scope`
#: returns None for SEVERAL open chapters as well as for none — it refuses to
#: guess — and the pane read that refusal as a fault: a paragraph telling the
#: reader to close one, and nothing at all about either chapter. It now lists
#: every OPEN chapter, one foldable row each, first expanded, each row's `focus`
#: calling the header picker's own setter.
#:
#: Both halves again, and here the retired half is a SENTENCE rather than a
#: `data-testid`: the apology is what this card deleted, it was in the bundle
#: this close rebuilt over (checked), and a rebuild that missed this card would
#: carry it.
CHAPTERS_LISTED = (
    "chapter-row",  # one open chapter, one row
    "chapter-fold",  # …a real button with aria-expanded, not an arrow glyph
    "chapter-open-count",  # how many open cards it carries, folded from the rows
    "chapter-focus",  # the door to the header picker's own setter
)

#: …and what it removed: the apology for a board that is merely working.
RETIRED_APOLOGY = ("Land or drop the finished ones",)

#: The EIGHTH wave's, and it is the thread's (tk-a1b7f2). A `status` event was
#: drawn as the bare word "done": `Thread.tsx::detail` tried body keys in an
#: order that reached `to` and never `reason`, and the render drew a text block
#: only for a comment. Every close note in the log — 61 of 61 on this board —
#: was on the wire and off the screen. The thread now draws a PHRASE and, under
#: it, the PROSE, and these are the two `data-testid`s that split.
#:
#: It was written OUTSIDE the `markers` tuple by the card that earned it, for
#: exactly the reason `PANES` records for `pane-swarm`: that wave's cards are
#: `.tsx`-only and none of them may rebuild `src/taskops/ui/`, so the assertion
#: would have been red from the moment it was written until the chapter-close
#: rebuild. tk-56740f is that rebuild, and both strings are asserted now.
CLOSING_NOTE = (
    "event-detail",  # the transition, the field, the verdict — the phrase
    "event-prose",  # …and the writing underneath it
)

#: The NINTH wave, and it is this chapter's own: ACTORS, the fourth view. It
#: shipped once as a grid of ACTOR tiles with an in-place reveal, and tk-5fc887
#: reversed both — sixty-seven tiles for sixty-six dead sub-agents is not a page
#: about who has been on this board — so these markers are that page's, not the
#: first draft's: `dev-card` where `actor-card` was, `dev-open` where
#: `actor-timesheet-toggle` was.
#:
#: What the row is really pinning is the chapter's refusal (ARCHITECTURE.md §11):
#: an actor is a name bound to the run of a card, so the bundle carries a dev's
#: own figures and the days it worked INSTEAD of a held/free/lapsed slot roster.
#: `actors-none` is the empty board's one sentence rather than an empty grid.
ACTORS = (
    "actors",  # the fourth tab (pages/Actors.tsx)
    "dev-card",  # ONE card per dev — the durable identity, never per agent
    "dev-live",  # how many of its agents are on a card RIGHT NOW, unopened
    "dev-recent",  # the most recent few agents, and the rest as a count
    "dev-open",  # the door into the full overlay (components/actors/DevPanel.tsx)
    "actors-none",  # a board nobody has touched: one sentence
)

#: The TENTH wave, and it is the SECOND redesign of that same panel (tk-36b550).
#: What a dev opened into was a DRAWING — one lane per agent on a shared
#: wall-clock axis — with a panel of hour BARS beside it on the page. Both
#: existed to compare actors against each other, and an ephemeral agent is a
#: label: `w1` today is not `w1` yesterday, which is this chapter's own goal. So
#: neither was restyled; both were deleted.
#:
#: What replaced them answers the one question the panel can answer honestly —
#: WHEN did the work happen: a pane per calendar day, NEWEST FIRST and only the
#: newest open, each day's hours a row, each row folding open to its sessions.
#: An hour with nothing counted is drawn and says so, because that is where the
#: dropped gaps are.
#:
#: Both halves are asserted, as every redesign row here is: these strings are the
#: new panel's, `RETIRED_TIMESHEET` below is the old one's, and a source tree
#: that kept one beside the other would carry both. Only the swap passes.
DATE_PANES = (
    "daysheet",  # the panel (components/actors/Daysheet.tsx)
    "day-pane",  # ONE PANE PER DATE, newest first
    "day-fold",  # …a real button with aria-expanded, not an arrow glyph
    "day-total",  # that day's counted time
    "day-dropped",  # the gaps: how many, and the wall-clock they hold
    "hour-row",  # every hour the day spans — including one with nothing in it
    "hour-fold",  # the second fold, and only where there is something behind it
    "hour-total",  # the time counted inside that hour
    "hour-cards",  # the cards it touched, or `nothing counted`
    "session-row",  # HH:MM – HH:MM, the duration, the card — a door to its dossier
    "daysheet-none",  # nothing counted in the window: one sentence
    "daysheet-rule",  # the arithmetic, in core/hours.py's own words
    "dev-figures",  # the rail: worked, commits, cards, who is running now
)

#: …and what that redesign REMOVED. Every one of these was in the bundle this
#: close rebuilt over (checked, one at a time), and none may be in the one that
#: replaces it: the lanes and their axis, the per-agent rows under them, and the
#: bar panel on the page.
RETIRED_TIMESHEET = (
    "timesheet",  # the drawing itself
    "timesheet-lane",  # ONE LANE PER AGENT: the comparison this card refuses
    "timesheet-lane-total",
    "timesheet-axis",
    "timesheet-ruler",
    "timesheet-tick",
    "timesheet-block",
    "timesheet-gap",
    "timesheet-range",
    "timesheet-dropped",
    "timesheet-capped",
    "timesheet-none",
    "timesheet-rule",
    "dev-agent",  # a row per sub-agent — an agent is not a subject here
    "dev-agents",
    "dev-agents-none",
    "dev-agents-more",
    "dev-agent-state",
    "dev-agent-card",
    "dev-agent-history",
    "pane-hours-today",  # THE UGLY ONE: a bar chart comparing labels
    "hours-dev",
    "hours-bar",
)

#: The EIGHTH wave, and it is one card (tk-382948): every screen that draws
#: prose routes through the one renderer. Two markers, on the same terms as the
#: rows above — neither is in the bundle this close rebuilt over.
#:
#: `chapter-goal` is the goal's own scroll box, which exists because the goal is
#: blocks now; `markdown-inline` is the renderer's second mode, the one a rule, a
#: criterion, a mention row and a tile note are drawn in. A rebuild that carried
#: the fix for the goal and not the fix for the lists would fail on the second.
PROSE = (
    "chapter-goal",  # the goal, rendered and scrolled, never cut
    "markdown-inline",  # the ONE renderer's spans-only mode
)


#: A chapter goal with real markdown in it — the bug this chapter exists for.
#:
#: NOT invented: it is an excerpt of the goal the migrated axion board actually
#: carries (4.252 characters, read off `board` on the live server, 2026-08-08),
#: cut to the four constructs that were printing literally on screen — bold, a
#: `###` heading, inline code and a bullet list. A fixture that said
#: "**bold**\n\n- item" would pin the parser; this one pins the SCREEN, because
#: it is shaped like the thing the reader complained about.
MARKDOWN_GOAL = """**La máquina, y el menú que ya está lleno.**

De cualquier feature a un veredicto **pre-registrado** en una llamada — eso es
la imprenta (`LA IMPRENTA ·1` a `·12`).

### Dónde está el frente hoy (actualizado 2026-08-05)

- `#103 etfflow_regime` — REJECT. El veto paga peaje de transacción para comprar nada.
- `#96 mlrank` — deuda fechada CONTRA EL RELOJ DEL TRIAL, con `tk-21a340` de prerequisito.

Y el límite que ninguna card mueve: la restricción que ata es el **nivel de Sharpe**."""

#: Two rules. The first is verbatim off this repo's own board (the Nova
#: chapter's), because a rule carrying a code span is the ordinary case and not a
#: contrived one — nine of the ten rules with backticks in this board's log are
#: shaped exactly like it.
#:
#: The second is another of them with the number a human types when they are
#: writing a list into a list. That is the whole reason it is here: handed to the
#: BLOCK renderer, `1. …` becomes an `<ol>` — a second numbering inside a tile
#: that already draws its own, which is criterion 2 failing.
MARKDOWN_RULES = [
    "Dev source in ui/, build with `node build.mjs` FROM ui/, and the rebuilt bundle"
    " in src/taskops/ui/ IS committed.",
    "1. The feed socket is a signal, not data: never render from a frame.",
]


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


def a_closed_pair(root: Path) -> list[dict[str, Any]]:
    """Two cards the board actually CLOSED, and the payloads it answers with.

    Its OWN board, and that is the point of the function rather than two more
    rows in `a_board`: nothing on the fixture board is done or integrated, and
    several assertions in `ui/smoke/main.tsx` are about exactly that shape (a
    Merged column with no rows is not drawn at all). A closed card there would
    have quietly changed what those assertions are looking at.

    Every string here is written by the SERVER onto a real event body —
    `submitted.note`, `reviewed.note`, `status.reason`, `status.no_code` — and
    §9 of the harness proves each one reached the screen. The first card takes
    the long way round (handed in, judged, closed) so its history carries all
    three kinds; the second closes with NO code, which is the other body key a
    reader should not have to open the log to learn about.
    """
    dev = LocalBoard(root, "dev:berna")
    cards = dev.call(
        "plan",
        {
            "milestone": "the importer",
            "goal": "read a bank CSV",
            "tasks": [
                {"title": "the CSV reader", "spec": "read the bank CSV", "review": True},
                {"title": "the changelog", "spec": "write it"},
            ],
        },
    )["cards"]
    worker = LocalBoard(root, "agent:berna/w2")
    reviewed, no_code = cards[0]["id"], cards[1]["id"]

    worker.call("take", {"task": reviewed})
    worker.call("bind", {"task": reviewed, "sha": "c0ffee11", "subject": "feat: csv"})
    worker.call(
        "update", {"task": reviewed, "status": "review", "comment": "parsed with Decimal throughout"}
    )
    dev.call(
        "review",
        {"task": reviewed, "verdict": "pass", "note": "read every row, the rounding holds"},
    )
    worker.call(
        "update",
        {"task": reviewed, "status": "done", "comment": "closed after the pass — Decimal all the way"},
    )

    worker.call("take", {"task": no_code})
    worker.call(
        "update",
        {
            "task": no_code,
            "status": "done",
            "no_code": True,
            "comment": "the README already said it, so there was nothing to write",
        },
    )
    payloads = [dev.call("card", {"task": reviewed}), dev.call("card", {"task": no_code})]
    dev.close()
    worker.close()
    return payloads


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
            "goal": MARKDOWN_GOAL,
            "rules": MARKDOWN_RULES,
            "criteria": ["Every number is a Decimal — `float` appears nowhere"],
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
                    # The second one is verbatim off THIS repo's own board — a
                    # criterion with a code span in it is the ordinary case, not
                    # a contrived one, and it is what pins criterion 2.
                    "criteria": [
                        "Decimal, never float",
                        "WHEN `npm run typecheck` runs in ui/ THEN it passes strict",
                    ],
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
        {
            "task": cards[1]["id"],
            # A comment quoting code is the ordinary case on this board, and it
            # is what says the mentions pane reads the same markdown the thread
            # does — it used to print the backticks (tk-382948).
            "comment": "Decimal or float? `round()` truncates",
            "mentions": ["dev:berna"],
        },
    )
    worker.call(
        "update",
        {
            "task": cards[1]["id"],
            "status": "released",
            # A released note is prose an agent wrote in a hurry, and it quotes
            # code — this is the shape every real one on this board has.
            "comment": "got to the rounding — see `src/tax.py::half_up`",
        },
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
        "closed": a_closed_pair(root.parent / "closed"),
        # The board this credential is looking at owes it an answer, and the
        # page must say so — a mention row carries what was said, not a title.
        "expect_board": ["Addressed to you", "Decimal or float?"],
        # Everything the dossier promises to show. A missing section fails here.
        "expect": [
            "the reduced rate",
            "10% for food",  # the spec
            "Criteria · 2",  # the section, counted
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
    for claim in (
        "ok criteria are on screen",
        "ok the draft survives a refusal",
        # The eighth wave's own claim, named here for the same reason as the two
        # above: a harness that silently stopped asserting it still fails.
        "ok a close draws its transition AND the note the worker signed off with",
        "ok a close with no commit says so, in the Python renderer's own words",
    ):
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
    markers = (
        VIEWS + GITHUB_VISIBLE + OWN_CLONE + WORKTREES_PR + SIDE_BY_SIDE + NOTHING_DRAWN
    ) + CHAPTERS_LISTED + CLOSING_NOTE + ACTORS + DATE_PANES + PROSE
    for testid in markers:
        assert f'"{testid}"' in app, f"{testid} is not in the committed bundle — rebuild it"
    for testid in RETIRED + RETIRED_TIMESHEET:
        assert f'"{testid}"' not in app, f"{testid} was retired but is still in the bundle"
    # A sentence, not a `data-testid`, so it is read as a plain substring: the
    # minifier keeps the literal but not the quotes around a JSX text node.
    for phrase in RETIRED_APOLOGY:
        assert phrase not in app, f"{phrase!r} was retired but is still in the bundle"
    # The pane that used to say "no events verb" no longer can: the verb exists
    # (`verbs/events.py`), so an empty pane now means an empty LOG and says that.
    assert "no events verb" not in app
    assert "The log is empty." in app
    # The anchor host, verbatim in the bytes — without it no link renders at all.
    assert "github.com" in app


_ = T0, _clock
