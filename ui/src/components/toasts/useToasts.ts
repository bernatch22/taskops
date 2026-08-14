/* The thin stateful half: the clock, the cursor and the already-seen set.
 *
 * `model.ts` owns every DECISION and has no clock; this hook owns the clock and
 * decides nothing. That line is why the whole feature is pinned by two smoke
 * sections with no timers and no jsdom in either of them.
 *
 * WHAT IT DOES NOT DO. It opens no socket, starts no fetch and reads no verb —
 * it is handed the `EventFeed` App already owns (`useEvents.ts` argues at
 * length why there is exactly one of those, and why it lives in App). A second
 * reader of the log for the toasts would have been a second clock asking one
 * verb, which is the shape `useBoard`'s one-owner rule exists to forbid.
 *
 * ONE TIMER, and only while something is standing. `setInterval` runs at
 * `TICK_MS` when the stack is non-empty and is torn down the moment it empties,
 * so an idle tab with no comments on it has no timer at all. Each tick does two
 * things with ONE reading of `Date.now()`: it hands that number to
 * `model.ts::expire`, and it stores it, which is what makes the tile pulse
 * decay without a second clock of its own.
 *
 * NOTHING IS STORED ANYWHERE. The head cursor and the seen set are refs — they
 * live as long as the tab and die with it. There are no read-receipts on this
 * board, by design (CLAUDE.md: no mark-as-read verb, ever), and the pulse is
 * derived per read from the same stack the toasts come from: no badge, no
 * counter, no per-card state.
 *
 * YOUR OWN COMMENT DOES NOT TOAST YOU. `pulse.actor` is who the server resolved
 * the reader as, and a notification for the sentence you just typed into the
 * drawer is noise — you watched it appear in the thread. It is still recorded
 * as SEEN, so it cannot arrive later through the dedupe's back door. Absent
 * `pulse.actor` (a board one version behind — types.ts) nothing is suppressed,
 * because "unknown" must never read as "everyone".
 */
import { useEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "../board/flip";
import { newComments, push, toastOf, expire, type Toast } from "./model";
import type { EventFeed } from "../../useEvents";
import type { BoardGroups } from "../../types";

/** How often the stack is re-judged. Half a second: the ttl is 8s and the pulse
 *  window 4s, so this is fine enough that neither ends visibly late, and coarse
 *  enough to be invisible next to the board's own 150ms refetch. */
export const TICK_MS = 500;

/** How long a commented tile stays lit. Long enough to find the card the toast
 *  is about, short enough that a busy board is not a christmas tree — and
 *  shorter than the toast's own ttl on purpose: the tile answers "which one",
 *  the toast answers "what was said". */
export const PULSE_MS = 4000;

/** Which cards are "just commented", at `now` — pure, so the highlight is
 *  pinned by calling it rather than by watching a board.
 *
 *  Derived from the SAME stack the toasts are drawn from, which is what makes
 *  "nothing stored" true rather than merely claimed: a card is lit because a
 *  toast about it is younger than the window, and it goes dark by arithmetic.
 *  An EXPANDED toast is not kept lit — expansion pins the message against its
 *  expiry (`model.ts::expire`), not the tile against its rest state. */
export function pulsing(
  stack: readonly Toast[],
  now: number,
  windowMs: number = PULSE_MS,
): ReadonlySet<string> {
  const out = new Set<string>();
  for (const toast of stack) {
    if (now - toast.shown < windowMs) out.add(toast.task);
  }
  return out;
}

const NONE: ReadonlySet<string> = new Set<string>();

export interface Toasts {
  /** newest first, capped — what `ToastStack` draws */
  stack: readonly Toast[];
  /** the card ids whose tile is lit right now */
  recent: ReadonlySet<string>;
  /** the reader asked for less motion: no slide, no growth, no pulse */
  reduced: boolean;
  expand: (id: string) => void;
  dismiss: (id: string) => void;
}

/** @param feed the ONE log read, owned by App (`useEvents.ts`)
 *  @param groups the current board's rows — where a card's title comes from
 *  @param self `pulse.actor`, when the board says it */
export function useToasts(
  feed: EventFeed,
  groups: BoardGroups | undefined,
  self: string | undefined,
): Toasts {
  const [stack, setStack] = useState<readonly Toast[]>([]);
  const [now, setNow] = useState<number>(() => Date.now());
  /** the previous page-one `head`; `null` until there has been one, which is
   *  what makes the first load silent (`model.ts::newComments`) */
  const lastHead = useRef<number | null>(null);
  const seen = useRef<Set<string>>(new Set<string>());

  const { head, events } = feed;
  useEffect(() => {
    if (head === null) return;
    const fresh = newComments(events, lastHead.current, head, seen.current);
    lastHead.current = head;
    if (fresh.length === 0) return;
    const stamp = Date.now();
    /* OLDEST first, because `push` puts each new toast on top: walking the
       newest-first window backwards leaves the newest at the head of the
       stack, which is where the design puts it. */
    const arriving = [...fresh].reverse();
    setStack((prev) => {
      let next = prev;
      for (const event of arriving) {
        seen.current.add(event.id);
        if (self && event.actor === self) continue;
        next = push(next, toastOf(event, groups, stamp));
      }
      return next;
    });
    setNow(stamp);
  }, [head, events, groups, self]);

  const idle = stack.length === 0;
  useEffect(() => {
    if (idle) return;
    const timer = setInterval(() => {
      const tick = Date.now();
      setNow(tick);
      setStack((prev) => expire(prev, tick));
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [idle]);

  /* Asked LIVE, every render, never read once at import: a reader who turns
     motion off mid-session is obeyed on the next frame (`flip.ts`). */
  const reduced = prefersReducedMotion(typeof window === "undefined" ? undefined : window);

  return {
    stack,
    // The pulse is pure decoration — it says "over there", and the toast says
    // everything. So reduced motion removes it outright rather than stilling it.
    recent: reduced ? NONE : pulsing(stack, now),
    reduced,
    expand: (id) =>
      setStack((prev) => prev.map((t) => (t.id === id ? { ...t, expanded: !t.expanded } : t))),
    dismiss: (id) => setStack((prev) => prev.filter((t) => t.id !== id)),
  };
}
