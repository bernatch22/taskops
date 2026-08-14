/* The toast MODEL, pinned by calling it — no render, no browser, no timers.
 *
 * This section draws nothing on purpose. `components/toasts/model.ts` is a pure
 * module precisely so the six rules this feature is accepted against can be
 * checked as function calls, with the clock and the cursor passed in; the stack
 * that draws them is a separate card and will be pinned by its markup. If a
 * rule below ever needs a render to check, that is the signal that a decision
 * leaked out of the model and into a component. */

import type { BoardGroups, Event } from "../../src/types";
import {
  TOAST_CAP,
  TOAST_TTL_MS,
  cardTitle,
  commentText,
  expire,
  newComments,
  push,
  toastOf,
  trim,
  type Toast,
} from "../../src/components/toasts/model";
import type { Check, Fixture, Harness } from "./section";

/** A log row, shaped as `core/types.py::Event` sends it and as `core/kinds.py:29`
 *  fills a comment's body. */
function ev(id: string, kind: string, task: string, text: string): Event {
  return {
    id,
    task,
    actor: "agent:berna/w4",
    kind,
    body: kind === "comment" ? { text } : { note: text },
    ts: 1_760_000_000,
  };
}

/** Page one as the verb answers it: NEWEST FIRST. */
const PAGE: readonly Event[] = [
  ev("e5", "comment", "tk-aaaaaa", "the newest word"),
  ev("e4", "commit", "tk-aaaaaa", "not a comment"),
  ev("e3", "comment", "tk-bbbbbb", "one below the top"),
  ev("e2", "comment", "tk-aaaaaa", "older than the window"),
  ev("e1", "claim", "tk-bbbbbb", "older still"),
];

const NONE: ReadonlySet<string> = new Set<string>();

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* ── 1. First load is silent ─────────────────────────────────────────────
   * A page of history is not news. With no previous head there is no delta,
   * and toasting the page would be fifty notifications on mount. */
  check(
    "first load toasts nothing, whatever page one holds",
    newComments(PAGE, null, 900, NONE).length === 0,
  );
  check(
    "a head that did not move toasts nothing",
    newComments(PAGE, 900, 900, NONE).length === 0,
  );
  // A board replaced under the tab reads as a head going backwards. Not news.
  check(
    "a head that went backwards toasts nothing",
    newComments(PAGE, 900, 880, NONE).length === 0,
  );

  /* ── 2. The head delta is the window, and only comments come through ──── */
  const advanced = newComments(PAGE, 900, 903, NONE);
  check(
    "head +3 surfaces the comments among the first three rows, newest first",
    advanced.length === 2 && advanced[0]?.id === "e5" && advanced[1]?.id === "e3",
    `got ${advanced.map((e) => e.id).join(",") || "nothing"}`,
  );
  check(
    "a commit inside the window is not a toast",
    !advanced.some((e) => e.kind !== "comment"),
  );
  check(
    "an older comment OUTSIDE the window stays quiet",
    !advanced.some((e) => e.id === "e2"),
  );

  /* ── 2b. The id dedupe — the safety net when the delta over-reaches ─────
   * A burst larger than a page makes the arithmetic claim rows the page does
   * not hold, so the same event can fall inside the window twice. It is shown
   * once, ever, by event id. */
  const again = newComments(PAGE, 900, 905, new Set(["e5", "e3"]));
  check(
    "an event already toasted is never toasted twice",
    again.length === 1 && again[0]?.id === "e2",
    `got ${again.map((e) => e.id).join(",") || "nothing"}`,
  );

  /* ── the body, narrowed once ─────────────────────────────────────────── */
  check("a comment's text is read from body.text", commentText(PAGE[0] as Event) === "the newest word");
  check(
    "a body without text reads as empty, never undefined",
    commentText(PAGE[1] as Event) === "",
  );

  /* ── 3. trim: whole words, an honest ellipsis ────────────────────────── */
  check("a short message is returned whole, with no ellipsis", trim("all of it", 40) === "all of it");
  check(
    "a message exactly at the limit is not cut",
    trim("0123456789", 10) === "0123456789",
  );
  const cut = trim("the quick brown fox jumps over the lazy dog", 20);
  check(
    "a long message is cut on a word boundary and says so",
    cut.endsWith("…") && cut.length <= 21 && !cut.includes("jum"),
    `got ${JSON.stringify(cut)}`,
  );
  check(
    "one word longer than the limit is cut rather than overflowing the box",
    trim("supercalifragilistic", 8) === "supercal…",
    `got ${JSON.stringify(trim("supercalifragilistic", 8))}`,
  );

  /* ── the card title, resolved here so the component stays dumb ────────── */
  const groups = {
    take: [{ id: "tk-aaaaaa", title: "Toast stack bottom-right" }],
    doing: [],
    merge: [],
    mentions: [],
    review: [],
    changes: [],
    stalled: [],
    reviewing: [],
    blocked: [],
  } as unknown as BoardGroups;
  check(
    "a commented card's title comes from whichever group holds its row",
    cardTitle(groups, "tk-aaaaaa") === "Toast stack bottom-right",
  );
  check(
    "a card whose row aged out falls back to its raw id, never to nothing",
    cardTitle(groups, "tk-zzzzzz") === "tk-zzzzzz",
  );
  check("board-level history keeps its own name", cardTitle(groups, "project") === "project");
  check("no board yet is still an id the reader can act on", cardTitle(undefined, "tk-aaaaaa") === "tk-aaaaaa");

  /* ── 4. push: newest on top, capped, oldest evicted ──────────────────── */
  const stamp = 10_000;
  let stack: readonly Toast[] = [];
  for (const id of ["a", "b", "c", "d", "e"]) {
    stack = push(stack, toastOf(ev(id, "comment", "tk-aaaaaa", id), groups, stamp));
  }
  check(
    `the stack is capped at ${TOAST_CAP}`,
    stack.length === TOAST_CAP,
    `got ${stack.length}`,
  );
  check(
    "newest is on top and the oldest beyond the cap is gone",
    stack.map((t) => t.id).join("") === "edcb",
    `got ${stack.map((t) => t.id).join("")}`,
  );
  check(
    "a toast carries the card's title, not just its id",
    stack[0]?.cardTitle === "Toast stack bottom-right",
  );
  // The same comment arriving twice (a resend, a replayed page) moves rather
  // than duplicates — an id appears once in the stack.
  const resent = push(stack, toastOf(ev("b", "comment", "tk-aaaaaa", "b"), groups, stamp));
  check(
    "the same event pushed again occupies one slot, on top",
    resent[0]?.id === "b" && resent.filter((t) => t.id === "b").length === 1,
  );

  /* ── 5. expire: the ttl, and expansion pinning against it ────────────── */
  const shown = 50_000;
  const three: readonly Toast[] = [
    { ...toastOf(ev("young", "comment", "tk-aaaaaa", "x"), groups, shown) },
    { ...toastOf(ev("old", "comment", "tk-aaaaaa", "x"), groups, shown - TOAST_TTL_MS - 1) },
    { ...toastOf(ev("read", "comment", "tk-aaaaaa", "x"), groups, shown - TOAST_TTL_MS - 1), expanded: true },
  ];
  const alive = expire(three, shown, TOAST_TTL_MS);
  check(
    "a toast younger than the ttl stands",
    alive.some((t) => t.id === "young"),
  );
  check(
    "a toast older than the ttl withdraws",
    !alive.some((t) => t.id === "old"),
  );
  check(
    "an EXPANDED toast never auto-expires — expansion is the reader reading",
    alive.some((t) => t.id === "read"),
  );
  // The toast's life starts when it is SHOWN, not when the comment was written:
  // a comment that reached the client late must still get its full ttl.
  const late = expire(
    [toastOf(ev("late", "comment", "tk-aaaaaa", "x"), groups, shown)],
    shown + 1,
    TOAST_TTL_MS,
  );
  check("a toast for an old comment still lives its full ttl", late.length === 1);
}
