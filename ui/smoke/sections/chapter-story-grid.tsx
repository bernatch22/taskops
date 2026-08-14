/* Pins the landed chapter's GRID — `components/story/ChapterStory.tsx` and the
 * pure folds under it (`components/story/stats.ts`), plus App's swap decision
 * (`App.tsx::boardView`). The fixture ActivityPayload is built BY HAND on
 * purpose, like chapter-completion-derivation's boards: this section needs the
 * exact boundary cases — the summary fallback chain, a null-numstat binary, a
 * dropped card — under its own control, and the live fixture's chapter is not
 * finished. */
import { renderToStaticMarkup } from "react-dom/server";

import { boardView } from "../../src/App";
import { ChapterStory } from "../../src/components/story/ChapterStory";
import { chapterStats, diffOf, landingOrder, summaryOf } from "../../src/components/story/stats";
import { Board } from "../../src/pages/Board";
import type { ActivityPayload, CardStory, Milestone, Pulse, Standing } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

const NOW = 1_755_000_000;

const STONE: Milestone = {
  id: "ms-story",
  title: "A finished chapter",
  goal: "reads as a story, with `activity` on the wire",
  rules: [],
  criteria: ["the grid replaces the columns"],
  branch: "ms/story",
  status: "landed",
  created: NOW - 86_400,
};

const PULSE: Pulse = {
  milestone: STONE.title,
  goal: STONE.goal,
  counts: { doing: 0, ready: 0, blocked: 0, stalled: 0, done: 3 },
  mentions: 0,
};

function story(id: string, over: Partial<CardStory>): CardStory {
  return {
    id,
    title: `Card ${id}`,
    priority: 2,
    assignee: "agent:berna/w1",
    holder: null,
    since: NOW,
    quiet_for: 60,
    labels: [],
    state: "done",
    status: "done",
    after: [],
    parent: null,
    review: false,
    branch: id,
    merged_into: "ms/story",
    commits: [],
    commits_total: 0,
    standing: null,
    resume: "",
    seconds: 0,
    thread: [],
    thread_total: 0,
    ...over,
  };
}

const STANDING: Standing = {
  submitted_at: NOW,
  submitted_by: "agent:berna/w1",
  verdict: "pass",
  note: "verdict line wins\nsecond line never drawn",
  reviewed_by: "agent:berna/w2",
  reviewed_at: NOW,
};

/* Three done + one dropped. `since` deliberately out of id order so the sort is
 * the thing under test, not the fixture's accident. */
const CARDS: CardStory[] = [
  story("tk-second", {
    since: NOW - 2000,
    resume: "released note wins over the commit\nnot this line",
    commits: [{ sha: "b".repeat(40), subject: "older", numstat: { "b.ts": [5, 1] } }],
    commits_total: 1,
    seconds: 600,
  }),
  story("tk-first", {
    since: NOW - 3000,
    standing: STANDING,
    // a binary beside counted files: null is "git printed -", counted as 0
    commits: [
      { sha: "a".repeat(40), subject: "seams", numstat: { "a.ts": [100, 20], "logo.png": null } },
    ],
    commits_total: 2,
    seconds: 3600,
  }),
  story("tk-third", {
    since: NOW - 1000,
    // no standing, no resume → the LAST commit's subject (commits newest last)
    commits: [
      { sha: "c".repeat(40), subject: "first try", numstat: { "c.ts": [1, 1] } },
      { sha: "d".repeat(40), subject: "commit subject is the fallback", numstat: { "a.ts": [3, 0] } },
    ],
    commits_total: 2,
    seconds: 120,
  }),
  story("tk-gone", {
    since: NOW - 500,
    state: "dropped",
    status: "dropped",
    resume: "not worth doing",
    seconds: 60,
  }),
];

const STORY: ActivityPayload = {
  milestone: STONE,
  reports: [],
  reports_total: 0,
  depth: "headline",
  since: 0,
  seq: 9,
  cards: CARDS,
  cards_total: CARDS.length,
  pulse: PULSE,
};

export async function run(fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* ── the pure folds ────────────────────────────────────────────────── */

  const order = landingOrder(CARDS).map((c) => c.id);
  check(
    "cards sort ascending by since — landing order",
    order.join(",") === "tk-first,tk-second,tk-third,tk-gone",
    order.join(","),
  );

  check("summary: a verdict's note wins, first line only", summaryOf(CARDS[1]!) === "verdict line wins");
  check("summary: resume next, first line only", summaryOf(CARDS[0]!) === "released note wins over the commit");
  check("summary: last commit's subject last", summaryOf(CARDS[2]!) === "commit subject is the fallback");
  check("summary: nothing to say draws nothing", summaryOf(story("tk-mute", {})) === "");

  const diff = diffOf(CARDS[1]!);
  check(
    "a null numstat entry is a binary, counted as 0",
    diff.added === 100 && diff.deleted === 20 && diff.binary,
    JSON.stringify(diff),
  );

  const stats = chapterStats(CARDS);
  check(
    "stats fold: cards, commits, files, lines, worked, span",
    stats.done === 3 &&
      stats.dropped === 1 &&
      stats.commits === 5 &&
      // a.ts, b.ts, c.ts, logo.png — a.ts touched by two cards counts ONCE
      stats.files === 4 &&
      stats.added === 109 &&
      stats.deleted === 22 &&
      stats.seconds === 4380 &&
      stats.to - stats.from === 2500,
    JSON.stringify(stats),
  );

  /* ── the view ──────────────────────────────────────────────────────── */

  const opened: string[] = [];
  const markup = renderToStaticMarkup(<ChapterStory story={STORY} openCard={(id) => opened.push(id)} />);

  check("the chapter renders", markup.includes('data-testid="chapter-story"'));
  check(
    "the cards sit in a responsive grid that collapses to one column",
    markup.includes('data-testid="story-grid"') &&
      markup.includes("grid-template-columns:repeat(auto-fill, minmax(300px, 1fr))"),
  );
  check("the completion mark is folded into the stats strip", markup.includes("chapter landed"));
  check(
    "the strip carries the aggregate numbers",
    markup.includes('data-testid="story-stats"') && markup.includes("+109") && markup.includes("−22"),
  );
  /* The header is the strip and NOTHING else. The milestone's goal prose, its
   * criteria and a large title all live elsewhere (the picker names the
   * chapter; monitor/Chapter.tsx owns the goal) and repeating them here pushed
   * the cards below the fold. Pinned as an ABSENCE, because a deletion that
   * only presence-checks the survivors comes back the first time somebody
   * "restores the header". */
  check("the milestone goal prose is gone from the story view", !markup.includes("reads as a story"));
  check("the criteria list is gone from the story view", !markup.includes("the grid replaces the columns"));
  check("the large milestone title is gone from the story view", !markup.includes("A finished chapter"));
  /* the grid reads left to right, top to bottom, so DOM order IS landing
   * order — the one thing the two-dimensional layout cannot say on its own,
   * which is why each tile also carries its ordinal. */
  const tiles = [...markup.matchAll(/data-card="(tk-[a-z]+)"/g)].map((m) => m[1]);
  check(
    "the tiles appear in landing order, one per card",
    tiles.join(",") === "tk-first,tk-second,tk-third,tk-gone",
    tiles.join(","),
  );
  const ordinals = [...markup.matchAll(/data-testid="ordinal"[^>]*>(\d+)</g)].map((m) => m[1]);
  check(
    "each tile carries its landing ordinal, 1..n in order",
    ordinals.join(",") === "1,2,3,4",
    ordinals.join(","),
  );

  /* The WHOLE tile is the interactive element — the complaint that produced
   * this redesign was a click target the size of a title. Under SSR the
   * handler cannot fire, so the wiring is pinned where it is decidable: the
   * component took `openCard`, and the element carrying each card's id is
   * itself the <button>, which is therefore both mouse- and keyboard-
   * activatable (a button is in the tab order and fires on Enter/Space). */
  const buttons = [...markup.matchAll(/<button[^>]*data-testid="story-tile"[^>]*data-card="(tk-[a-z]+)"/g)];
  check(
    "every tile IS the button — the whole tile opens the drawer, not a title link",
    buttons.length === 4 && buttons.map((m) => m[1]).join(",") === tiles.join(","),
    `${buttons.length}`,
  );
  check("no tile fired during a static render", opened.length === 0);

  /* The order connector: one arrow per tile in the gutter to its right, on
   * every tile EXCEPT the chapter's last — four cards, three arrows — so the
   * ordinals read as a sequence and not just as numbers. */
  const arrows = (markup.match(/data-testid="story-arrow"/g) ?? []).length;
  check("an order arrow follows every tile but the chapter's last", arrows === CARDS.length - 1, `${arrows}`);
  check(
    "the last tile carries no arrow — the flow ends there",
    markup.lastIndexOf('data-testid="story-arrow"') < markup.lastIndexOf('data-card="tk-gone"'),
  );

  check(
    "the dropped card is muted and marked, not omitted",
    markup.includes('data-card="tk-gone"') &&
      markup.includes('data-dropped="true"') &&
      markup.includes('data-testid="dropped-chip"'),
  );
  check("the binary shows its chip", markup.includes('data-testid="bin-chip"'));
  check("worked time and commit count are chips", markup.includes("60m worked") && markup.includes("2 commits"));
  check(
    "the diff numbers are drawn per tile, three of the four cards having one",
    (markup.match(/data-testid="diff"/g) ?? []).length === 3 && markup.includes("+100") && markup.includes("−20"),
  );
  check(
    "the summary line is drawn for every card that has one",
    (markup.match(/data-testid="story-summary"/g) ?? []).length === 4 &&
      markup.includes("verdict line wins") &&
      !markup.includes("second line never drawn"),
  );

  /* The board page's swap is App's, pinned pure: */
  check("story != null draws the grid", boardView(STORY) === "story");
  check("story == null draws the columns — no spinner state", boardView(null) === "columns");
  const columns = renderToStaticMarkup(<Board board={fixture.board} openCard={() => {}} />);
  check("and the columns are still the columns", columns.includes('data-testid="board"'));
}
