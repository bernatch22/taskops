import { renderToStaticMarkup } from "react-dom/server";

import { Board } from "../../src/pages/Board";
import { Monitor } from "../../src/pages/Monitor";
import { KpiRail } from "../../src/components/chrome/KpiRail";
import { WorktreeDiff, Worktrees, rows } from "../../src/pages/Worktrees";
import type {
  BoardPayload
  
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, named } = h;

  /* ── A board older than the `done` group ───────────────────────────
   *
   * `done_total` and `groups.done` arrived in ONE commit (a1d1005), so a board
   * that predates it sends nine groups and no total — and every consumer of
   * either now reads `?? 0` / `?? []`. Same reasoning as 2b for why the payload
   * is built here: no board at this version can produce it. This one is made by
   * DELETING keys from the server's own answer rather than by writing a shape,
   * so it stays a real payload minus exactly what an older one lacks. */

  const older = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  delete older.done_total;
  delete older.groups.done;

  // All THREE consumers, and getting here took a correction worth recording:
  // rendering Monitor + Board alone left two of the three `?? 0` sites dead.
  // Monitor's standing is drawn only when NOBODY holds a lease (LiveLeases'
  // empty branch), and the fixture has a live card — so the leases are emptied
  // on this copy to reach it. `KpiRail` is not on either page at all; it is
  // App's chrome, so it is rendered directly. Mutating each site one at a time
  // is what showed this: with only the two pages, breaking Monitor or KpiRail
  // alone still passed.
  const quiet = JSON.parse(JSON.stringify(older)) as BoardPayload;
  quiet.groups.doing = [];
  quiet.groups.reviewing = [];
  quiet.groups.stalled = [];

  const olderMarkup = renderToStaticMarkup(
    <>
      <Monitor board={older} openCard={() => {}} now={now} />
      <Monitor board={quiet} openCard={() => {}} now={now} />
      <Board board={older} openCard={() => {}} />
      <Worktrees groups={older.groups} />
      <KpiRail board={older} />
    </>,
  );

  // Every assertion below is POSITIVE — it names the figure that must be on
  // screen — and that is a correction, not a style. The first version asserted
  // `!markup.includes("undefined")`, which can never fail: TypeScript's `!`
  // erases at runtime and React renders `undefined` as NOTHING, so a broken
  // fallback leaves an EMPTY element, not the word. Mutating each of the five
  // `?? 0` / `?? []` sites one at a time is what exposed it — four stayed green.
  check(
    "the standing is actually on screen (else the figure check proves nothing)",
    olderMarkup.includes('data-testid="standing"'),
  );
  check("the KPI rail is on screen too", olderMarkup.includes('data-testid="kpis"'));
  check("the worktrees table is on screen too", olderMarkup.includes('data-testid="worktrees"'));

  /* WHO carries each tree (`pages/Worktrees.tsx::owner`). e4 shipped the line
   * and said plainly that nothing asserted its `data-testid` — its branch was
   * cut before this harness could reach the table with real rows. Pinned here,
   * and pinned as the TWO facts the cell answers rather than as its presence:
   * the dev to talk to, and — only when an agent holds it — which process. The
   * unowned row is the other case and the one a `??` chain gets wrong silently:
   * it must read as a sentence, never as an empty cell.
   *
   * `owner()`'s third branch — a dev with no worker half — is NOT asserted, and
   * deliberately: a `dev:` never holds or is handed a card (the role rule the
   * verb registry enforces), so no board can produce that row and building one
   * here would be the hand-written fixture this file exists to avoid.
   *
   * The regex ends at the FIRST `</span>` and the tags are stripped after, so it
   * says nothing about how the line is nested — it used to require the cell's
   * own wrapper (`</span></span>`) and that wrapper was a five-column table's,
   * gone with it. What is asserted is the two facts, in one line, in order. */
  const owners = [...olderMarkup.matchAll(/data-testid="worktree-owner"[^>]*>(.*?)<\/span>/gs)]
    .map((m) => (m[1] ?? "").replace(/<[^>]+>/g, ""));
  check("every worktree row names who carries it", owners.length === rows(older.groups).length);
  check(
    "the dev is the subject of the line, the worker its qualifier",
    owners.some((c) => c === "dev:berna · w1"),
  );
  check(
    "an unowned tree says so in words, never as an empty cell",
    owners.some((c) => c === "nobody — free to take"),
  );

  /* WHICH CHAPTER each tree belongs to — the join `pages/Worktrees.tsx::chapter`
   * makes: the id off the row (`pulse.py::_row`), the words off the payload's own
   * `milestones` list. Both halves are asserted, because either one missing
   * yields the same `null` and only one of them is a bug:
   *   · with the list, a row that has an id is NAMED;
   *   · without it — and equally, on a row from a board one version behind that
   *     sends no `milestone` at all — the answer is `null` and NEVER the raw id. */
  const chapter = fixture.board.milestones[0];
  check(
    "a worktree row carries its chapter, resolved to its title",
    named.some((w) => w.milestone?.id === chapter?.id && w.milestone?.title === chapter?.title),
  );
  check(
    "with no chapters to join against, no row invents one",
    rows(fixture.board.groups).every((w) => w.milestone === null),
  );
  /* THE BASE RIDES IN THE SAME JOIN (tk-6e7003). A card belongs to a chapter
   * regardless of who is looking at it, so the branch a tree is compared
   * against comes off the ROW's chapter and never off the header's focus —
   * which is `null` under "All milestones" and made every diff on this screen
   * say "this host could not read that diff". */
  check(
    "a worktree row carries its own chapter's branch, not the one in focus",
    named.some((w) => w.milestone?.id === chapter?.id && w.milestone?.branch === chapter?.branch),
  );
  const amnesiac = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  for (const group of Object.values(amnesiac.groups)) {
    for (const r of group) delete (r as { milestone?: string }).milestone;
  }
  check(
    "a board one version behind sends no milestone and the row says nothing",
    rows(amnesiac.groups, amnesiac.milestones).every((w) => w.milestone === null),
  );

  /* THE INDEX ITSELF — two columns, four facts on a row, and no heading over
   * nothing. Rendered from the server's own payload WITH its chapters, because
   * the chapter line is a join and only a real `milestones` list can prove it
   * reached the screen; the checks above prove the join, these prove the draw. */
  const indexMarkup = renderToStaticMarkup(
    <Worktrees groups={fixture.board.groups} milestones={fixture.board.milestones} />,
  );
  /* BOTH columns populated — the only state in which two shells are drawn, and
   * therefore the only payload that can pin criterion 3 ("exactly as today").
   * The fixture's own board has nothing integrated, so a row is MOVED into the
   * `done` group rather than invented: same row shape the server sent, in the
   * group the Merged column folds. */
  const both = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  both.groups.done = [both.groups.take[0]!];
  const twoColumns = renderToStaticMarkup(
    <Worktrees groups={both.groups} milestones={both.milestones} />,
  );
  check(
    "with rows on both sides the index is two columns, In progress and Merged",
    (twoColumns.match(/data-testid="worktree-column"/g) ?? []).length === 2 &&
      twoColumns.includes('data-column="In progress"') &&
      twoColumns.includes('data-column="Merged"'),
  );
  check(
    "a row carries its branch, its title and its chapter, resolved",
    indexMarkup.includes('data-testid="worktree-chapter"') &&
      indexMarkup.includes(`⌗ ${chapter?.title ?? ""}`) &&
      indexMarkup.includes(named[0]!.id) &&
      indexMarkup.includes(named[0]!.title),
  );
  /* The other half of `chapter()`, at the RENDER: a row whose id cannot be
   * resolved draws no chapter line at all — never the raw `ms-…`.
   *
   * The rows here KEEP their ids and the list to join against is emptied, which
   * is the case that matters and is not the one `amnesiac` builds: mutating
   * `chapter()` to fall back to the id left the amnesiac render green (its rows
   * carry no id either, so both branches answer `null`) and only this one red. */
  const blind = renderToStaticMarkup(<Worktrees groups={fixture.board.groups} />);
  check(
    "an unresolvable chapter is a missing line, not a printed id",
    !blind.includes('data-testid="worktree-chapter"') && !blind.includes("ms-"),
  );
  // A heading over an empty sub-block is a fact about the layout, not about the
  // board. Emptied at the payload, so the block that goes is a real one.
  const noWaiting = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  noWaiting.groups.take = [];
  noWaiting.groups.blocked = [];
  const trimmed = renderToStaticMarkup(
    <Worktrees groups={noWaiting.groups} milestones={noWaiting.milestones} />,
  );
  check(
    "a sub-block with no rows draws no heading",
    indexMarkup.includes(">waiting<") &&
      !trimmed.includes(">waiting<") &&
      trimmed.includes(">working<"),
  );
  /* A COLUMN WITH NOTHING IN IT IS NOT DRAWN AT ALL. This REPLACES the previous
   * answer — an equal-height shell with a dotted empty field and a sentence in
   * it — which on a real landed chapter was still half a screen of nothing.
   *
   * `older` has no `done` group and nothing integrated, so Merged is that case:
   * one shell survives, and it is the populated one. `1fr` in the surviving
   * track is what makes it full width, and it is the same declaration that
   * draws two, so what is pinned here is the count of shells. */
  check(
    "one empty column: the other is drawn alone, and the empty shell is gone",
    (olderMarkup.match(/data-testid="worktree-column"/g) ?? []).length === 1 &&
      olderMarkup.includes('data-column="In progress"') &&
      !olderMarkup.includes('data-column="Merged"') &&
      !olderMarkup.includes('data-testid="worktrees-empty"'),
  );
  /* BOTH empty: one centred sentence and no column shell at all — not two, not
   * one. The notes are the other half of the criterion: they state the rule the
   * board enforces, which is true whether or not a tree exists. */
  const emptyBoth = renderToStaticMarkup(<Worktrees groups={{} as BoardPayload["groups"]} />);
  check(
    "both empty: one centred message, and not one column shell",
    emptyBoth.includes('data-testid="worktrees-none"') &&
      emptyBoth.includes("No card is open on this chapter") &&
      !emptyBoth.includes('data-testid="worktree-column"') &&
      /data-testid="worktrees-none"/.test(emptyBoth) &&
      emptyBoth.includes("justify-content:center") &&
      // …and none of the shell's furniture came along: no heading, no count,
      // and not the `taskops_assign` hint the dotted field used to carry.
      !emptyBoth.includes("0 trees") &&
      !emptyBoth.includes("taskops_assign hands a card to a worker"),
  );
  const NOTE_TITLES = [
    "Branches are inhabited, not switched",
    "A third lock nobody has to remember",
    "A card merges into its chapter, never main",
  ];
  check(
    "the three notes are drawn in every state, including both-empty",
    NOTE_TITLES.every(
      (t) =>
        emptyBoth.includes(t) &&
        olderMarkup.includes(t) &&
        twoColumns.includes(t) &&
        indexMarkup.includes(t),
    ),
  );
  /* `stretch` survives the change: with one column it decides nothing, with two
   * it is what keeps them level — so it is pinned on the two-column render. */
  check(
    "two columns are still stretched to a shared height",
    twoColumns.includes("align-items:stretch") && !twoColumns.includes("align-items:start"),
  );

  /* THE SECOND SURFACE. A tree is a pull request, so clicking one opens ITS
   * diff, full width — not the card Dossier, which is what this chapter exists
   * to undo. No handler fires under `react-dom/server`, so what is in reach is
   * the other half of criterion 3 and it is the half that was wrong: the page
   * the click has to land on exists, is not the drawer, and replaces the table
   * rather than floating over it. `onOpen` is gone from `WorktreesProps`
   * entirely — that one is a compile error, above, not a string match. */
  const diffPage = renderToStaticMarkup(
    <WorktreeDiff row={named[0]!} base="ms/nova" reader={null} onBack={() => {}} />,
  );
  check(
    "a tree opens its own full-width diff page, naming the branch",
    diffPage.includes('data-testid="worktree-diff"') &&
      diffPage.includes(`data-branch="${named[0]!.id}"`),
  );
  check(
    "the diff page is not the card drawer, and not the table either",
    !diffPage.includes('data-testid="dossier"') && !diffPage.includes('data-testid="worktrees"'),
  );

  /* ITS CHROME — the four things `WorktreeDiff` itself owns, as opposed to the
   * file list it delegates. The back link is the ONLY way out of this surface:
   * there is no router and no history entry, so a page that lost it is a reader
   * trapped on it. The range line and the directory are what say WHICH tree
   * this is; the identity line is who is in it. */
  check(
    "the diff page offers the only way back there is",
    diffPage.includes('data-testid="worktree-diff-back"') && diffPage.includes("← Worktrees"),
  );
  check(
    "it names the range in the direction the diff reads, base ← head",
    /data-testid="worktree-diff-range"[^>]*>ms\/nova[\s\S]*?tk-/.test(diffPage),
  );
  check(
    "and where the tree is on disk, and who is in it",
    diffPage.includes(`.taskops/trees/${named[0]!.id}`) &&
      diffPage.includes('data-testid="worktree-diff-owner"'),
  );
  // The other half of the range line: with no chapter in focus there is no base,
  // and the UI may not guess one (`gitwork/trees.py::base_ref` resolves the trunk
  // from the repo and no verb sends it). It says so instead of drawing an empty
  // side — a bare `←` would read as a range against nothing.
  const noBase = renderToStaticMarkup(
    <WorktreeDiff row={named[0]!} base="" reader={null} onBack={() => {}} />,
  );
  check(
    "with no chapter in focus the base is a sentence, not an empty side",
    noBase.includes("the trunk this board does not name"),
  );
  // NO SLUG → NO ANCHOR, on this surface too. `diffPage` above is rendered from
  // the fixture's own repo-less board, so this is the real case and not a copy.
  check(
    "no slug: the diff page emits no forge anchor at all",
    !diffPage.includes('data-testid="worktree-diff-forge"') && !diffPage.includes("<a "),
  );
  check(
    "with a slug it links out, to a compare and never to an empty href",
    (() => {
      const linked = renderToStaticMarkup(
        <WorktreeDiff
          row={named[0]!}
          base="ms/nova"
          repo={{ host: "github.com", slug: "owner/repo", url: "https://github.com/owner/repo" }}
          reader={null}
          onBack={() => {}}
        />,
      );
      return (
        linked.includes('data-testid="worktree-diff-forge"') &&
        linked.includes(`https://github.com/owner/repo/compare/ms/nova...${named[0]!.id}`) &&
        !linked.includes('href=""')
      );
    })(),
  );
  check(
    "with nothing selected the page is exactly the table",
    olderMarkup.includes('data-testid="worktrees"') &&
      !olderMarkup.includes('data-testid="worktree-diff"'),
  );
  check(
    "a board with no done_total still draws every page",
    olderMarkup.includes('data-testid="monitor"') && olderMarkup.includes('data-testid="board"'),
  );
  check(
    "the standing's closed figure reads 0",
    /<div class="num"[^>]*>0<\/div><div[^>]*>closed this chapter</.test(olderMarkup),
  );
  check(
    "the rail's closed tile reads 0",
    /data-kpi="closed".*?class="num"[^>]*>0<\/span>/s.test(olderMarkup),
  );
  // The header collapses to the plain word: there is no "n of m" to state.
  check("the Done column keeps its plain header", olderMarkup.includes(">Done<"));
  check("nothing rendered NaN", !olderMarkup.includes("NaN"));
}
