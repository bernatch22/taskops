import { renderToStaticMarkup } from "react-dom/server";

import { WorktreeDiff, Worktrees  } from "../../src/pages/Worktrees";
import { pageView } from "../../src/pages/WorktreeDiff";
import {
  resetGitAvailability
  
} from "../../src/links";
import { PatchText } from "../../src/components/card/Patch";
import { split } from "../../src/components/card/split";
import { onTab } from "../../src/App";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, named } = h;

  const git = fixture.git;

  /* ── The diff reads like a page ────────────────────────────────────────
   *
   * Four claims, and the first is the only one with arithmetic in it. `split()`
   * is a pure function of a string, so it is exercised on the DOOR'S OWN patch
   * (the same `git.compare.patch` §8 draws) rather than on a hand-written diff —
   * the fixture rule, applied to a parser.
   */

  const hunks = split(git.compare.patch);
  check("the door's own patch folds into hunks", hunks.length > 0 && !!hunks[0]);
  check(
    "every hunk keeps its @@ header, the reader's only anchor",
    hunks.every((h) => h.header.startsWith("@@")),
  );
  check(
    "a context row is on both sides and both numbers advance",
    hunks.some((h) => h.rows.some((r) => r.left !== null && r.right !== null)),
  );
  check(
    "line numbers count up, per side, never sharing a counter",
    hunks.every((h) => {
      const left = h.rows.flatMap((r) => (r.left ? [r.left.n] : []));
      const right = h.rows.flatMap((r) => (r.right ? [r.right.n] : []));
      const rising = (ns: number[]): boolean => ns.every((n, i) => i === 0 || n === ns[i - 1]! + 1);
      return rising(left) && rising(right);
    }),
  );
  check(
    "the patch's own additions are on the RIGHT and carry no marker",
    hunks.some((h) => h.rows.some((r) => r.right?.text === "REDUCED = 0.10" && r.left === null)),
  );

  /* Pairing is POSITIONAL, and the longer run leaves null opposite its tail.
   * Written by hand because no real patch guarantees a 2-for-1 replacement, and
   * this is the rule the whole alignment rests on. */
  const paired = split("@@ -3,2 +3,3 @@\n-old one\n-old two\n+new one\n+new two\n+new three\n ctx");
  check(
    "a run of deletions pairs positionally with the run of additions after it",
    paired[0]?.rows[0]?.left?.text === "old one" && paired[0]?.rows[0]?.right?.text === "new one",
  );
  check(
    "and the longer run keeps going with nothing opposite it",
    paired[0]?.rows[2]?.left === null && paired[0]?.rows[2]?.right?.text === "new three",
  );
  check(
    "numbering survives the pairing: the context line after it is 5 ← 6",
    paired[0]?.rows[3]?.left?.n === 5 && paired[0]?.rows[3]?.right?.n === 6,
  );

  /* THE FALLBACK IS THE WHOLE SAFETY OF THIS FEATURE. Anything with no readable
   * `@@` in it is `[]`, and the component draws the unified view it always drew
   * — never an empty two-column table, which reads as "no changes". */
  check("a body with no hunk in it is not a table", split(git.no_repo).length === 0);
  check("nor is a hunk header it cannot read", split("@@ what @@\n+a").length === 0);
  // A BAD HEADER POISONS THE WHOLE PATCH, and does not merely skip its hunk: the
  // counters after it would be invented. So a readable hunk BEFORE an unreadable
  // one is dropped with it — the case a `continue` would quietly keep.
  check(
    "one unreadable header drops the patch, not just its own hunk",
    split("@@ -1,1 +1,1 @@\n ctx\n@@ nope @@\n+x").length === 0,
  );
  // A hunk with a header and NO rows is the empty two-column table this feature
  // must never draw: it reads as "no changes" and means "I understood nothing".
  check("a hunk with no rows in it is not a table either", split("@@ -1,0 +1,0 @@").length === 0);
  // `split("\n")` leaves a tail after the final newline. It is not a line of the
  // patch — git writes a blank context line as a single space — and counting it
  // would push every hunk after it by one and draw a row that is not there.
  check(
    "the newline at the end of a patch is not a row",
    split("@@ -1,1 +1,1 @@\n ctx\n")[0]?.rows.length === 1,
  );
  // `\\ No newline at end of file` is a note about the line above, on whichever
  // side it followed. It is a line of neither file: no counter, no row, and it
  // does NOT break the run it sits in — the deletion still pairs with what comes
  // after it.
  check(
    "the no-newline marker breaks neither the run nor the numbering",
    split("@@ -1,1 +1,2 @@\n-a\n\\ No newline at end of file\n+b\n+c")[0]?.rows.length === 2,
  );
  // `---`/`+++` are FILE headers and belong to no hunk. Tested before `+`/`-`
  // exactly as `tone()` tests them — drop that ordering and the second file's
  // header lands inside the first file's last hunk as a deletion.
  check(
    "a file header never becomes a row of the file before it",
    hunks.every((h) =>
      h.rows.every((r) =>
        [r.left?.text, r.right?.text].every(
          (t) => t === undefined || !/^(--|\+\+|diff |index )/.test(t),
        ),
      ),
    ),
  );
  const unreadable = renderToStaticMarkup(
    <PatchText text={"Binary files a/logo.png and b/logo.png differ"} view={{ size: "page", mode: "split" }} />,
  );
  check(
    "asked for split, an unparseable patch falls back to unified",
    unreadable.includes('data-testid="patch"') && !unreadable.includes('data-testid="patch-split"'),
  );

  /* THE TWO SIZES. Criterion 3 is that the DRAWER's pane does not move, so the
   * assertion is on its literal measurements — and on the page's being other
   * ones. A variant that silently inherited the page's numbers would pass a
   * "does it render" check and fail this. */
  const inDrawer = renderToStaticMarkup(<PatchText text={git.compare.patch} />);
  check(
    "the drawer's pane keeps today's measurements",
    inDrawer.includes("font-size:11.5px") && inDrawer.includes("max-height:360px"),
  );
  check("and stays unified by default", !inDrawer.includes('data-testid="patch-split"'));
  const onPage = renderToStaticMarkup(
    <PatchText text={git.compare.patch} view={{ size: "page", mode: "split" }} />,
  );
  check(
    "the page's pane is a page's: bigger type, a cap on the viewport",
    onPage.includes("font-size:13px") && onPage.includes("max-height:72vh"),
  );
  check(
    "and it draws two columns with a number per side",
    onPage.includes('data-testid="patch-split"') &&
      (onPage.match(/data-testid="patch-split-row"/g) ?? []).length > 0,
  );

  /* THE PAGE ITSELF: the toggle, defaulted to split, and the CARD'S OWN thread —
   * the same component and the same box the dossier uses, fed the dossier `App`
   * already fetched. There is no worktree comment and there must never be one. */
  const threaded = renderToStaticMarkup(
    <WorktreeDiff
      row={named[0]!}
      base="ms/nova"
      reader={null}
      onBack={() => {}}
      dossier={fixture.card}
      team={fixture.board.team}
      now={now}
      onComment={async () => {}}
    />,
  );
  check(
    "the page offers unified ↔ split, and split is what it defaults to",
    /data-mode="split"[^>]*aria-pressed="true"/.test(threaded) &&
      /data-mode="unified"[^>]*aria-pressed="false"/.test(threaded),
  );
  check(
    "the page asks the file list for a PAGE's measurements, not a drawer's",
    pageView("split").size === "page" && pageView("unified").mode === "unified",
  );
  check(
    "the card's own thread is on the page, whole — the same component, every event",
    threaded.includes('data-testid="worktree-diff-thread"') &&
      threaded.includes('data-testid="thread"') &&
      threaded.includes(`Thread · ${fixture.card.history.length}`) &&
      (threaded.match(/data-testid="event"/g) ?? []).length === fixture.card.history.length,
  );
  check(
    "with the same comment box, and its mention picker",
    threaded.includes('data-testid="comment"'),
  );
  check(
    "no send door, no box — a button with nowhere to send is worse than none",
    !renderToStaticMarkup(
      <WorktreeDiff row={named[0]!} base="ms/nova" reader={null} onBack={() => {}} dossier={fixture.card} />,
    ).includes('data-testid="comment"'),
  );

  /* THE NAV COMES BACK. Selecting a tab clears the open tree — including the tab
   * already active, which is the click that used to do nothing at all. No
   * handler fires here, so the rule is a pure function (`App.tsx::onTab`). */
  /* …and the page OBEYS a selection it is handed. The state was lifted out of
   * this page and into `App`, so the index has to be able to be told which tree
   * is open — otherwise clearing it up there would clear nothing down here. Both
   * props optional: the harness's own `<Worktrees groups={…} />` above is the
   * uncontrolled caller, and it still draws the index. */
  const told = renderToStaticMarkup(
    <Worktrees
      groups={fixture.board.groups}
      milestones={fixture.board.milestones}
      openTree={named[0]!.id}
      onOpenTree={() => {}}
    />,
  );
  check(
    "handed a selection, the index shows that tree's diff instead of itself",
    told.includes('data-testid="worktree-diff"') &&
      told.includes(`data-branch="${named[0]!.id}"`) &&
      !told.includes('data-testid="worktrees"'),
  );
  /* THE BUG A READER HIT (tk-6e7003): nothing above passes a focused chapter —
   * there is no such prop any more — and this is exactly the "All milestones"
   * case, where the page used to compare against `""` and every tree answered
   * "this host could not read that diff". The range line must name the ROW's
   * own chapter branch, which is also criterion 3: it names the base actually
   * used. */
  const chaptered = named.find((w) => w.milestone) ?? named[0]!;
  const ownBase = chaptered.milestone?.branch ?? "";
  const unfocused = renderToStaticMarkup(
    <Worktrees
      groups={fixture.board.groups}
      milestones={fixture.board.milestones}
      openTree={chaptered.id}
      onOpenTree={() => {}}
    />,
  );
  check(
    "with no chapter in focus, a tree still compares against ITS OWN chapter",
    ownBase !== "" &&
      new RegExp(`data-testid="worktree-diff-range"[^>]*>${ownBase}[\\s\\S]*?${chaptered.id}`).test(
        unfocused,
      ) &&
      !unfocused.includes("the trunk this board does not name"),
  );
  // The other half, and the line the spec drew: a row whose chapter cannot be
  // resolved gets NO base — the honest sentence — rather than a borrowed one.
  check(
    "a tree whose chapter cannot be resolved borrows nobody's branch",
    renderToStaticMarkup(
      <Worktrees groups={fixture.board.groups} openTree={chaptered.id} onOpenTree={() => {}} />,
    ).includes("the trunk this board does not name"),
  );
  // The card behind the tree rides through the index untouched — `App` fetches
  // it once, for the drawer and for this page alike, and the page that forgot to
  // pass it on would show a diff with no thread under it.
  check(
    "the card's thread and its send door travel through the index to the page",
    renderToStaticMarkup(
      <Worktrees
        groups={fixture.board.groups}
        milestones={fixture.board.milestones}
        openTree={named[0]!.id}
        onOpenTree={() => {}}
        dossier={fixture.card}
        team={fixture.board.team}
        now={now}
        onComment={async () => {}}
      />,
    ).includes('data-testid="thread"'),
  );
  check(
    "and handed none, it is the index again",
    renderToStaticMarkup(
      <Worktrees
        groups={fixture.board.groups}
        milestones={fixture.board.milestones}
        openTree={null}
        onOpenTree={() => {}}
      />,
    ).includes('data-testid="worktrees"'),
  );
  check("selecting the tab you are on returns to the index", onTab("worktrees").tree === null);
  check("and so does leaving for another one", onTab("board").tree === null);
  check("the tab asked for is the tab you get", onTab("board").tab === "board");

  resetGitAvailability();
}
