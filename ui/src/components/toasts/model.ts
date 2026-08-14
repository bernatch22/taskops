/* The toast model — every decision this feature makes about WHICH comments are
 * new, what a preview says, how deep the stack goes and when a toast leaves,
 * with no React, no timers and no clock of its own.
 *
 * It is a plain module because the alternative was measured elsewhere in this
 * dashboard and rejected: a hook that reads `Date.now()` inside itself can only
 * be tested by a browser and a stopwatch, and the smoke harness here has
 * neither (`react-dom/server`, one render, no jsdom). Every function below
 * takes its clock, its cursor and its already-seen set as ARGUMENTS, so the
 * whole feature is pinned by calling functions.
 *
 * ── Why "new" is a head delta and an id set, and not a per-event seq ────────
 *
 * `verbs/events.py::run` answers page one newest-first and returns `head` — the
 * board's sequence at the moment of the read. It does NOT return a seq per
 * event: line 53 is `[event for _, event in rows]`, the rowid is dropped on the
 * way out. So the client cannot ask "which rows are above my cursor" directly;
 * it derives it: `head - lastHead` events arrived, and page one is newest
 * first, so they are its first `head - lastHead` rows.
 *
 * That arithmetic is exact until a burst larger than a page (`EVENT_PAGE`, 50)
 * lands between two reads, and then it over-counts: the delta says 60, the page
 * holds 50, and the 50th row is older than the cursor claims. The id set is the
 * safety net for exactly that case — a toast is shown once, by event id, ever.
 * Which is also why the FIRST load is silent: with no previous head there is no
 * delta, and a page of history toasted on mount would be 50 notifications for
 * things that happened yesterday.
 *
 * Nothing here is stored anywhere. There are no read-receipts on this board, by
 * design (CLAUDE.md: no mark-as-read verb, ever) — "already toasted" is a set
 * that lives as long as the tab and dies with it.
 */

import type { BoardGroups, Event } from "../../types";

/** How many toasts stand at once. Four is the design's: the stack sits above
 *  the bottom-right corner and a fifth would reach into the board behind it.
 *  Beyond the cap the OLDEST leaves — a notification stack is a window on the
 *  newest, not a queue that must be drained. */
export const TOAST_CAP = 4;

/** How long a toast stands before it withdraws, in milliseconds. */
export const TOAST_TTL_MS = 8000;

/** Roughly two lines at the stack's width. `trim` cuts on a word boundary at or
 *  before this, so the real cut is a little shorter and never longer. */
export const TRIM_LIMIT = 120;

/** One notification. `id` is the EVENT's id — that is what makes "already
 *  toasted" answerable without storing anything, since event ids are
 *  `sha256(canonical)[:32]` and a comment cannot collide with itself. */
export interface Toast {
  /** the comment event's id */
  id: string;
  /** the card it was written on */
  task: string;
  /** that card's title, resolved once here so the component stays dumb */
  cardTitle: string;
  /** who wrote it */
  actor: string;
  /** the comment's body text, WHOLE — `trim` is applied at render, so expanding
   *  a toast in place needs no second lookup */
  text: string;
  /** the event's own timestamp, epoch SECONDS, as `core/types.py::Event` sends
   *  it. For display only. */
  ts: number;
  /** when this toast entered the stack, in the caller's own clock unit (the
   *  same one `expire` is given). NOT `ts`: a comment can arrive at the client
   *  seconds or minutes after it was written, and a toast that inherited the
   *  event's age would flash and vanish. A toast's life starts when it is
   *  shown. */
  shown: number;
  /** expanded in place by a click — which PINS it (see `expire`) */
  expanded: boolean;
}

/** The comment events that arrived between two reads of the feed.
 *
 *  @param events page one of the log, NEWEST FIRST (`verbs/events.py`)
 *  @param lastHead the `head` of the previous answer, or `null` on first load
 *  @param head the `head` of this answer
 *  @param seen event ids already toasted this session — the dedupe that holds
 *         when the delta and the page disagree (a burst larger than a page)
 *  @returns the events to toast, newest first. Empty on first load, on a head
 *           that did not move, and on a head that went BACKWARDS (a board
 *           replaced under the tab — nothing about that is news).
 */
export function newComments(
  events: readonly Event[],
  lastHead: number | null,
  head: number,
  seen: ReadonlySet<string>,
): readonly Event[] {
  if (lastHead === null) return [];
  const delta = head - lastHead;
  if (delta <= 0) return [];
  return events
    .slice(0, delta)
    .filter((event) => event.kind === "comment" && !seen.has(event.id));
}

/** The comment's body text, as `core/kinds.py:29` stores it (`body.text`).
 *  Returns "" for a body shaped otherwise rather than rendering `undefined` —
 *  `Event.body` is `Record<string, unknown>` on purpose (an unknown kind is
 *  stored intact), so this is the one place that narrows it. */
export function commentText(event: Event): string {
  const text = event.body["text"];
  return typeof text === "string" ? text : "";
}

/** The preview cut: at most `limit` characters, on a WORD boundary, with an
 *  ellipsis that is honest — it appears only when something was actually cut.
 *  A single word longer than the limit is cut mid-word rather than returned
 *  whole, because the alternative is a toast that overflows its own box. */
export function trim(text: string, limit: number = TRIM_LIMIT): string {
  const flat = text.trim().replace(/\s+/g, " ");
  if (flat.length <= limit) return flat;
  const head = flat.slice(0, limit);
  const space = head.lastIndexOf(" ");
  const cut = space > 0 ? head.slice(0, space) : head;
  return `${cut.replace(/[.,;:]$/, "")}…`;
}

/** Newest on top, capped. The oldest beyond `cap` is dropped — including a
 *  pinned one: expansion pins against the CLOCK (`expire`), not against a
 *  reader who kept commenting. */
export function push(
  stack: readonly Toast[],
  toast: Toast,
  cap: number = TOAST_CAP,
): readonly Toast[] {
  return [toast, ...stack.filter((t) => t.id !== toast.id)].slice(0, Math.max(cap, 0));
}

/** Which toasts survive at `now`. Anything shown longer ago than `ttlMs` goes,
 *  EXCEPT one the reader expanded: opening a message is the reader saying they
 *  are reading it, and a notification that withdrew mid-sentence would be the
 *  one bug this whole surface is judged on. A pinned toast leaves by being
 *  collapsed, dismissed, or pushed off the cap.
 *
 *  `now` and `ttlMs` share a unit and it is the caller's — `Toast.shown` is
 *  stamped in the same one. */
export function expire(
  stack: readonly Toast[],
  now: number,
  ttlMs: number = TOAST_TTL_MS,
): readonly Toast[] {
  return stack.filter((t) => t.expanded || now - t.shown < ttlMs);
}

/** A card id → its title, over every row the board payload carries. The groups
 *  are the only place the dashboard learns titles, and a card can appear in any
 *  of them, so all ten are searched rather than guessing which one a commented
 *  card sits in.
 *
 *  Falls back to the RAW `tk-` id, never to "" or "unknown": a card whose row
 *  aged out (`done` is capped at 20) or which belongs to another chapter is
 *  still a card the reader can open, and the id is the thing they can act on.
 *  `task: "project"` — board-level history — comes back as itself for the same
 *  reason. */
export function cardTitle(groups: BoardGroups | undefined, task: string): string {
  if (!groups) return task;
  for (const rows of Object.values(groups)) {
    if (!Array.isArray(rows)) continue;
    for (const row of rows as readonly { id: string; title: string }[]) {
      if (row.id === task && row.title) return row.title;
    }
  }
  return task;
}

/** A comment event plus a board becomes a toast. One place, so the component
 *  that draws the stack holds no knowledge of the log's shape. */
export function toastOf(
  event: Event,
  groups: BoardGroups | undefined,
  shown: number,
): Toast {
  return {
    id: event.id,
    task: event.task,
    cardTitle: cardTitle(groups, event.task),
    actor: event.actor,
    text: commentText(event),
    ts: event.ts,
    shown,
    expanded: false,
  };
}
