/* Pins the landing-timeline — `components/story/ChapterStory.tsx` and the pure
 * folds under it (`components/story/stats.ts`), plus App's swap decision
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
  criteria: ["the timeline replaces the columns"],
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
    title: `Station ${id}`,
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
    "stations sort ascending by since — landing order",
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

  check("the timeline renders", markup.includes('data-testid="chapter-story"'));
  check("the header celebrates the landed chapter", markup.includes("chapter landed"));
  check("the goal renders as markdown, backticks read", markup.includes("<code") && !markup.includes("`activity`"));
  check("the chapter's criteria are listed", markup.includes("the timeline replaces the columns"));
  check(
    "the stations appear in landing order in the markup",
    markup.indexOf("tk-first") < markup.indexOf("tk-second") &&
      markup.indexOf("tk-second") < markup.indexOf("tk-third") &&
      markup.indexOf("tk-third") < markup.indexOf("tk-gone"),
  );
  check("the dropped card is a muted station, not omitted", markup.includes('data-dropped="true"') && markup.includes("dropped"));
  check("the binary shows its chip", markup.includes('data-testid="bin-chip"'));
  check("worked time and commit count are chips", markup.includes("60m worked") && markup.includes("2 commits"));
  check("every station title is a button into the drawer", (markup.match(/data-testid="station-title"/g) ?? []).length === 4);

  /* sqrt scaling: tk-first (120 lines) is the max at 100%; tk-third (5 lines)
   * draws at sqrt(5/120) ≈ 20%, not the 4% a linear scale would flatten it to. */
  // lazy [^>]*? so the FIRST `width:` in the style wins, not max-width's
  const widths = [...markup.matchAll(/data-testid="diff-bar"[^>]*?width:([\d.]+)%/g)].map((m) => Number(m[1]));
  check(
    "diff bars are sqrt-scaled against the chapter's max",
    widths.length === 3 && Math.max(...widths) === 100 && widths.some((w) => w > 15 && w < 25),
    JSON.stringify(widths),
  );

  /* clicking a title opens the EXISTING drawer — under SSR the handler cannot
   * fire, so the wiring is pinned by the prop's effect being reachable: the
   * component took `openCard` and every station is a button (above). The board
   * page's swap is App's, pinned pure: */
  check("story != null draws the timeline", boardView(STORY) === "story");
  check("story == null draws the columns — no spinner state", boardView(null) === "columns");
  const columns = renderToStaticMarkup(<Board board={fixture.board} openCard={() => {}} />);
  check("and the columns are still the columns", columns.includes('data-testid="board"'));
}
