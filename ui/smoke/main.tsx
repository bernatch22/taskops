/* What the dashboard has to prove, run against a real board payload.
 *
 * This file is the list. It is aimed at the modules `src/main.tsx` bundles, so
 * every assertion below is about the page that actually ships — and the three
 * seams that make it runnable without a browser are used exactly as their
 * authors designed them:
 *
 *   · `Dossier`, exported beside `Drawer`, because `Overlay` is a PORTAL and a
 *     portal renders nothing under `renderToStaticMarkup`. The document is the
 *     part worth asserting on; the portal is not.
 *   · `submit()`, the send rule as a pure function, so "the draft survives a
 *     refusal" is a claim with no DOM in it.
 *   · `overlayStack`, which holds no listener, so "Escape closes the top-most
 *     only" runs under plain node.
 *
 * The payload is the board's own answer (`tests/test_ui.py` builds it from a
 * live `LocalBoard`), never a hand-written shape: a UI that renders a fixture
 * the server would never send is a UI that renders nothing in production, and
 * that was v1's actual failure. `expect` and `expect_board` travel IN the
 * fixture for the same reason — the Python side names the strings it put on the
 * board and this side proves they reached the screen. */
import { renderToStaticMarkup } from "react-dom/server";

import { Dossier } from "../src/components/card/Drawer";
import { Markdown } from "../src/components/shared/Markdown";
import { CommentBox, submit, watching } from "../src/components/card/CommentBox";
import { RpcError, createClient } from "../src/client";
import { depth, escape, push } from "../src/components/shared/overlayStack";
import { Board } from "../src/pages/Board";
import { Monitor } from "../src/pages/Monitor";
import { LiveLeases } from "../src/components/monitor/LiveLeases";
import { EventStream, FIXTURE_EVENTS } from "../src/components/monitor/EventStream";
import { KpiRail } from "../src/components/chrome/KpiRail";
import { Menu as MilestoneMenu } from "../src/components/chrome/MilestonePicker";
import { WorktreeDiff, Worktrees, rows } from "../src/pages/Worktrees";
import { pageView } from "../src/pages/WorktreeDiff";
import { LEASE_TTL } from "../src/components/monitor/panels";
import { Swarm, topology } from "../src/components/monitor/Swarm";
import {
  cascade,
  gitAvailable,
  noteGitRefusal,
  resetGitAvailability,
  type GitTarget,
} from "../src/links";
import { CommitPatch, DiffPane, FileList, FilesChanged, PatchText } from "../src/components/card/Patch";
import { Thread, detail, oneLine, prose } from "../src/components/card/Thread";
import { split } from "../src/components/card/split";
import { onTab } from "../src/App";
import { Actors, RECENT, actorRows, cardTitles, devRows } from "../src/pages/Actors";
import { DevDetail, DevPanel, devCards } from "../src/components/actors/DevPanel";
import { Daysheet, HourRow, RULE, dayLabel, daysheet, span } from "../src/components/actors/Daysheet";
import { TABS } from "../src/components/chrome/TabNav";
import type {
  ActorSession,
  BoardPayload,
  CardPayload,
  Event,
  GitDiff,
  Milestone,
  ReportPayload,
  ReviewingRow,
  TeamMember,
} from "../src/types";

/** The fixture, as `tests/test_ui.py` writes it. */
export interface Fixture {
  board: BoardPayload;
  card: CardPayload;
  /** substrings the Monitor + Board markup must contain */
  expect_board: string[];
  /** substrings the dossier must contain */
  expect: string[];
  /** the same `board` verb, focused on a chapter that has LANDED */
  board_landed: BoardPayload;
  /** substrings that chapter must still be able to say for itself */
  expect_landed: string[];
  /** the /git door's own answer over a real clone, and its own no-repo refusal */
  git: { compare: GitDiff; no_repo: string; stale: string };
  /** two cards the board actually CLOSED: the reviewed one, then the `no_code`
   *  one. Their histories are where `submitted`, `reviewed` and `status` bodies
   *  come from — see §9. */
  closed: CardPayload[];
}

/** The panes Monitor draws. Nova's own eight — nothing merged, nothing dropped
 *  for lack of a verb (`components/monitor/panels.ts`) — plus `pane-swarm`,
 *  which is this chapter's and is NOT one of Nova's: the topology pane is the
 *  ninth section, at the foot of the left column. */
const PANES = [
  "pane-leases",
  "pane-throughput",
  "pane-health",
  "pane-dag",
  "pane-files",
  "pane-chapter",
  "pane-mentions",
  "pane-events",
  "pane-swarm",
];

export async function smoke(fixture: Fixture): Promise<string[]> {
  const failures: string[] = [];
  const now = Date.now() / 1000;
  const opened: string[] = [];

  function check(name: string, ok: boolean, detail = ""): void {
    if (ok) console.log("ok " + name);
    else failures.push(`${name}${detail ? " — " + detail : ""}`);
  }

  /* ── 1. Monitor draws its eight panes ─────────────────────────────────── */

  const monitor = renderToStaticMarkup(
    <Monitor board={fixture.board} openCard={(id) => opened.push(id)} now={now} />,
  );
  check("monitor renders", monitor.includes('data-testid="monitor"'));
  for (const pane of PANES) {
    check("pane " + pane, monitor.includes(`data-testid="${pane}"`));
  }

  /* ── 1b. Prose is rendered as prose (tk-382948) ────────────────────────
   *
   * The bug, on the freshly migrated axion board: a chapter goal of 4.252
   * characters of real markdown printed as one raw paragraph with the asterisks
   * and the backticks visible. Three claims, and they fail separately:
   *
   *   · the GOAL renders as elements — bold, heading, code, list — and none of
   *     the source markers survives as a character;
   *   · nothing is CUT. A tall goal gets its own scroll, so the last sentence of
   *     the fixture goal must be in the markup;
   *   · a RULE keeps its numbering. This is the one that needed a new mode:
   *     block-rendered, the fixture's second rule (`1. …`) becomes an `<ol>`
   *     inside a tile that already numbers itself.
   *
   * All three read the SAME `monitor` markup rendered above, from the server's
   * own payload — the goal, the rules and the criteria on it are what
   * `tests/test_ui.py::a_board` put on a real board. */

  const slice = (markup: string, from: string, to: string): string => {
    const start = markup.indexOf(from);
    if (start < 0) return "";
    const end = markup.indexOf(to, start);
    return markup.slice(start, end < 0 ? markup.length : end);
  };

  const goal = slice(monitor, 'data-testid="chapter-goal"', 'data-testid="chapter-rules"');
  check("the chapter goal has its own box", goal !== "");
  check(
    "the goal renders as markdown, not as characters",
    goal.includes("<strong") &&
      goal.includes("<code") &&
      goal.includes("<ul") &&
      goal.includes("Dónde está el frente hoy"),
    goal,
  );
  check(
    "no source marker survives as text",
    !goal.includes("**") && !goal.includes("###") && !goal.includes("`"),
    goal,
  );
  check(
    "a long goal scrolls and is never cut",
    goal.includes("max-height") &&
      goal.includes("overflow-y:auto") &&
      // The last words of the fixture goal. A clamp or an ellipsis loses them.
      goal.includes("la restricción que ata es el"),
    goal,
  );

  /* The mentions pane draws a COMMENT — the same string the thread draws — and
   * it was the third screen printing prose raw. Inline, because the row is one
   * line between an author and a card line. */
  const mention = slice(monitor, 'data-testid="pane-mentions"', 'data-testid="pane-events"');
  check(
    "the mention row reads the comment's markdown",
    mention.includes("<code") && mention.includes("round()") && !mention.includes("`"),
    mention,
  );

  const rules = slice(monitor, 'data-testid="chapter-rules"', 'data-testid="chapter-criteria"');
  check(
    "a rule reads its inline markdown",
    rules.includes("<code") && rules.includes("node build.mjs"),
    rules,
  );
  check(
    "…and keeps the tile's numbering: no second list, no block wrapper",
    !rules.includes("<ol") && !rules.includes("<p") && rules.includes("1. The feed socket"),
    rules,
  );
  check(
    "the chapter's criteria go through the same one renderer",
    slice(monitor, 'data-testid="chapter-criteria"', "Integration branch").includes("<code"),
  );

  /* ── 2. The Event stream: rows when it has them, honesty when it does not ─
   *
   * The pane pages the `events` verb itself, so under this harness — which
   * renders once, fires no effect and has no wire — `Monitor` draws it with
   * `client={undefined}` and it must say so rather than claim an empty log.
   * That is the same rule as before: a "0" there is a statement the board never
   * made. What is new is the other half — the pane HAS a populated shape now,
   * and the split that makes it reachable here is `EventStream` staying pure
   * beside its container (`EventStreamPane`), exactly as `Dossier` sits beside
   * `Drawer`. Rendering it with `FIXTURE_EVENTS` is what proves the entry
   * markup a real fetch draws: the kind pill, the actor, the card id, the body.
   */

  check(
    "event stream with no client says nothing asked for the log",
    monitor.includes("has not been handed a client") &&
      monitor.includes('data-testid="pane-empty"'),
  );
  check("event stream counter is — and not 0", monitor.includes("—"));

  const stream = renderToStaticMarkup(
    <EventStream
      events={FIXTURE_EVENTS}
      total={1284}
      now={now}
      more={true}
      loading={false}
      onMore={() => {}}
    />,
  );
  check(
    "event rows draw kind, actor, card and body",
    stream.includes('data-kind="commit"') &&
      stream.includes("berna/m6") &&
      stream.includes("tk-4b37dd") &&
      stream.includes("the pane is drawn before the verb exists"),
  );
  // task="project" is board history — the stream shows it or it is not the log.
  check("the stream draws board-level history", stream.includes(">project<"));
  check("the counter is the log's total", stream.includes("1,284"));
  // The honest-binary rule: a file git could not count is a binary, never +0−0.
  check("a commit shows its numstat", stream.includes("2 files · +3 −1 · 1 binary"));
  check("an older page can be asked for", stream.includes('data-testid="event-more"'));

  /* ── 2b. The reviewing row's version-skew fallback ─────────────────────
   *
   * `LiveLeases.leaseStart` counts a reviewing row down from `review_since` —
   * the REVIEW lease's own acquisition — and falls back to `since`, the WORK
   * lease's, for a board that predates the key. That fallback was correct by
   * construction and had NO test: the branch that wrote it was cut before this
   * harness existed (tk-17d463).
   *
   * The row is assembled HERE rather than taken from the fixture, and that is
   * not the shortcut this file otherwise forbids: the case under test is a
   * payload NO board at this version can produce — `pulse.py::run` always sends
   * the key. There is nowhere else it could come from. What can still be the
   * server's own shape is the row itself, so it is a real `doing` row from the
   * fixture with only the two keys under test set on top of it.
   *
   * `since` is deliberately older than the TTL, which is what makes the two
   * cases distinguishable at all: the floor reads 0s (the payload cannot say
   * more) while the real key reads minutes. Asserting they DIFFER is what
   * would fail if somebody "simplified" `leaseStart` back to `row.since`. */

  const base = fixture.board.groups.doing[0] ?? fixture.board.groups.take[0];
  if (base === undefined) {
    check("a row to build the reviewing case from", false, "the fixture has no open card");
  } else {
    const standing = { ready: 0, blocked: 0, closed: 0 };
    const draw = (row: ReviewingRow): string =>
      renderToStaticMarkup(
        <LiveLeases
          doing={[]}
          reviewing={[row]}
          stalled={[]}
          now={now}
          onOpen={() => {}}
          standing={standing}
        />,
      );

    // The review lease was claimed 60s ago; the work lease, three TTLs ago.
    const withKey = draw({ ...base, since: now - LEASE_TTL * 3, review_since: now - 60 });
    const withoutKey = draw({ ...base, since: now - LEASE_TTL * 3 });

    check("a reviewing row draws with review_since", withKey.includes('data-testid="pane-leases"'));
    check("it counts the REVIEW lease down, not the work lease", withKey.includes("14m"));
    check(
      "a board with no review_since neither crashes nor drops the row",
      withoutKey.includes('data-testid="pane-leases"') && withoutKey.includes(base.id),
    );
    // The floor, verbatim: `TTL - (now - since)` clamped at 0. Never a NaN, and
    // never the 14m it has no way of knowing.
    check(
      "without the key it shows the floor and not a wrong figure",
      withoutKey.includes(">0s<") && !withoutKey.includes("14m") && !withoutKey.includes("NaN"),
    );
    check("the two payloads do not render the same countdown", withKey !== withoutKey);
  }

  /* ── 2c. A board older than the `done` group ───────────────────────────
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
  const named = rows(fixture.board.groups, fixture.board.milestones);
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

  /* ── 2d. A chapter that has LANDED is still a readable chapter ──────────
   *
   * The regression this section exists for: `landed` became a real milestone
   * status and the board payload still filtered `milestones` to `open`, so two
   * finished chapters — 36 cards, their goals, rules and threads — were in the
   * log and on no screen. The payload is the server's own answer to `board
   * milestone=<the landed one>`, which is the read that could not be reached.
   *
   * Three claims, and they are three because they fail separately: the chapter
   * is READABLE (goal, rules, criteria), it is OFFERED by the picker, and it is
   * not drawn as a live board that happens to be quiet. */

  const landedBoard = fixture.board_landed;
  const landedMonitor = renderToStaticMarkup(
    <Monitor board={landedBoard} openCard={() => {}} now={now} />,
  );
  check(
    "a landed chapter still resolves server-side",
    landedBoard.milestone !== null && landedBoard.milestone.status === "landed",
    JSON.stringify(landedBoard.milestone),
  );
  for (const text of fixture.expect_landed) {
    check("the landed chapter shows " + JSON.stringify(text), landedMonitor.includes(text));
  }
  check(
    "every pane still draws over it",
    PANES.every((pane) => landedMonitor.includes(`data-testid="${pane}"`)),
  );
  // The empty state names the state instead of implying a live board that
  // stopped: "0 ready to pick up" is true of a landed chapter and reads as work
  // somebody abandoned.
  check(
    "Live leases says the chapter landed",
    landedMonitor.includes("This chapter has landed"),
  );
  check(
    "and does not offer work to pick up",
    !landedMonitor.includes("ready to pick up") && !landedMonitor.includes("NaN"),
  );

  // The picker's open menu. Rendered directly because the dropdown is state
  // behind a click and no handler fires here — that is what `Menu` is exported
  // for (MilestonePicker.tsx).
  const menu = renderToStaticMarkup(
    <MilestoneMenu
      milestones={[...fixture.board.milestones, ...landedBoard.milestones]}
      landedTotal={landedBoard.landed_total}
      selected=""
      anchor={{ current: null }}
      onClose={() => {}}
      onSelect={() => {}}
    />,
  );
  const landedId = landedBoard.milestone?.id ?? "";
  check("the menu offers the landed chapter at all", menu.includes(landedId));
  check(
    "and offers it as history, told apart from what is in flight",
    menu.includes('data-testid="milestone-landed"') &&
      new RegExp(`data-milestone="${landedId}" data-landed="1"`).test(menu),
    menu,
  );

  /* ── 2e. SEVERAL chapters open is a list, not an apology (tk-13d115) ─────
   *
   * `_facts.in_scope` returns None for several open chapters — it refuses to
   * guess — and the Chapter pane used to read that refusal as a fault: a
   * paragraph telling the reader to "land or drop the finished ones" and nothing
   * at all about either chapter. Two open chapters is a working board.
   *
   * The payload is the server's own, with the landed chapter re-opened and the
   * focus cleared: exactly the shape a board with two chapters in flight sends,
   * and every field on both chapters is a real one the board wrote. */

  const several = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const second = JSON.parse(
    JSON.stringify(fixture.board_landed.milestone),
  ) as Milestone | null;
  const first = several.milestone;
  check(
    "the two-chapter fixture has two real chapters",
    first !== null && second !== null,
  );
  if (first && second) {
    second.status = "open";
    several.milestone = null; // what the server sends when it cannot focus one
    // The re-opened one FIRST, so the row that expands by default is the chapter
    // that has rules AND criteria — criterion 2 is about the whole body, and a
    // chapter with neither would prove only that the goal is drawn.
    // …and a THIRD that has LANDED, in the same list, because that is exactly
    // how the payload sends it (`_facts.chapters`: open first, landed after).
    // A landed chapter is history and must not be listed as in flight.
    const ghost: Milestone = {
      ...first,
      id: "ms-hasalreadylanded",
      title: "a landed chapter",
      status: "landed",
    };
    several.milestones = [second, first, ghost];
    // One card moved to the second chapter, so the counts have something to
    // disagree about if they are ever invented rather than folded.
    const moved = several.groups.take[0];
    if (moved) moved.milestone = second.id;

    const many = renderToStaticMarkup(
      <Monitor
        board={several}
        openCard={() => {}}
        now={now}
        onFocusChapter={() => {}}
      />,
    );
    check(
      "with two chapters open the pane apologises for nothing",
      !many.includes("Land or drop the finished ones"),
      many,
    );
    check(
      "it lists BOTH chapters as foldable rows",
      many.includes(first.title) &&
        many.includes(second.title) &&
        (many.match(/data-testid="chapter-fold"/g) ?? []).length === 2,
      many,
    );
    // A real button with `aria-expanded`, not an arrow glyph: the first row open,
    // the rest closed.
    check(
      "the first row is expanded and the second is not",
      (many.match(/aria-expanded="true"/g) ?? []).length === 1 &&
        (many.match(/aria-expanded="false"/g) ?? []).length === 1,
      many,
    );
    // Criterion 2: the expanded body is what the single-chapter pane draws —
    // goal, rules, criteria (drawn on no other screen) and the branch footer.
    check(
      "the expanded body is the whole chapter, criteria included",
      many.includes(second.goal) &&
        // …through the SAME `Goal` the focused pane draws (tk-382948): the
        // accordion was the second of the two sites printing it raw, and a fix
        // applied to one of two call sites is the drift this pane already has a
        // post-mortem about.
        many.includes('data-testid="chapter-goal"') &&
        many.includes('data-testid="chapter-rules"') &&
        many.includes('data-testid="chapter-criteria"') &&
        many.includes("Integration branch") &&
        many.includes(second.branch),
      many,
    );
    check(
      "the collapsed one shows its title and NOT its goal",
      // A RENDERED fragment, not the raw string: since the goal became markdown
      // the source text appears nowhere at all, so `!includes(first.goal)` is
      // true even for a pane that draws the whole thing. A heading the renderer
      // emits verbatim is what can still tell the two apart.
      many.includes(first.title) &&
        !many.includes(first.goal) &&
        !many.includes("Dónde está el frente hoy"),
      many,
    );
    check(
      "the chapter that landed is not listed — this pane is what is in flight",
      !many.includes(ghost.title) && !many.includes(ghost.id),
      many,
    );
    // And the common case is untouched: one chapter in focus is the pane that
    // was always there — no rows, no fold arrow, no accordion chrome.
    const focusedOne = renderToStaticMarkup(
      <Monitor
        board={fixture.board}
        openCard={() => {}}
        now={now}
        onFocusChapter={() => {}}
      />,
    );
    check(
      "with a chapter in focus the pane renders as it always did",
      !focusedOne.includes('data-testid="chapter-fold"') &&
        !focusedOne.includes('data-testid="chapter-focus"') &&
        focusedOne.includes("Chapter in focus"),
      focusedOne,
    );
    // The counts are FOLDED from the rows, never invented — and a payload whose
    // rows name no chapter draws no count at all rather than `0 open` on each.
    check(
      "each row says how many open cards it carries",
      (many.match(/data-testid="chapter-open-count"/g) ?? []).length === 2,
      many,
    );
    const blind = JSON.parse(JSON.stringify(several)) as BoardPayload;
    for (const rows of Object.values(blind.groups)) {
      for (const row of rows as { milestone?: string }[]) delete row.milestone;
    }
    const blindMarkup = renderToStaticMarkup(
      <Monitor board={blind} openCard={() => {}} now={now} />,
    );
    check(
      "with no row naming a chapter, no count is drawn rather than a wrong one",
      !blindMarkup.includes('data-testid="chapter-open-count"') &&
        blindMarkup.includes('data-testid="chapter-fold"'),
      blindMarkup,
    );
    // The `focus` action is the header picker's own setter arriving as a prop —
    // no handler fires here, so what is pinned is that the control exists only
    // when there is somewhere for it to go. `App.tsx` passes `setMilestone`.
    const noFocus = renderToStaticMarkup(
      <Monitor board={several} openCard={() => {}} now={now} />,
    );
    check(
      "focus is offered when a setter is passed and not otherwise",
      (many.match(/data-testid="chapter-focus"/g) ?? []).length === 2 &&
        !noFocus.includes('data-testid="chapter-focus"'),
      noFocus,
    );
  }

  /* ── 3. The Board page draws its columns ──────────────────────────────── */

  const board = renderToStaticMarkup(
    <Board board={fixture.board} openCard={(id) => opened.push(id)} />,
  );
  check("board renders", board.includes('data-testid="board"'));
  for (const column of ["Ready", "In flight", "Review", "Blocked", "To merge", "Done"]) {
    check("column " + column, board.includes(column));
  }
  check(
    "every open card has a tile",
    fixture.board.groups.take.every((row) => board.includes(row.id)),
  );

  for (const text of fixture.expect_board) {
    check("board shows " + JSON.stringify(text), (monitor + board).includes(text));
  }

  /* ── 3b. A tile names its chapter only when the view holds more than one ──
   *
   * Three states, and all three are properties of the VIEW, not of a tile — so
   * all three are reached by rendering the whole Board, exactly as App does.
   * The spanning payload is the server's own answer with ONE row moved to the
   * chapter the fixture already landed: no shape is written here, and the
   * chapter that does the moving is a real `Milestone` the board sent. */

  const focused = renderToStaticMarkup(<Board board={fixture.board} openCard={() => {}} />);
  check(
    "with one chapter in view no tile repeats it — the header already said it",
    !focused.includes('data-testid="tile-chapter"'),
    focused,
  );

  /* A tile's NOTE — the submit note or the reviewer's words, "verbatim, never
   * summarised" — was the fourth screen printing prose raw (tk-382948). The
   * payload is the server's own with one open row moved into `review`, the
   * group `Board.tsx` reads `row.text` for; the text moved with it is a real
   * released note off the same board. */
  const handedBoard = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const handed = handedBoard.groups.take[0] ?? handedBoard.groups.doing[0];
  if (handed) {
    handedBoard.groups.review = [
      { ...handed, holder: null, text: "got to the rounding — see `src/tax.py::half_up`" },
    ];
    const withNote = renderToStaticMarkup(<Board board={handedBoard} openCard={() => {}} />);
    check(
      "a tile's note reads its markdown instead of printing the backticks",
      withNote.includes("<code") &&
        withNote.includes("src/tax.py::half_up") &&
        !withNote.includes("`src/tax.py"),
      withNote,
    );
  }

  const spanBoard = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const other = fixture.board_landed.milestone;
  const here = spanBoard.milestone;
  const moved = spanBoard.groups.take[0];
  check(
    "the spanning fixture has the two chapters and a row to move",
    other !== null && here !== null && moved !== undefined,
  );
  if (other && here && moved) {
    spanBoard.milestones = [...spanBoard.milestones, other];
    moved.milestone = other.id;
    // A third row pointing at a chapter this payload cannot name — aged past
    // `milestones`' cap, or a board one version behind. It must draw NOTHING.
    const orphan = spanBoard.groups.blocked[0] ?? spanBoard.groups.take[1];
    if (orphan) orphan.milestone = "ms-doesnotexist";

    const spanning = renderToStaticMarkup(<Board board={spanBoard} openCard={() => {}} />);
    check(
      "with two chapters in view the moved tile names its own",
      spanning.includes(`⌗ ${other.title}`),
      spanning,
    );
    check(
      "and the rows that stayed name theirs",
      spanning.includes(`⌗ ${here.title}`),
      spanning,
    );
    check(
      "a chapter that does not resolve draws nothing, never the raw id",
      !spanning.includes("ms-doesnotexist"),
      spanning,
    );
  }

  /* ── 4. The dossier — including the criteria v1 never drew ─────────────── */

  const dossier = renderToStaticMarkup(
    <Dossier
      dossier={fixture.card}
      openId={fixture.card.card.id}
      team={fixture.board.team}
      now={now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  for (const text of fixture.expect) {
    check("dossier shows " + JSON.stringify(text), dossier.includes(text));
  }
  check("criteria are on screen", dossier.includes('data-testid="criteria"'));
  check(
    "every criterion is drawn, numbered",
    // Split on the backticks: a criterion is drawn through the ONE renderer now
    // (tk-382948), so a code span reaches the page as `<code>…</code>` and the
    // criterion is no longer one raw substring. Every piece of it is still
    // there, which is the claim — "drawn" was never "drawn as plain text".
    fixture.card.card.criteria.every((text) =>
      text.split("`").every((piece) => piece === "" || dossier.includes(piece)),
    ),
  );
  check("the comment box is the foot", dossier.includes('data-testid="comment-box"'));

  /* …and drawn through the ONE renderer, inline. The check above splits on the
   * backticks, so it passes for a criterion printed raw — mutating this site
   * came back green until this was added. What cannot be green raw: a `<code>`
   * element per code span, one inline render per criterion, and no `<p>` (the
   * block wrapper) anywhere in the section. */
  const crit = slice(dossier, 'data-testid="criteria"', "Commits ·");
  check(
    "a criterion reads its markdown and keeps its number",
    crit !== "" &&
      crit.includes("<code") &&
      crit.includes("npm run typecheck") &&
      !crit.includes("`") &&
      !crit.includes("<p") &&
      (crit.match(/data-testid="markdown-inline"/g) ?? []).length ===
        fixture.card.card.criteria.length,
    crit,
  );

  /* CRITERION 3 of tk-382948: the spec and the thread render EXACTLY as they
   * did. The proof is byte-level and it is the strongest one available here —
   * the dossier must CONTAIN, verbatim, what `<Markdown>` produces for the very
   * same string on its own. Had the inline mode leaked into the default path
   * (or had the spec been switched to it), the substring would not be there. */
  const spec = fixture.card.card.spec;
  check(
    "the spec is still the block renderer's own output, byte for byte",
    spec !== "" && dossier.includes(renderToStaticMarkup(<Markdown text={spec} />)),
  );
  const said = fixture.card.history.find((e) => e.kind === "comment");
  const saidText = typeof said?.body["text"] === "string" ? said.body["text"] : "";
  check(
    "a comment is too — the thread is untouched",
    saidText !== "" && dossier.includes(renderToStaticMarkup(<Markdown text={saidText} />)),
  );
  /* The released note and the reviewer's verdict were the other raw draws in
   * this document. Both are prose and both now read their markdown. */
  /* SCOPED to the section, not to the whole document: `<code>` appears in the
   * criteria too, so the unscoped form of this check passed with the resume note
   * printed raw. */
  const resume = slice(dossier, "Resume note · previous worker", "Worktree");
  check(
    "the previous worker's released note reads its markdown",
    resume.includes("<code") &&
      resume.includes("src/tax.py::half_up") &&
      !resume.includes("`"),
    resume,
  );

  /* The reviewer's verdict is the last raw draw in this document, and no fixture
   * board can reach it: `standing.verdict === "changes"` needs a card that was
   * handed in and bounced, which would move the card this dossier is about out
   * of the group every other assertion here reads. So it is the same exception
   * `2b` documents — the server's own payload, with the ONE key under test set
   * on top of it, in the shape `core/review.py::Standing` sends. */
  const bounced = JSON.parse(JSON.stringify(fixture.card)) as CardPayload;
  bounced.standing = {
    submitted_at: now - 600,
    submitted_by: "agent:berna/w2",
    verdict: "changes",
    note: "the rounding is still `float` in one branch",
    reviewed_by: "dev:berna",
    reviewed_at: now - 60,
  };
  const changes = renderToStaticMarkup(
    <Dossier
      dossier={bounced}
      openId={bounced.card.id}
      team={fixture.board.team}
      now={now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  const verdict = slice(changes, 'data-testid="verdict"', "</div></div>");
  check(
    "the reviewer's words read their markdown too",
    verdict.includes("<code") && verdict.includes("float") && !verdict.includes("`"),
    verdict,
  );

  /* ── 5. The one write: the comment box posts `update` ──────────────────── */

  const posted: unknown[] = [];
  const client = createClient("/b", fakeStorage(), {
    fetch: (async (_url: string, init: { body: string }) => {
      posted.push(JSON.parse(init.body));
      return { json: async () => ({ ok: true, seq: 1, data: {} }) };
    }) as unknown as typeof globalThis.fetch,
  });
  const task = fixture.card.card.id;
  const send = async (text: string, mentions: string[]): Promise<void> => {
    // The same call `useBoard.comment` makes: `update` with comment= and
    // mentions= riding on it. No status: the browser does not move a card.
    await client.rpc("update", { task, comment: text, mentions });
  };

  const sent = await submit("Decimal, please", ["dev:berna"], send);
  check("send posts one call", posted.length === 1);
  check(
    "the call is update, with the comment and the mentions",
    JSON.stringify(posted[0]) ===
      JSON.stringify({
        verb: "update",
        args: { task, comment: "Decimal, please", mentions: ["dev:berna"] },
      }),
    JSON.stringify(posted[0]),
  );
  check("an accepted comment clears the draft", sent.draft === "" && sent.failed === "");

  const refusal = async (): Promise<void> => {
    throw new RpcError("refused", "Refused: taskops_take task=tk-1 first");
  };
  const kept = await submit("a paragraph", ["dev:berna"], refusal);
  check("the draft survives a refusal", kept.draft === "a paragraph");
  check("the mentions survive it too", kept.picked.length === 1);
  check(
    "the refusal is shown in the server's own words",
    kept.failed === "Refused: taskops_take task=tk-1 first",
  );

  const blank = await submit("   ", [], async () => {
    throw new Error("an empty comment must never reach the board");
  });
  check("an empty draft sends nothing", blank.failed === "" && posted.length === 1);

  /* The picker offers who is LIVE, not everybody seen today. The clock is the
     board's own lease TTL, so a member last seen three TTLs ago is not somebody
     you reach by writing to them and is not drawn. */
  const chipsOf = (markup: string): number => markup.split('data-testid="mention-pick"').length - 1;
  const member = (actor: string, ago: number): TeamMember => ({ actor, seen: 0, ago });
  const noSend = async (): Promise<void> => undefined;

  const mixed = renderToStaticMarkup(
    <CommentBox
      team={[member("agent:berna/live", LEASE_TTL - 60), member("agent:berna/gone", LEASE_TTL * 3)]}
      onSend={noSend}
    />,
  );
  check("only the live member is offered", chipsOf(mixed) === 1, mixed);
  check("the stale member is not offered", !mixed.includes("agent:berna/gone"));
  check("with somebody live there is no sentence", !mixed.includes('data-testid="nobody-live"'));

  const allStale = renderToStaticMarkup(
    <CommentBox
      team={[member("agent:berna/gone", LEASE_TTL + 1), member("dev:berna", LEASE_TTL * 90)]}
      onSend={noSend}
    />,
  );
  check("nobody live draws no chips", chipsOf(allStale) === 0, allStale);
  check(
    "and one honest sentence instead",
    allStale.includes('data-testid="nobody-live"') &&
      allStale.includes("a comment with no address still lands on the card"),
  );

  /* A window WATCHING a public board: the box says so instead of offering a
     form whose every send is a 409. `watching()` is the whole rule and it reads
     the SERVER's answer — an older payload with no `actor` is not anonymous. */
  check("anon is watching", watching({ actor: "anon" }));
  check("a named reader is not", !watching({ actor: "dev:berna" }));
  check("and neither is a payload that predates the key", !watching({}) && !watching(undefined));

  const window_ = renderToStaticMarkup(
    <CommentBox team={[member("agent:berna/live", 10)]} onSend={noSend} readOnly />,
  );
  check("a watcher gets no textarea and no send", !window_.includes('data-testid="send"'), window_);
  check("no mention picker either", chipsOf(window_) === 0);
  check(
    "and the refusal names how a key gets registered",
    window_.includes('data-testid="read-only"') && window_.includes("--key ~/.ssh/id_ed25519"),
  );
  check(
    "a reader WITH a credential still gets the form",
    renderToStaticMarkup(<CommentBox team={[member("agent:berna/live", 10)]} onSend={noSend} />)
      .includes('data-testid="send"'),
  );

  /* ── 6. Escape closes the top-most overlay only ────────────────────────── */

  const closed: string[] = [];
  const popDrawer = push(() => closed.push("drawer"));
  const popConfirm = push(() => closed.push("confirm"));
  check("two overlays are stacked", depth() === 2);
  check("escape closes the top-most", escape() && JSON.stringify(closed) === '["confirm"]');
  popConfirm();
  check("escape then closes the one below", escape() && closed.length === 2);
  popDrawer();
  check("an empty stack swallows nothing", escape() === false && depth() === 0);

  /* ── 7. The board points at the code — and only when it can ───────────────
   *
   * `BoardPayload.repo` is the whole switch (`links.tsx`). The fixture is a
   * REAL board with no `origin` recorded, so the no-slug case is the payload
   * above, unmodified — the case that must change NOTHING. The with-slug case
   * is built here for the same reason as 2b and 2c: this board cannot produce
   * one, and the copy is the server's own answer with the key set on top.
   *
   * The gitlab pass is not a duplicate. It is the assertion that a non-GitHub
   * host is a VALUE and not a second code path: same components, same props,
   * a different row of `BY_HOST`, and `/-/commit/` instead of `/commit/`.
   * Delete that row and this is the check that goes red. */

  const drawAll = (payload: BoardPayload, dossierCard: CardPayload): string =>
    renderToStaticMarkup(
      <>
        <Monitor board={payload} openCard={() => {}} now={now} />
        <Worktrees
          groups={payload.groups}
          milestones={payload.milestones}
          repo={payload.repo}
        />
        <Dossier
          dossier={dossierCard}
          openId={dossierCard.card.id}
          team={payload.team}
          now={now}
          onClose={() => {}}
          onComment={async () => {}}
          repo={payload.repo}
        />
      </>,
    );

  const REPO = {
    host: "github.com",
    slug: "owner/repo",
    url: "https://github.com/owner/repo",
  };

  const linkable = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  linkable.repo = REPO;
  const onGitlab = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  onGitlab.repo = { host: "gitlab.com", slug: "g/sub/p", url: "https://gitlab.com/g/sub/p" };

  // A commit with counts, on the dossier's commit list AND on its thread — the
  // two places a sha is drawn, and the two `numstat` readers (a typed field and
  // `readNumstat` over an open event body) that must agree.
  const counted = JSON.parse(JSON.stringify(fixture.card)) as CardPayload;
  const sha = counted.commits[0]?.sha ?? "0".repeat(40);
  const numstat = { "src/a.py": [12, 3], "ui/logo.png": null };
  counted.commits[0] = { sha, subject: "a commit with counts", numstat: { "src/a.py": [12, 3], "ui/logo.png": null } };
  counted.history = [
    ...counted.history,
    {
      id: "smoke-commit",
      ts: now - 60,
      actor: "agent:berna/e3",
      kind: "commit",
      scope: "task",
      subject: counted.card.id,
      body: { sha, subject: "a commit with counts", numstat },
    } as unknown as (typeof counted.history)[number],
  ];

  const noSlug = drawAll(fixture.board, counted);
  const slug = drawAll(linkable, counted);
  const gitlab = drawAll(onGitlab, counted);

  // NO SLUG → NO LINKS, and no layout shift. Not "no href" — no ANCHOR: a
  // disabled-looking link is the dead anchor the chapter's rule forbids.
  check("no slug: not one anchor is rendered", !noSlug.includes("<a "));
  check(
    "no slug: no compare offered anywhere",
    !noSlug.includes("card-compare") &&
      !noSlug.includes("chapter-compare") &&
      !noSlug.includes("worktree-compare"),
  );
  // The layout does not depend on the slug either. This used to assert the
  // five-column grid string, which pinned a table that no longer exists; what it
  // was really about survives, so that is what it says now: with no anchor to
  // draw, the index still draws every column that has rows and every row in
  // them. The count is the fixture's own — one column, because nothing on this
  // board is integrated — and it is derived rather than written, so it follows
  // the payload instead of pinning a number.
  check(
    "no slug: the worktrees index is whole anyway",
    (noSlug.match(/data-testid="worktree-column"/g) ?? []).length === 1 &&
      (noSlug.match(/data-testid="worktree-row"/g) ?? []).length ===
        rows(fixture.board.groups).length,
  );

  check("a sha links to the commit page", slug.includes(`https://github.com/owner/repo/commit/${sha}`));
  check("the thread's sha is a link too", slug.includes('data-testid="thread-commit-link"'));
  check(
    "the card offers its PR-diff view against the chapter branch",
    slug.includes('data-testid="card-compare"') && /compare\/ms[^"]*\.\.\.tk-/.test(slug),
  );
  // …with NO base in the URL: the trunk is not on the board, so the forge's own
  // default branch answers. A `main` appearing here is the UI guessing.
  check(
    "the chapter compares against the trunk, whose name the UI does not know",
    slug.includes('data-testid="chapter-compare"') &&
      /href="https:\/\/github\.com\/owner\/repo\/compare\/ms[^".]*"/.test(slug),
  );
  check("a worktree row compares too", slug.includes('data-testid="worktree-compare"'));
  // …and it is the row button's SIBLING, never its child. That is the invariant
  // the old reserved sixth column existed to buy: an `<a>` inside a `<button>`
  // is invalid HTML and unreachable by keyboard. The column is gone; the rule it
  // was protecting is asserted directly instead.
  check(
    "the compare anchor sits beside the row button, not inside it",
    /data-testid="worktree-row"[\s\S]*?<\/button><a /.test(slug),
  );
  check(
    "every outward anchor is a new tab with rel=noopener",
    (slug.match(/<a /g) ?? []).length === (slug.match(/rel="noopener noreferrer"/g) ?? []).length,
  );
  check("no anchor has an empty href", !slug.includes('href=""'));

  check("the numstat draws +12", slug.includes(">+12<"));
  check("and −3, with a minus sign", slug.includes(">−3<"));
  // The honest half: git prints `-` for a binary and the payload stores null.
  // A "0" here would be the UI claiming a measurement nobody made.
  check("a binary is counted as binary, never as a zero", slug.includes("1 binary"));
  check(
    "both numstat readers agree — the commit list and the thread",
    (slug.match(/data-testid="numstat"/g) ?? []).length >= 2,
  );

  check(
    "a non-github host is a VALUE: /-/commit and /-/compare",
    gitlab.includes(`https://gitlab.com/g/sub/p/-/commit/${sha}`) && gitlab.includes("/-/compare/"),
  );
  check("nothing rendered NaN or an undefined path", !slug.includes("NaN") && !slug.includes("/undefined"));

  /* ── 8. The diff comes from the viewer's own clone ───────────────────────
   *
   * `fixture.git` is the /git DOOR'S OWN answer over a real two-branch repo,
   * and `fixture.git.no_repo` its own refusal on a host that has none
   * (`tests/test_ui.py::a_diff`). Both had to come from the server for the same
   * reason the board payload does — and the refusal doubly so: `noteGitRefusal`
   * matches on the WORDS of `gitdoor.py::NO_REPO`, so a message written by hand
   * here would pass while the real cascade never flipped.
   *
   * WHAT THIS CANNOT REACH, said as plainly as tk-e586f5 said it: `useGitDiff`
   * fetches inside a `useEffect`, and `react-dom/server` fires no effects. So
   * `FilesChanged` and `CommitPatch` can never reach their PATCH step under this
   * harness, and the step they do reach — the honest fallback — is what is
   * asserted on them. The patch renderer itself is reached the way it is
   * designed to be: `cascade()` is pure and `DiffPane` takes a step, so every
   * one of the four is drawn here from a real payload. The gap is the fetch
   * firing, not what it draws. It is covered end to end on the Python side
   * (`tests/test_topology.py`), never in a browser.
   */

  const git = fixture.git;
  const target: GitTarget = { kind: "compare", base: "main", head: "tk-a11111" };

  check("the door answered with a real range", git.compare.head.length === 40);
  check(
    "and with the numstat vocabulary, per file",
    Object.keys(git.compare.stat).sort().join(",") === "pdf.py,tax.py",
    JSON.stringify(git.compare.stat),
  );

  // Step 2 — the patch, drawn from the door's own text.
  const patch = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: git.compare, loading: false })} />,
  );
  check("the patch pane draws the diff", patch.includes('data-testid="patch"'));
  check("a hunk header is drawn as a header", patch.includes("@@"));
  check("an added line keeps its +", patch.includes("+REDUCED = 0.10"));
  check("the file's own header is in the text", patch.includes("diff --git"));
  check("an untruncated patch says nothing about truncation", !patch.includes("patch-truncated"));

  // A CUT patch: the server's own payload with the one key a big range sets.
  const cut = renderToStaticMarkup(
    <DiffPane
      step={cascade(REPO, target, {
        diff: { ...git.compare, truncated: true },
        loading: false,
      })}
    />,
  );
  check("a cut patch says it was cut, with the cap in bytes", cut.includes('data-testid="patch-truncated"'));
  check("and offers the whole of it on the forge", cut.includes('data-testid="patch-truncated-link"'));
  check("the cap is a figure, not an adjective", cut.includes(git.compare.cap.toLocaleString()));

  /* THE FILE LIST the diff PAGE hands its whole range to — drawn from the same
   * door payload, through `FileList`, the pure half of `FilesChanged` (the
   * asking half is a `useEffect` and no effect fires here). The page adds
   * exactly one thing to it, `summary`, so that is what is asserted beside the
   * rows: `N files changed` plus the range's own +/−. */
  const listed = renderToStaticMarkup(
    <FileList
      reader={null}
      repo={REPO}
      target={target}
      step={cascade(REPO, target, { diff: git.compare, loading: false })}
      summary={true}
    />,
  );
  check(
    "the range is a file list, one row per file the door named",
    listed.includes('data-testid="files-changed"') &&
      (listed.match(/data-testid="changed-file"/g) ?? []).length ===
        Object.keys(git.compare.stat).length,
  );
  check(
    "every path the door named is on it",
    Object.keys(git.compare.stat).every((p) => listed.includes(p)),
  );
  check(
    "and the page's own addition, the summary bar, counts those same files",
    listed.includes('data-testid="files-changed-summary"') &&
      listed.includes(`${Object.keys(git.compare.stat).length} files changed`),
  );
  // The drawer's pane never drew a bar, and still must not: `summary` is a prop,
  // not a thing the component decided for itself.
  check(
    "without the prop there is no bar",
    !renderToStaticMarkup(
      <FileList
        reader={null}
        repo={REPO}
        target={target}
        step={cascade(REPO, target, { diff: git.compare, loading: false })}
      />,
    ).includes('data-testid="files-changed-summary"'),
  );

  // Step 1 — loading. Not a spinner forever: it says what it is waiting on.
  const waiting = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: null, loading: true })} />,
  );
  check("waiting draws the loading step", waiting.includes('data-testid="patch-loading"'));

  /* Steps 3 and 4 — the no-repo host, discovered from the door's own words.
   * `noteGitRefusal` is the only way the flag moves, and `why()` changes with
   * it: before the refusal the sentence is "could not read that diff"; after it,
   * "this host serves boards, not a clone". Asserting BOTH is what would fail if
   * the flag stopped mattering. */
  const beforeRefusal = cascade(null, target, { diff: null, loading: false });
  check(
    "before any refusal the sentence is about this read, not about the host",
    beforeRefusal.step === "none" && beforeRefusal.why.includes("could not read that diff"),
  );
  /* The STALE CLONE — the everyday case once the board is shared. The card is
   * closed and its branch is on origin; this clone has simply never fetched it.
   * That is not an error and must not read as one, and only the door knows
   * WHICH ref was missing, so the cascade quotes it rather than composing a
   * sentence of its own. Asserted before the no-repo flag is flipped, because
   * afterwards every pane would say the host has no clone. */
  const stale = cascade(null, target, {
    diff: null,
    loading: false,
    refusal: git.stale,
  });
  check(
    "a ref this clone lacks is quoted in the door's own words",
    stale.step === "none" && stale.why.includes("not in your clone yet"),
  );
  check(
    "and it names the git fetch that brings it",
    stale.step === "none" && stale.why.includes("git fetch origin tk-b22222"),
  );
  const staleForge = cascade(REPO, target, { diff: null, loading: false, refusal: git.stale });
  check(
    "the same words ride the forge step, which is still offered",
    staleForge.step === "forge" && staleForge.why.includes("git fetch origin"),
  );
  check(
    "a stale ref does NOT flip availability — ask again for the next one",
    (noteGitRefusal(git.stale), gitAvailable()),
  );

  noteGitRefusal(git.no_repo);
  check("the door's own words flip availability", !gitAvailable());
  check(
    "an unknown ref would NOT have flipped it",
    (resetGitAvailability(), noteGitRefusal(git.stale), gitAvailable()),
  );
  noteGitRefusal(git.no_repo);

  const withSlug = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: null, loading: false })} />,
  );
  check("no clone, but a slug: the forge step", withSlug.includes('data-testid="patch-forge"'));
  check("with a real anchor on it", withSlug.includes('data-testid="patch-forge-link"') && !withSlug.includes('href=""'));
  check(
    "and it reads as this host being what it is, not as an error",
    withSlug.includes("serves boards, not a clone"),
  );

  const bare = renderToStaticMarkup(
    <DiffPane step={cascade(null, target, { diff: null, loading: false })} />,
  );
  check("no clone and no slug: one honest sentence", bare.includes('data-testid="patch-none"'));
  check("with no anchor at all", !bare.includes("<a "));
  check("that says both halves", bare.includes("no remote to link out to"));

  /* The two containers, under the harness's real limitation: no effect fires,
   * so both sit at the cascade's fallback — and that is a REAL state (a phone
   * on a `taskops serve` host), which must still be a readable pane and never a
   * dead anchor. */
  const filesChanged = renderToStaticMarkup(
    <FilesChanged reader={undefined} repo={REPO} base="ms/x" head="tk-a11111" />,
  );
  check(
    "Files changed with no reader falls to the forge, not to nothing",
    filesChanged.includes('data-testid="patch-forge"') && !filesChanged.includes('href=""'),
  );
  const fold = renderToStaticMarkup(
    <CommitPatch reader={undefined} repo={REPO} sha={sha} />,
  );
  check("a commit row offers its fold", fold.includes('data-testid="patch-toggle"'));
  check("and fetches nothing until it is opened", !fold.includes('data-testid="patch-loading"'));

  /* ── 9. The diff reads like a page ────────────────────────────────────────
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

  /* ── 9. Swarm topology: who is attached to what ──────────────────────────
   *
   * The pane's whole claim is that it invents nothing — it folds four slices
   * the board already sends into nodes and edges. `topology()` is that fold,
   * exported as a pure function precisely so it can be asserted here WITHOUT
   * rendering, which is also why the layout is arithmetic and not a force
   * simulation: a simulation settles over frames and this harness has none.
   *
   * The rows are built here rather than taken from the fixture for the reason
   * §2b builds its own: this repo's board cannot be made to hold a live work
   * lease AND a live review lease on one card AND two cards declaring one path,
   * all at the same instant, from a test. The SHAPES are the payload's own
   * (`BoardRow`, `ReviewingRow`, `TeamMember` — the compiler checks that), and
   * the pane against the real fixture is asserted in §1 with the other panes. */

  const swarmRow = (id: string, holder: string | null, files: string[]) =>
    ({
      id,
      title: id + " does a thing",
      priority: 1,
      assignee: holder ?? "agent:berna/x",
      holder,
      since: now - 100,
      quiet_for: null,
      files,
      labels: [],
    }) satisfies BoardPayload["groups"]["doing"][number];

  const swarmTeam: TeamMember[] = [
    { actor: "dev:berna", seen: now, ago: 0 },
    { actor: "agent:berna/s1", seen: now, ago: 0 },
  ];
  const swarmDoing = [
    swarmRow("tk-aaa111", "agent:berna/s1", ["ui/src/shared.ts"]),
    swarmRow("tk-bbb222", "agent:berna/s2", ["ui/src/shared.ts", "ui/src/other.ts"]),
  ];
  const swarmReviewing = [
    { ...swarmRow("tk-aaa111", "agent:berna/rv1", ["ui/src/shared.ts"]), review_since: now - 30 },
  ] as unknown as ReviewingRow[];
  const swarmLapsed = [swarmRow("tk-ccc333", null, [])];

  const swarmGraph = topology({ team: swarmTeam, doing: swarmDoing, reviewing: swarmReviewing, stalled: swarmLapsed });
  const swarmEdge = (from: string, to: string, kind: string) =>
    swarmGraph.edges.some((e) => e.from === from && e.to === to && e.kind === kind);

  const swarmCards = new Set(swarmGraph.nodes.filter((n) => n.kind === "card").map((n) => n.id));

  /* The orchestrator's edges go to its AGENTS and to no card — the registry
   * refuses `take` to a `dev:`, so a dev→card edge is a claim the server makes
   * impossible. It is NOT "no edges at all": that was the bug, drawing
   * `s14 — dev:berna — tk-13d115` by letting the lease line cross the centre. */
  check(
    "swarm: the orchestrator is the centre and touches no card",
    swarmGraph.nodes[0]?.id === "dev:berna" &&
      swarmGraph.nodes[0]?.kind === "orchestrator" &&
      !swarmGraph.edges.some((e) => e.from === "dev:berna" && swarmCards.has(e.to)) &&
      !swarmGraph.edges.some((e) => e.to === "dev:berna" && swarmCards.has(e.from)),
  );
  check(
    "swarm: every card edge starts at the agent that holds it, never at a dev",
    swarmGraph.edges
      .filter((e) => e.kind === "lease" || e.kind === "lapsed")
      .every((e) => e.from.startsWith("agent:") && swarmCards.has(e.to)),
  );
  check(
    "swarm: every drawn agent hangs off its dev by an ownership edge",
    swarmGraph.nodes
      .filter((n) => n.kind !== "card" && n.kind !== "orchestrator")
      .every((n) => swarmEdge("dev:berna", n.id, "owns")),
  );
  /* Ownership is a standing fact about a name and not work, so it is drawn
   * apart (`--hair-2`, thinner) and left out of the header count. */
  check(
    "swarm: an ownership edge is not counted as a lease",
    swarmGraph.leases === swarmGraph.edges.filter((e) => e.kind === "lease").length &&
      swarmGraph.edges.some((e) => e.kind === "owns"),
  );
  /* An agent whose dev is not on `team` still draws; the far end is simply not
   * there. An orchestrator is never invented for an absent dev. */
  const swarmOrphan = topology({
    team: [{ actor: "dev:other", seen: now, ago: 0 }],
    doing: [swarmRow("tk-ddd444", "agent:berna/s9", [])],
    reviewing: [],
    stalled: [],
  });
  check(
    "swarm: an agent whose dev is absent draws itself and no ownership edge",
    swarmOrphan.nodes.some((n) => n.id === "agent:berna/s9") &&
      !swarmOrphan.nodes.some((n) => n.id === "dev:berna") &&
      !swarmOrphan.edges.some((e) => e.kind === "owns"),
  );
  check("swarm: a live lease is an edge from its worker", swarmEdge("agent:berna/s1", "tk-aaa111", "lease"));
  check(
    "swarm: a card under review has TWO edges, and the verifier is its own kind",
    swarmEdge("agent:berna/rv1", "tk-aaa111", "lease") &&
      swarmGraph.edges.filter((e) => e.to === "tk-aaa111" && e.kind === "lease").length === 2 &&
      swarmGraph.nodes.find((n) => n.id === "agent:berna/rv1")?.kind === "verifier" &&
      swarmGraph.nodes.find((n) => n.id === "agent:berna/s1")?.kind === "worker" &&
      /* three true edges around one card: two leases, and each agent's own
       * ownership edge back to the dev */
      swarmEdge("dev:berna", "agent:berna/s1", "owns") &&
      swarmEdge("dev:berna", "agent:berna/rv1", "owns"),
  );
  check(
    "swarm: a stalled card draws its lapsed owner",
    swarmGraph.nodes.find((n) => n.id === "agent:berna/x")?.kind === "lapsed" &&
      swarmEdge("agent:berna/x", "tk-ccc333", "lapsed"),
  );
  check(
    "swarm: two cards on one declared path are one dashed edge, counted once",
    swarmGraph.contested === 1 && swarmEdge("tk-aaa111", "tk-bbb222", "contested"),
  );
  check("swarm: a card nobody declared a shared file with has no dashed edge",
    !swarmGraph.edges.some((e) => e.kind === "contested" && (e.from === "tk-ccc333" || e.to === "tk-ccc333")));

  /* Criterion 5, and the reason `Math.random()` is banned in that file: the same
   * payload twice is the same markup, byte for byte. */
  const drawSwarm = () =>
    renderToStaticMarkup(
      <Swarm team={swarmTeam} doing={swarmDoing} reviewing={swarmReviewing} stalled={swarmLapsed} />,
    );
  const swarmFirst = drawSwarm();
  check("swarm: the same payload renders identically twice", swarmFirst === drawSwarm());
  check(
    "swarm: the header counts nodes, live leases and contested edges",
    swarmFirst.includes(`${swarmGraph.nodes.length} nodes · ${swarmGraph.leases} live leases · 1 contested edge`),
  );
  const swarmDrawn = (swarmFirst.match(/data-testid="swarm-node"/g) ?? []).length;
  check(
    "swarm: every node carries an accessible <title>",
    swarmDrawn === swarmGraph.nodes.length && (swarmFirst.match(/<title>/g) ?? []).length === swarmDrawn,
  );
  check("swarm: the dashed edge is drawn dashed", swarmFirst.includes('stroke-dasharray="5 4"'));
  /* Criterion 2: the two kinds are two different claims, so they may not be one
   * line. An ownership edge is `--hair-2` and thinner than any lease. */
  check(
    "swarm: an ownership edge is drawn quieter than a lease",
    swarmFirst.includes('data-kind="owns"') &&
      swarmFirst.includes('stroke="var(--hair-2)"') &&
      /* the mock's own numbers: a lease is 1.6 solid, ownership 1 and dashed 3 4 */
      /data-kind="owns"[^>]*stroke-width="1"[^>]*stroke-dasharray="3 4"/.test(swarmFirst) &&
      !/data-kind="lease"[^>]*stroke="var\(--hair-2\)"/.test(swarmFirst),
  );
  /* Criterion 1 and 3: the mockup's SVG is the specification, so its numbers are
   * asserted as numbers. The pane used to draw r=16 discs on a 460×330 board and
   * read as a bubble chart; nothing about the DATA changed to fix that. */
  check(
    "swarm: the svg is the mockup's viewBox, height and guide rings",
    swarmFirst.includes('viewBox="0 0 600 400"') &&
      swarmFirst.includes('height="440"') &&
      swarmFirst.includes('cx="300" cy="200" r="100"') &&
      swarmFirst.includes('cx="300" cy="200" r="130"') &&
      /* the grid is a 28px CSS background on the wrapper, not an SVG pattern */
      swarmFirst.includes("background-size:28px 28px") &&
      !swarmFirst.includes("<pattern"),
  );
  check(
    "swarm: a node is r=26 with a halo ring at r=34, opacity 0.22",
    /r="26" fill="var\(--pane\)" stroke="[^"]+" stroke-width="1.6"/.test(swarmFirst) &&
      /r="34" fill="none" stroke="[^"]+" stroke-width="1" opacity="0.22"/.test(swarmFirst),
  );
  /* Criterion 2: TWO texts per node — that is what makes it read as a diagram
   * rather than a bubble chart. */
  check(
    "swarm: a node carries its glyphs inside and its sub-label at dy=46",
    /dominant-baseline="central" font-size="12" font-weight="500"/.test(swarmFirst) &&
      /dy="46"[^>]*font-size="9.5"/.test(swarmFirst) &&
      swarmFirst.includes(">tk-aaa111<") &&
      swarmFirst.includes(">orchestrator<") &&
      /* the glyphs are `initials()` for an actor and the id without its `tk-`
       * for a card — three at most, because `w1` and `w10` exist */
      swarmFirst.includes(">ber<") &&
      swarmFirst.includes(">s1<") &&
      swarmFirst.includes(">aaa<") &&
      !swarmFirst.includes(">agent:berna/s1<"),
  );
  /* The ring is the mock's OUTER guide circle, centred where the mock centres
   * it: the coordinates in its SVG are 300+130·cosθ, 200+130·sinθ. */
  check(
    "swarm: every ring node sits on r=130 around the mockup's centre",
    swarmGraph.nodes
      .filter((n) => n.id !== "dev:berna")
      .every((n) => Math.abs(Math.hypot(n.x - 300, n.y - 200) - 130) < 0.05) &&
      swarmGraph.nodes[0]?.x === 300 &&
      swarmGraph.nodes[0]?.y === 200,
  );
  check(
    "swarm: every edge is the mockup's weight and opacity",
    /data-kind="lease"[^>]*stroke-width="1.6"[^>]*opacity="0.55"/.test(swarmFirst) &&
      /data-kind="contested"[^>]*stroke-width="1.6"[^>]*stroke-dasharray="5 4"[^>]*opacity="0.55"/.test(swarmFirst),
  );
  check(
    "swarm: the caveat is on the pane, in the Edit surface's own words",
    swarmFirst.includes("a warning, never a lock") &&
      swarmFirst.includes("never what a worker actually edited"),
  );

  /* Nothing running is the COMMON state, not an edge case: one sentence and no
   * graph — never an empty ring pretending to be a topology. */
  const swarmQuiet = renderToStaticMarkup(
    <Swarm team={swarmTeam} doing={[]} reviewing={[]} stalled={[]} />,
  );
  check(
    "swarm: nothing running is one sentence and no graph",
    swarmQuiet.includes('data-testid="pane-empty"') &&
      !swarmQuiet.includes('data-testid="swarm-graph"') &&
      !swarmQuiet.includes('data-testid="swarm-count"'),
  );

  /* ── 9. The thread draws the prose an agent closed with ────────────────────
   *
   * The complaint was "the agents never leave comments when they close a card".
   * They do — measured on this repo's own log, 61 of 61 `status done` events
   * carry a `reason` — and `mcp/thread.py::detail` prints it. The DASHBOARD
   * dropped it, for two independent reasons: `detail()` tried `to` before it
   * would ever have reached `reason` (which was not in its list at all), so a
   * close resolved to the bare word "done"; and the render drew a text block
   * only for `kind === "comment"`, so even the right string had nowhere to go.
   *
   * Everything below comes from the board's OWN event bodies — `tests/test_ui.py`
   * closes two real cards through the verbs — because a hand-written history is
   * exactly what would have kept this bug green. */

  const [reviewed, noCode] = fixture.closed;
  if (reviewed === undefined || noCode === undefined) {
    check("the fixture carries two closed cards", false, "fixture.closed is short");
  } else {
    const closedThread = renderToStaticMarkup(<Thread history={reviewed.history} now={now} />);
    const at = (h: Event[], kind: string): Event | undefined => h.find((e) => e.kind === kind);

    // Criterion 1. The transition is still there — a reader must see at a glance
    // that this was a close and not a remark — and the note is there WITH it.
    check(
      "a close draws its transition AND the note the worker signed off with",
      closedThread.includes('data-testid="event-detail"') &&
        closedThread.includes('data-testid="event-prose"') &&
        closedThread.includes("closed after the pass — Decimal all the way") &&
        closedThread.includes(">done<"),
    );
    // …and the prose is what the log actually holds, not a string this file made up.
    check(
      "the note on screen is the one the server wrote into status.reason",
      at(reviewed.history, "status")?.body["reason"] ===
        "closed after the pass — Decimal all the way",
    );

    // Criterion 2. `submitted` and `reviewed` carry `body.note`; the verdict
    // rides beside its note rather than replacing it.
    check(
      "handing in draws its note",
      closedThread.includes("parsed with Decimal throughout") &&
        at(reviewed.history, "submitted")?.body["note"] === "parsed with Decimal throughout",
    );
    check(
      "a verdict draws BOTH its word and what the verifier wrote",
      closedThread.includes(">pass<") &&
        closedThread.includes("read every row, the rounding holds"),
    );
    // The card the rest of this file uses was RELEASED, so its note is the third
    // case and it is on the screen the drawer draws.
    check(
      "a release draws its note",
      renderToStaticMarkup(<Thread history={fixture.card.history} now={now} />).includes(
        "got to the rounding",
      ),
    );

    // Criterion 3. `no_code` means no commit was ever bound to the card. The
    // Python renderer prints `(no code)`; so does this one now.
    const noCodeThread = renderToStaticMarkup(<Thread history={noCode.history} now={now} />);
    check(
      "a close with no commit says so, in the Python renderer's own words",
      noCodeThread.includes("done (no code)") &&
        noCodeThread.includes("the README already said it, so there was nothing to write") &&
        at(noCode.history, "status")?.body["no_code"] === true,
    );

    // Criterion 4. The two renderers agree. `oneLine` is the join Python uses
    // (`: done — <reason>`), and it is what the Event stream — one line per row
    // — draws, so a close is not a bare word there either.
    const status = at(reviewed.history, "status");
    check(
      "phrase and prose join the way mcp/thread.py::detail joins them",
      status !== undefined &&
        oneLine(status) === "done — closed after the pass — Decimal all the way" &&
        oneLine(noCode.history.filter((e) => e.kind === "status")[0] as Event) ===
          "done (no code) — the README already said it, so there was nothing to write",
    );
    check(
      "the Event stream row carries the prose too, not just the transition",
      renderToStaticMarkup(
        <EventStream
          events={reviewed.history}
          total={reviewed.history.length}
          now={now}
          more={false}
          loading={false}
          onMore={() => {}}
        />,
      ).includes("done — closed after the pass"),
    );
    // The split itself: a phrase is never prose and prose is never a phrase, so
    // nothing is drawn twice. `released` is the one that used to arrive through
    // the fallback loop as a phrase.
    const released = at(fixture.card.history, "released");
    check(
      "no event draws its writing twice",
      released !== undefined &&
        detail(released) === "" &&
        prose(released) === "got to the rounding — see `src/tax.py::half_up`" &&
        // A commit's subject is a phrase, not prose — it stays on the one line
        // it was always on, exactly as `mcp/thread.py::detail` treats it.
        prose(at(reviewed.history, "commit") as Event) === "" &&
        detail(at(reviewed.history, "commit") as Event) === "feat: csv",
    );
    // And the whole of it reaches the DOSSIER, which is the screen the reader
    // complained about — not just the component in isolation.
    check(
      "the closing note is on the dossier a reader actually opens",
      renderToStaticMarkup(
        <Dossier
          dossier={reviewed}
          openId={reviewed.card.id}
          team={fixture.board.team}
          now={now}
          onClose={() => {}}
          onComment={async () => {}}
        />,
      ).includes("closed after the pass — Decimal all the way"),
    );
  }
  /* ── 10. Actors: a page about DEVS, and an agent is a LINE inside one ────
   *
   * The rows are built here for the reason §9 builds its own: this repo's board
   * cannot be made to hold a work lease, a review lease, a lapsed assignment and
   * a fortnight of hours at one instant from a test. The SHAPES are the
   * payload's (`BoardRow`, `TeamMember`, `ReportPayload` — the compiler checks
   * it), and `devRows()` is exported pure precisely so the folding rule can be
   * asserted without rendering.
   *
   * TWO devs, deliberately. A board with several is the case this shape exists
   * for — it is why the top level is a dev and not "the current user" — and this
   * repo's own board has one, so the two-dev case can only be pinned here. */

  const actorRow = (id: string, holder: string | null, assignee = "") =>
    ({
      id,
      title: id + " does a thing",
      priority: 1,
      assignee,
      holder,
      since: now - 100,
      quiet_for: null,
      files: [],
      labels: [],
    }) satisfies BoardPayload["groups"]["doing"][number];

  const hours = (seconds: number, cards: string[], closed?: number, commits?: number) => ({
    seconds,
    human: `${Math.round(seconds / 3600)}h`,
    cards,
    ...(closed === undefined ? {} : { closed }),
    ...(commits === undefined ? {} : { commits }),
  });

  const actorsProps = {
    team: [
      { actor: "dev:berna", seen: now, ago: 4 },
      { actor: "agent:berna/w1", seen: now, ago: 34 },
      { actor: "agent:berna/rv1", seen: now, ago: 60 },
      { actor: "agent:berna/idle", seen: now, ago: 900 },
      { actor: "dev:ana", seen: now, ago: 120 },
      { actor: "agent:ana/a1", seen: now, ago: 15 },
    ] satisfies TeamMember[],
    doing: [actorRow("tk-a11ffa", "agent:berna/w1"), actorRow("tk-d44444", "agent:ana/a1")],
    reviewing: [
      { ...actorRow("tk-b22eee", "agent:berna/rv1"), review_since: now - 30 },
    ] as unknown as ReviewingRow[],
    stalled: [actorRow("tk-c33ddd", null, "agent:berna/w9")],
    report: {
      from: now - 14 * 86400,
      to: now,
      days: [
        { day: "2026-08-07", by_actor: {}, closed: [], commits: 0 },
        {
          day: "2026-08-08",
          by_actor: {
            "agent:berna/w1": hours(7200, ["tk-a11ffa"], 1, 3),
            "dev:berna": hours(3600, ["tk-a11ffa"], 0, 0),
            // Worth zero today: criterion 9 says it gets no row at all.
            "agent:berna/zzz": hours(0, [], 0, 0),
            "agent:ana/a1": hours(3600, ["tk-d44444"], 1, 2),
          },
          closed: ["tk-a11ffa"],
          commits: 3,
        },
      ],
      by_actor: {
        "dev:berna": hours(3600, ["tk-a11ffa"], 2, 5),
        "agent:berna/w1": hours(7200, ["tk-a11ffa"], 1, 3),
        "agent:berna/rv1": hours(1800, [], 0, 0),
        "agent:berna/idle": hours(600, [], 0, 1),
        "agent:berna/w9": hours(0, [], 0, 0),
        "dev:ana": hours(1800, [], 1, 1),
        "agent:ana/a1": hours(3600, ["tk-d44444"], 1, 2),
      },
      total: { seconds: 10800, closed: 1 },
    },
    now,
    onOpen: (id: string) => opened.push(id),
  };

  const devs = devRows(actorsProps);

  /* Criterion 1 and 8: one card per DEV, none per agent, and two devs are two
   * cards each carrying its own agents. Sixty-seven tiles for sixty-six dead
   * sub-agents is what this replaced. */
  check(
    "actors: two devs are two rows, and every agent is inside one of them",
    devs.map((d) => d.dev).join(" ") === "dev:berna dev:ana" &&
      devs[0]?.agents.map((a) => a.actor).join(" ") ===
        "agent:berna/w1 agent:berna/rv1 agent:berna/w9 agent:berna/idle" &&
      devs[1]?.agents.map((a) => a.actor).join(" ") === "agent:ana/a1",
    devs.map((d) => `${d.dev}:${d.agents.length}`).join(" "),
  );
  /* The agents keep `actorRows()`' rank INSIDE their dev: a live work lease,
   * then a live review lease, then a lapsed assignment, then the rest. */
  check(
    "actors: inside a dev, a live lease outranks an agent holding none",
    devs[0]?.agents.map((a) => a.state ?? "none").join(" ") === "doing reviewing lapsed online",
  );
  /* The roles are still derived from the name and the lease — a verifier holds
   * the SECOND mutex and is not a shade of worker. */
  check(
    "actors: the worker and the verifier are told apart",
    devs[0]?.agents[0]?.role === "worker" && devs[0]?.agents[1]?.role === "verifier",
  );

  /* Criterion 7: who is on a card RIGHT NOW is a fact on the card, not behind a
   * click — it is the question somebody opens this tab to answer. */
  check(
    "actors: a live lease is counted and named without opening anything",
    devs[0]?.live === 2 &&
      devs[0]?.onCards.map((c) => `${c.actor}=${c.id}`).join(" ") ===
        "agent:berna/w1=tk-a11ffa agent:berna/rv1=tk-b22eee",
    JSON.stringify(devs[0]?.onCards),
  );

  /* A dev's figures are the SUM of it and its agents — 2+1, 5+3+1, and every
   * member's seconds — and the wording is `core/hours.py`'s. */
  check(
    "actors: a dev's figures are it and its agents, summed",
    devs[0]?.closed === 3 &&
      devs[0]?.commits === 9 &&
      devs[0]?.seconds === 13200 &&
      devs[0]?.worked === "3h 40m" &&
      devs[0]?.partial === false,
    `${devs[0]?.closed}/${devs[0]?.commits}/${devs[0]?.worked}`,
  );

  /* …and when ONE member cannot say a figure, the sum is REFUSED rather than
   * quietly taken over the rest: the dev's own is drawn and the panel says the
   * agents' are counted separately. `agent:berna/old` is a board one version
   * behind — no `closed`, no `commits` (types.ts: both optional). */
  const partialProps = {
    ...actorsProps,
    report: {
      ...actorsProps.report,
      by_actor: {
        ...actorsProps.report.by_actor,
        "agent:berna/old": hours(1800, ["tk-9f0000", "tk-9f0001"]),
      },
    },
  };
  const partial = devRows(partialProps).find((d) => d.dev === "dev:berna");
  check(
    "actors: a figure one member cannot say refuses the sum, it does not skip it",
    partial?.partial === true &&
      partial?.closed === 2 &&
      partial?.commits === 5 &&
      partial?.worked === "1h",
    `${partial?.closed}/${partial?.commits}/${partial?.worked}`,
  );
  /* That member is still HISTORY and not a free slot: it says what it carried. */
  const oldRow = partial?.agents.find((a) => a.actor === "agent:berna/old");
  check(
    "actors: an agent with no card carries its history, not a slot",
    oldRow?.card === null &&
      oldRow?.carried.join(",") === "tk-9f0000,tk-9f0001" &&
      oldRow?.presence === "not seen in 24h" &&
      oldRow?.closed === null,
  );
  /* `actorRows()` is still the fold underneath, and still per actor. */
  check(
    "actors: every actor the board can name reaches exactly one dev",
    actorRows(actorsProps).length ===
      devRows(actorsProps).reduce((n, d) => n + d.agents.length + (d.self ? 1 : 0), 0),
  );

  const actorsMarkup = renderToStaticMarkup(<Actors {...actorsProps} />);
  check("actors: the view renders", actorsMarkup.includes('data-testid="actors"'));
  check(
    "actors: one card per dev is DRAWN, and no card for an agent",
    (actorsMarkup.match(/data-testid="dev-card"/g) ?? []).length === 2 &&
      !actorsMarkup.includes('data-testid="actor-card"'),
  );
  check(
    "actors: NO WORKER SLOTS, under that name or any other",
    !/free|slot|capacity/i.test(actorsMarkup),
  );
  check(
    "actors: the window qualifier is said once, on the view",
    (actorsMarkup.match(/closed and commits are over the last 2 days/g) ?? []).length === 1,
  );
  check(
    "actors: the live lease is on the card, with a door to the card it holds",
    actorsMarkup.includes("2 agents on a card right now") &&
      actorsMarkup.includes('data-testid="dev-live-card" data-card="tk-a11ffa"'),
  );
  /* THE BAR PANEL IS DELETED, not restyled, and deleted from the PAGE: it
   * existed to compare actors against each other, and an ephemeral agent is a
   * label. Nothing replaces it here — the hours moved into the dev's own panel,
   * grouped by the one axis that is a fact about a person, the calendar day. */
  check(
    "actors: the hours bar panel is gone from the page, under any name",
    !actorsMarkup.includes('data-testid="pane-hours-today"') &&
      !actorsMarkup.includes('data-testid="hours-bar"') &&
      !actorsMarkup.includes("Hours worked today") &&
      !actorsMarkup.includes("agent:berna/zzz"),
  );

  /* Criterion 6: MORE AGENTS THAN THE CAP is said, never truncated in silence —
   * on the card (the recent few) and in the detail (the rows). */
  const many = Array.from({ length: 30 }, (_, i) => `agent:berna/n${i}`);
  const capProps = {
    ...actorsProps,
    team: many.map((actor, i) => ({ actor, seen: now, ago: i })) satisfies TeamMember[],
    doing: [],
    reviewing: [] as unknown as ReviewingRow[],
    stalled: [],
    report: {
      ...actorsProps.report,
      by_actor: Object.fromEntries(many.map((a) => [a, hours(600, [], 0, 0)])),
    },
  };
  const capped = devRows(capProps)[0]!;
  const capMarkup = renderToStaticMarkup(<Actors {...capProps} />);
  check(
    "actors: a dev with thirty agents draws a few names and counts the rest",
    capped.agents.length === 30 &&
      capMarkup.includes(`+${30 - RECENT} more`) &&
      (capMarkup.match(/agent:berna\/n\d+/g) ?? []).length === 0,
    capMarkup.split('data-testid="dev-recent"')[1]?.slice(0, 120),
  );
  /* Criterion 5: a board nobody has touched is ONE sentence, not an empty grid. */
  const actorsEmpty = renderToStaticMarkup(
    <Actors team={[]} doing={[]} reviewing={[]} stalled={[]} report={null} now={now} onOpen={() => {}} />,
  );
  check(
    "actors: nobody seen is one sentence",
    actorsEmpty.includes('data-testid="actors-none"') &&
      !actorsEmpty.includes('data-testid="dev-card"'),
  );

  /* The fourth tab exists AND has a page. A tab that falls through to the Board
   * is a dead tab that still looks alive; `App`'s page map is a
   * `Record<TabId, …>`, so this list and that map cannot disagree. */
  check(
    "actors: the tab bar is Nova's four, in Nova's order",
    TABS.map((t) => t.id).join(" ") === "monitor board actors worktrees",
  );

  /* ── 11. The detail: an overlay, and a pane per DATE with an hour inside ──
   *
   * This section pinned a DRAWING — lanes per agent on a shared axis — and a
   * panel of bars beside it. Both are deleted, and this is the redesign that
   * replaced them: the window grouped by calendar day, newest FIRST and only the
   * newest open, each day's hours a row, each row folding open to its sessions.
   * A sub-agent adds nothing here; it is at most the name on a session.
   *
   * The folds are clicks and no handler fires under `react-dom/server`, so the
   * same two seams the rest of this dashboard uses carry the assertions:
   * `daysheet()` is exported PURE (everything that decides what the click lands
   * on), and `HourRow` takes `open` as a PROP, so an hour folded open is a tree
   * this harness can render — exactly as `Dossier` is exported beside `Drawer`.
   *
   * The fixture is built from a LOCAL midnight, not a fixed epoch: an hour is
   * the reader's own hour (`Date#getHours`), and a UTC constant would bucket
   * differently in every timezone this suite runs in.
   */

  const DAYSHEET_DAY = "2026-08-08";
  const midnight = new Date(2026, 7, 8).getTime() / 1000;
  const at = (h: number, m: number) => midnight + h * 3600 + m * 60;
  const run = (
    fromH: number,
    fromM: number,
    toH: number,
    toM: number,
    task: string,
  ): ActorSession => ({
    start: at(fromH, fromM),
    end: at(toH, toM),
    task,
    seconds: at(toH, toM) - at(fromH, fromM),
  });
  const sheetHours = (blocks: ActorSession[], total = blocks.length) => ({
    seconds: blocks.reduce((n, b) => n + b.seconds, 0),
    human: "ignored — a merged day's total is this screen's own sum",
    cards: [...new Set(blocks.map((b) => b.task))],
    sessions: blocks,
    sessions_total: total,
  });

  /* 10:38–11:12 is the session that CROSSES an hour boundary; 11:00 is then an
   * hour inside the day's span with nothing counted, and 12:20 belongs to an
   * AGENT — both are merged onto one list with no row of their own. */
  const sheetReport = {
    from: midnight - 86400,
    to: midnight + 86400,
    days: [
      {
        day: "2026-08-06",
        by_actor: { "dev:berna": { seconds: 60, human: "1m", cards: [] } },
        closed: [],
        commits: 0,
      },
      {
        day: "2026-08-07",
        by_actor: {
          "dev:berna": sheetHours([
            { ...run(15, 0, 15, 30, "tk-a11ffa"), start: at(15, 0) - 86400, end: at(15, 30) - 86400 },
          ]),
        },
        closed: [],
        commits: 0,
      },
      {
        day: DAYSHEET_DAY,
        by_actor: {
          "dev:berna": sheetHours([
            run(9, 0, 9, 58, "tk-e5a340"),
            run(10, 4, 10, 31, "tk-c4445b"),
            run(10, 38, 11, 12, "tk-c4445b"),
          ]),
          "agent:berna/w1": sheetHours([run(12, 20, 12, 40, "tk-d34294")], 4),
        },
        closed: [],
        commits: 0,
      },
    ],
    by_actor: {},
    total: { seconds: 0, closed: 0 },
  } satisfies ReportPayload;

  const sheetTitles = { "tk-c4445b": "the index: two columns" };
  const sheet = daysheet(
    sheetReport,
    ["dev:berna", "agent:berna/w1", "agent:berna/never"],
    sheetTitles,
  );

  /* Criterion 1: one pane per calendar day, NEWEST FIRST — the panel this
   * replaced drew the 7th above the 8th — and a day with no counted session at
   * all (the 6th sends no `sessions` key) is not a pane. */
  check(
    "daysheet: one pane per date, newest first, and no pane for a day with nothing",
    sheet.map((d) => d.day).join(" ") === "2026-08-08 2026-08-07",
    JSON.stringify(sheet.map((d) => d.day)),
  );
  check(
    "daysheet: a pane is headed by its weekday and date, not by an ISO string",
    sheet[0]?.label === "Saturday 8 August" && dayLabel("2026-08-07") === "Friday 7 August",
    `${sheet[0]?.label}`,
  );

  /* Criterion 2: the hours the day SPANS — first session's hour to the last's —
   * so the shape of the day is visible, and never 00–23. */
  const dayOne = sheet[0]!;
  check(
    "daysheet: the rows are the hours the day spans, not a full clock",
    dayOne.hours.map((h) => h.label).join(" ") === "09:00 10:00 11:00 12:00",
    JSON.stringify(dayOne.hours.map((h) => h.label)),
  );
  /* …and the hour with nothing in it is PRESENT. It is where the dropped gap
   * is, and the reason the day's total is smaller than last minus first. */
  check(
    "daysheet: an hour inside the span with nothing counted is a row, not a hole",
    dayOne.hours[2]?.label === "11:00" && dayOne.hours[2]?.sessions.length === 0,
  );

  /* Criterion 4: 10:38–11:12 belongs to the hour of its START and is ONE
   * session. Split, it would put 22m in 10:00 and 12m in 11:00 — two intervals
   * `core/hours.py` never produced, and 11:00 would stop being empty. */
  check(
    "daysheet: a session across an hour boundary stays whole, in the hour it started",
    dayOne.hours[1]?.sessions.length === 2 &&
      dayOne.hours[1]?.sessions[1]?.seconds === 34 * 60 &&
      dayOne.hours[1]?.seconds === 61 * 60 &&
      dayOne.hours[2]?.seconds === 0,
    JSON.stringify(dayOne.hours.map((h) => h.seconds / 60)),
  );
  check(
    "daysheet: the day's total is the sum of its hours, and the gaps are measured",
    dayOne.seconds === 139 * 60 &&
      dayOne.seconds === dayOne.hours.reduce((n, h) => n + h.seconds, 0) &&
      dayOne.gaps === 3 &&
      span(dayOne.dropped) === "1h 21m",
    `${dayOne.seconds / 60} ${dayOne.gaps} ${span(dayOne.dropped)}`,
  );
  /* The dev's sessions and its agents' are ONE list. The agent is not a lane,
   * not a row and not a heading — it is the name on a session. */
  check(
    "daysheet: the dev and its agents merge onto one list of sessions",
    dayOne.hours[3]?.sessions[0]?.actor === "agent:berna/w1" &&
      dayOne.hours[0]?.sessions[0]?.actor === "dev:berna",
  );
  check(
    "daysheet: a truncated answer says so rather than shrinking the day",
    dayOne.capped === true && sheet[1]?.capped === false,
  );
  /* A board one version behind sends no `sessions` at all — degraded, never
   * crashed (types.ts: both keys optional). */
  check(
    "daysheet: a payload without sessions degrades to no pane at all",
    daysheet(sheetReport, ["agent:berna/never"]).length === 0 &&
      daysheet(null, ["dev:berna"]).length === 0,
  );

  const opened2: string[] = [];
  const sheetMarkup = renderToStaticMarkup(
    <Daysheet days={sheet} onOpen={(id) => opened2.push(id)} />,
  );
  /* Criterion 1, drawn: the NEWEST pane is the open one and the rest are shut —
   * real buttons carrying `aria-expanded`, never a bare arrow glyph. */
  check(
    "daysheet: the newest pane is open and the older one is closed",
    (sheetMarkup.match(/data-testid="day-fold" aria-expanded="(true|false)"/g) ?? []).join(" ") ===
      'data-testid="day-fold" aria-expanded="true" data-testid="day-fold" aria-expanded="false"' &&
      sheetMarkup.includes(">Saturday 8 August<"),
    sheetMarkup.match(/aria-expanded="(true|false)"/g)?.join(" "),
  );
  /* Criterion 2, drawn: the empty hour SAYS so, and carries no fold — there is
   * nothing behind it, and an arrow that opens nothing is not a control. */
  check(
    "daysheet: the empty hour says nothing counted and is not a fold",
    sheetMarkup.includes('data-testid="hour-row" data-hour="11:00" data-empty="yes"') &&
      sheetMarkup.includes(">nothing counted<") &&
      (sheetMarkup.match(/data-testid="hour-fold"/g) ?? []).length === 3,
    sheetMarkup.match(/data-hour="[^"]+" data-empty="[^"]+"/g)?.join(" "),
  );
  check(
    "daysheet: an hour row carries its counted time and the cards touched",
    sheetMarkup.includes(">tk-c4445b<") && sheetMarkup.includes(">1h 1m<") &&
      sheetMarkup.includes(">58m<"),
  );
  /* An hour of the CLOSED pane is not drawn at all. */
  check(
    "daysheet: a closed date pane draws none of its hours",
    (sheetMarkup.match(/data-testid="hour-row"/g) ?? []).length === 4,
  );
  /* Criterion 3: folded open, the hour lists its sessions — start, end,
   * duration, card and title. `HourRow` takes `open` as a prop precisely so this
   * is reachable with no click. */
  const hourMarkup = renderToStaticMarkup(
    <HourRow hour={dayOne.hours[1]!} open onFold={() => {}} onOpen={(id) => opened2.push(id)} />,
  );
  check(
    "daysheet: an open hour lists its sessions with start, end, duration and card",
    (hourMarkup.match(/data-testid="session-row"/g) ?? []).length === 2 &&
      hourMarkup.includes("10:04 – 10:31") &&
      hourMarkup.includes(">27m<") &&
      hourMarkup.includes(">tk-c4445b</span>") &&
      hourMarkup.includes("the index: two columns"),
    hourMarkup.slice(0, 240),
  );
  /* Criterion 6: a session is a door to its CARD's dossier — the same `openCard`
   * every other view uses — and it is a real button. */
  check(
    "daysheet: a session opens the dossier of the card it was credited to",
    /<button[^>]*data-testid="session-row" data-card="tk-c4445b"/.test(hourMarkup),
  );
  /* A card the board cannot name right now is drawn as its ID ALONE, never with
   * a title nothing sent. */
  check(
    "daysheet: a session on a card nobody holds is its id and no invented title",
    renderToStaticMarkup(
      <HourRow hour={dayOne.hours[0]!} open onFold={() => {}} onOpen={() => {}} />,
    ).includes(">tk-e5a340</span></span>"),
  );
  /* The gaps are said as a figure, and the rule is on screen in
   * `core/hours.py`'s own words. */
  check(
    "daysheet: the dropped time is a figure and the arithmetic is beside it",
    sheetMarkup.includes("3 gaps · 1h 21m not counted") &&
      sheetMarkup.includes('data-testid="daysheet-rule"') &&
      sheetMarkup.includes("credited to the card that CLOSES it") &&
      RULE.includes("dropped whole, never capped"),
  );
  /* Nothing counted in the window is a SENTENCE, never an empty pane. */
  check(
    "daysheet: an actor with no counted time says so instead of drawing a pane",
    renderToStaticMarkup(<Daysheet days={[]} onOpen={() => {}} />).includes(
      'data-testid="daysheet-none"',
    ),
  );
  /* THE DELETED DESIGN, absent from the tree it was drawn in: no lane, no axis,
   * no per-agent row anywhere in this panel. */
  check(
    "daysheet: the lane-per-agent drawing is gone, not hidden",
    !sheetMarkup.includes("timesheet") && !sheetMarkup.includes("lane"),
  );

  /* Criterion 5 of the previous card, kept: the detail is a FULL OVERLAY reusing
   * the existing machinery. `DevPanel` is `shared/Overlay` — a portal — so it
   * renders nothing at all here, exactly as `Drawer` does; `DevDetail` beside it
   * is the document, and it is what the harness reads. */
  const sheetDev = devRows({ ...actorsProps, report: sheetReport })[0]!;
  check(
    "actors: the dev detail is the shared portal overlay, not a second one",
    renderToStaticMarkup(
      <DevPanel row={sheetDev} report={sheetReport} onOpen={() => {}} onClose={() => {}} />,
    ) === "" && !actorsMarkup.includes('data-testid="dev-figures"'),
  );
  const detailMarkup = renderToStaticMarkup(
    <DevDetail
      row={sheetDev}
      report={sheetReport}
      titles={sheetTitles}
      onOpen={() => {}}
      onClose={() => {}}
    />,
  );
  check(
    "actors: the detail is the figures and the date panes, and NOTHING per agent",
    detailMarkup.includes('data-testid="dev-figures"') &&
      detailMarkup.includes('data-testid="day-pane" data-day="2026-08-08"') &&
      !detailMarkup.includes('data-testid="dev-agent"') &&
      !detailMarkup.includes('data-testid="dev-card"') &&
      !detailMarkup.includes("timesheet"),
  );
  /* `cards` is a UNION and not a sum, so it survives a member that cannot say
   * its `closed`/`commits` — which is the case that refuses every other total. */
  check(
    "actors: the rail counts the distinct cards carried, and says who is running now",
    devCards(devs[0]!) === 1 &&
      detailMarkup.includes("2 running now") &&
      cardTitles(actorsProps)["tk-a11ffa"] === "tk-a11ffa does a thing",
    `${devCards(devs[0]!)}`,
  );
  const partialDetail = renderToStaticMarkup(
    <DevDetail row={partial!} report={actorsProps.report} onOpen={() => {}} onClose={() => {}} />,
  );
  check(
    "actors: a refused sum is said in words, and a real sum says it is one",
    partialDetail.includes('data-testid="dev-partial"') &&
      renderToStaticMarkup(
        <DevDetail row={devs[0]!} report={actorsProps.report} onOpen={() => {}} onClose={() => {}} />,
      ).includes('data-testid="dev-sum"'),
  );

  return failures;
}

/** `localStorage`, in four lines. `client.ts` takes its storage as a parameter
 *  precisely so this is all it costs (v1 faked three globals to import its api). */
function fakeStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: () => null,
    get length() {
      return map.size;
    },
  } as Storage;
}
