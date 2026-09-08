/* The Stream's whole vocabulary: which family a kind belongs to, what a run of
 * events by one worker on one card reads as, and how long something counts as
 * new. No React, no timers and no clock of its own.
 *
 * It is a plain module for the reason `toasts/model.ts` is one, and the two are
 * siblings: a hook that reads `Date.now()` inside itself can only be tested by
 * a browser and a stopwatch, and the smoke harness here has neither
 * (`react-dom/server`, one render, no jsdom). Every function below takes its
 * clock and its arrival stamps as ARGUMENTS, so the whole feature is pinned by
 * calling functions.
 *
 * ── Why a MOMENT and not a row ──────────────────────────────────────────────
 *
 * The Event stream on the Monitor draws one row per event and that is right for
 * what it answers: "what happened, in order, ever". A rail beside the code
 * answers a different question — "what are the workers DOING right now" — and
 * at that question one row per event is noise: a `taskops_plan` of nine cards
 * is nine identical rows, and a worker who commits three times in a minute
 * pushes everybody else's work off the screen.
 *
 * So consecutive events by the SAME actor on the SAME card within `MOMENT_GAP_S`
 * fold into one entry. The fold is on (actor, task) and not on actor alone
 * because a worker moving between two cards is exactly the change a reader
 * wants to see, and it is CONSECUTIVE-only — a moment never reaches back over
 * somebody else's work to collect an older run, which would put an entry above
 * events that happened after it.
 *
 * ── Why "new" is stamped by the CLIENT ──────────────────────────────────────
 *
 * `useEvents` stamps every row it catches up on with the reader's own clock and
 * this module reads those stamps; nothing here looks at `Event.ts`. A comment
 * written three minutes ago that reaches this tab now is NEW here, and a rail
 * that highlighted by `ts` would show it already faded. `toasts/model.ts::Toast
 * .shown` decided the same thing first, for the same reason.
 *
 * Nothing here is stored anywhere. There are no read-receipts on this board, by
 * design (CLAUDE.md: no mark-as-read verb, ever) — "new" is arithmetic over a
 * map that lives as long as the tab and dies with it.
 */

import { changed, oneLine, prose } from "../card/Thread";
import { trim } from "../toasts/model";
import type { Event } from "../../types";

/** How far apart two events by one worker on one card can be and still read as
 *  one thing they did. Two minutes: long enough to hold a commit and the
 *  comment that explains it, short enough that a worker who came back after
 *  lunch starts a new entry. */
export const MOMENT_GAP_S = 120;

/** The slide-in, and then the tint. Both are windows over the ARRIVAL stamp,
 *  and both are short: the rail is a live surface, so "new" has to mean the
 *  last few seconds or the whole screen reads as new and none of it does. */
export const ENTER_MS = 1_200;
export const FRESH_MS = 6_000;

/** What a kind is ABOUT, which is the only grouping a reader of this rail
 *  actually asks for. Five families, and every kind in `core/kinds.py` is in
 *  exactly one — a kind this bundle predates falls to "work", which is the
 *  honest default for a fact about a card. */
export type Family = "talk" | "work" | "code" | "review" | "chapter";

export const FAMILY: Record<string, Family> = {
  comment: "talk",
  created: "work",
  edited: "work",
  claimed: "work",
  released: "work",
  status: "work",
  commit: "code",
  merged: "code",
  submitted: "review",
  reviewed: "review",
  milestone: "chapter",
  project: "chapter",
  report: "chapter",
};

export function familyOf(event: Event): Family {
  return FAMILY[event.kind] ?? "work";
}

/** What the reader can narrow to. `all` is a filter and not the absence of one,
 *  so the chip row always has exactly one thing selected. */
export type Filter = "all" | Family;

export const FILTERS: readonly { id: Filter; name: string }[] = [
  { id: "all", name: "all" },
  { id: "talk", name: "talk" },
  { id: "work", name: "work" },
  { id: "code", name: "code" },
  { id: "review", name: "review" },
  { id: "chapter", name: "chapter" },
];

/** The rows a filter and a card selection leave. Both narrow; neither reorders.
 *  `task` is the reader clicking a card id to follow one card — `null` is every
 *  card, and "project" rows (the board's own history) are cards for this
 *  purpose, which is what lets a reader follow those too. */
export function keep(
  events: readonly Event[],
  filter: Filter,
  task: string | null,
): readonly Event[] {
  if (filter === "all" && task === null) return events;
  return events.filter(
    (e) => (filter === "all" || familyOf(e) === filter) && (task === null || e.task === task),
  );
}

/** One run of work: what a worker did on one card, without interruption. */
export interface Moment {
  /** the NEWEST event's id — stable across a re-render, unique in the log */
  key: string;
  actor: string;
  task: string;
  /** the newest event's `ts`: when this moment last moved */
  ts: number;
  /** the oldest event's `ts`: when it started */
  from: number;
  /** newest first, exactly as they came out of the log */
  events: readonly Event[];
}

/** The fold. `events` newest first (the feed's own order); the moments come
 *  back newest first too, and every event lands in exactly one.
 *
 *  The gap is measured against the OLDEST event collected so far and not
 *  against the first: a worker committing steadily every ninety seconds is one
 *  moment that keeps growing, which is what "without interruption" means. */
export function moments(
  events: readonly Event[],
  gapSeconds: number = MOMENT_GAP_S,
): readonly Moment[] {
  const out: Moment[] = [];
  let run: Event[] = [];
  const close = (): void => {
    if (run.length === 0) return;
    const newest = run[0]!;
    const oldest = run[run.length - 1]!;
    out.push({
      key: newest.id,
      actor: newest.actor,
      task: newest.task,
      ts: newest.ts,
      from: oldest.ts,
      events: run,
    });
    run = [];
  };
  for (const event of events) {
    const last = run[run.length - 1];
    const joins =
      last !== undefined &&
      last.actor === event.actor &&
      last.task === event.task &&
      last.ts - event.ts <= gapSeconds;
    if (!joins) close();
    run.push(event);
  }
  close();
  return out;
}

/** The plural a roll-up says. Only the kinds that actually arrive in runs are
 *  named; anything else falls back to "<kind> events", which is clumsy and
 *  true, and is the shape that tells the next reader a kind was added without
 *  a word for its plural. */
const MANY: Record<string, string> = {
  comment: "comments",
  created: "cards",
  edited: "edits",
  claimed: "claims",
  released: "releases",
  status: "status changes",
  commit: "commits",
  merged: "merges",
  submitted: "hand-ins",
  reviewed: "verdicts",
  milestone: "chapter changes",
  project: "board changes",
  report: "reports",
};

/** The newest progress a moment reports, 0–100, or null when it reports none.
 *  `progress` is an `edited` event like any other (`verbs/update.py::_progress`
 *  argues why it is not a kind of its own), so it is read off the body here
 *  rather than being given a branch in the vocabulary. */
export function progressOf(events: readonly Event[]): number | null {
  for (const event of events) {
    if (event.kind !== "edited" || event.body["field"] !== "progress") continue;
    const to = event.body["to"];
    if (typeof to === "number") return to;
  }
  return null;
}

/** A moment on one line. A run of one is the log's own phrase, unchanged
 *  (`Thread.tsx::oneLine`) — the rail must not grow a second wording for a
 *  single event. A run of several is counted, sized and, if the worker said how
 *  far along they are, ended with that number: `3 commits · 2 files · +41 −7 ·
 *  progress → 68`. */
export function roll(moment: Moment): string {
  if (moment.events.length === 1) return oneLine(moment.events[0]!);
  const counts = new Map<string, number>();
  for (const event of moment.events) {
    counts.set(event.kind, (counts.get(event.kind) ?? 0) + 1);
  }
  const parts: string[] = [];
  for (const [kind, n] of counts) {
    parts.push(n === 1 ? kind : `${n} ${MANY[kind] ?? `${kind} events`}`);
  }
  const sized = changed(moment.events);
  if (sized) parts.push(sized);
  const pct = progressOf(moment.events);
  if (pct !== null) parts.push(`progress → ${pct}`);
  return parts.join(" · ");
}

/** The human writing inside a moment, newest first, trimmed — what a reader
 *  came to the rail to read. A run of several events can carry several notes
 *  (a release and the comment before it), and all of them are shown: the roll
 *  says what happened, these say what was SAID.
 *
 *  `trim` is the toasts' own cut, imported rather than re-derived: the same
 *  sentence must not read two lengths on two surfaces. */
export function said(moment: Moment, limit: number): readonly { id: string; text: string }[] {
  const out: { id: string; text: string }[] = [];
  for (const event of moment.events) {
    const written = prose(event);
    if (written) out.push({ id: event.id, text: trim(written, limit) });
  }
  return out;
}

/** How new a thing is, at `now`, in the reader's own clock.
 *
 *  `entering` is the slide; `fresh` is the tint; `rest` is everything the
 *  reader was already looking at. Reduced motion collapses `entering` into
 *  `fresh` and keeps the tint: a colour is not motion, and removing the mark
 *  along with the animation would leave a reader who asked for stillness with
 *  no way to see what changed. `undefined` — a row the feed opened with — is at
 *  rest by definition: history is not news. */
export type Freshness = "entering" | "fresh" | "rest";

export function freshness(at: number | undefined, now: number, reduced: boolean): Freshness {
  if (at === undefined) return "rest";
  const age = now - at;
  if (age >= FRESH_MS) return "rest";
  if (age < ENTER_MS && !reduced) return "entering";
  return "fresh";
}

/** A moment is as new as its newest event: the stamp of the first row in it, or
 *  the newest stamp any of its rows carries when the top one was history and
 *  something older arrived late. */
export function arrivedAt(
  moment: Moment,
  arrivals: ReadonlyMap<string, number>,
): number | undefined {
  let at: number | undefined;
  for (const event of moment.events) {
    const stamp = arrivals.get(event.id);
    if (stamp !== undefined && (at === undefined || stamp > at)) at = stamp;
  }
  return at;
}

/** How many moments are still lit at `now` — the number the "new" pill shows a
 *  reader who has scrolled away from the top. Derived from the same stamps the
 *  tint is, so the pill and the highlight can never disagree. */
export function fresh(
  moments: readonly Moment[],
  arrivals: ReadonlyMap<string, number>,
  now: number,
): number {
  let n = 0;
  for (const moment of moments) {
    if (freshness(arrivedAt(moment, arrivals), now, true) !== "rest") n += 1;
  }
  return n;
}

/** The local calendar day an event belongs to, as a key. Local and not UTC
 *  because the divider a reader sees says "today", and their today is the one
 *  their clock is in — the same rule `core/hours.py` buckets by. */
export function dayKey(ts: number): string {
  const at = new Date(ts * 1000);
  const two = (n: number): string => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** What that divider says: today and yesterday by name, everything else by
 *  date. `now` is epoch SECONDS, the same unit every other clock in this
 *  dashboard passes around. */
export function dayLabel(ts: number, now: number): string {
  const key = dayKey(ts);
  if (key === dayKey(now)) return "today";
  if (key === dayKey(now - 86400)) return "yesterday";
  const at = new Date(ts * 1000);
  return `${at.getDate()} ${MONTHS[at.getMonth()] ?? ""}`;
}
