/* The Event log's own read — the ONE fetch in this dashboard that is not
 * `useBoard`, and the reasons it is allowed to exist are written here so the
 * next person does not have to guess whether the rule was broken or narrowed.
 *
 * `useBoard`'s rule is that there is exactly one owner of "what the board says
 * right now", because every pane must paint from the SAME snapshot. This is not
 * that: the log is not a snapshot, it is a scrollback. It is unbounded, it is
 * paged, and the reader's position in it is view state belonging to one pane —
 * folding it into the board payload would make every 150 ms refetch carry
 * however many pages the reader had scrolled through, on the hot path every
 * open tab hits on a timer.
 *
 * What it does NOT do, and this is the half that keeps the rule intact:
 *
 *   · it opens NO socket. There is one feed, `client.subscribe`, and `useBoard`
 *     owns it. This hook is driven by a `signal` — anything whose identity
 *     changes when the board moved, and App hands it the board payload itself,
 *     which is a new object on every answer the one fetcher receives. A change
 *     frame therefore catches this pane up for free, and there is no second
 *     listener to keep alive, reconnect or tear down.
 *   · it never writes anything but its own rows. No board state, no card.
 *
 * WHO CALLS IT: `App`, once, and nobody else. It lived inside `EventStreamPane`
 * while the Event stream was its only reader; the moment a SECOND surface wanted
 * the log (the comment toasts, which derive their news from `head`) that
 * placement would have become two hooks on two independent clocks asking the
 * same verb — the exact shape `useBoard`'s one-owner rule exists to forbid, one
 * level down. So the hook is called in App and the `EventFeed` is passed as a
 * prop, the same way the board payload is. There are three readers now — the
 * Monitor's pane, the toasts, and the Editor's Stream rail — and still one read.
 *
 * ── IT CATCHES UP; IT DOES NOT START OVER (2026-09-08) ───────────────────────
 *
 * It used to re-read PAGE ONE on every board answer, and page one replaced the
 * rows. That was argued as honesty — "the pane shows the NEWEST events, and a
 * reader who has paged back into history is reading a log that grew above
 * them" — and it was the best the wire could do: `events` only read BACKWARDS,
 * so "what arrived" was a thing the client had to derive by arithmetic over a
 * page (`components/toasts/model.ts` is the post-mortem of that derivation).
 *
 * The verb reads forwards now. `events after=<head>` answers exactly the rows
 * written since the cursor the reader holds, oldest first, and pages forward on
 * `next` when the catch-up is bigger than one page (`verbs/events.py`). So the
 * honest thing and the useful thing are the same thing: new rows are PREPENDED,
 * the scrollback survives, and nobody has to guess which rows are new — the
 * answer to `after=` IS the news, by construction. It also costs less: a quiet
 * board answers a catch-up with an empty list instead of fifty rows, on every
 * poke.
 *
 * Three things follow, and each is a rule rather than a detail:
 *
 *   · WHAT ARRIVED IS STAMPED, in the client's clock, never in the event's
 *     `ts`. A comment written three minutes ago that reaches this tab now is
 *     NEW here, and a surface that highlighted by `ts` would show it already
 *     faded (`components/toasts/model.ts::Toast.shown` decided the same thing
 *     first, for the same reason). The stamps are pruned by `ARRIVAL_TTL_MS`,
 *     so the map is bounded by what arrived in the last minute and not by how
 *     long the tab has been open.
 *   · A CATCH-UP THAT WILL NOT END IS A RESET. `CATCH_UP_PAGES` bounds the
 *     forward walk; past it — a tab that slept through a thousand events — the
 *     feed starts over on page one, which is the only honest thing to draw when
 *     the middle is missing.
 *   · A HEAD THAT WENT BACKWARDS is a board replaced under the tab (a `board
 *     pull`, a different board on the same address). Nothing about that is
 *     news: the feed resets rather than prepending rows from a history this one
 *     never had.
 *
 * The rows still only ever GROW in a session. There is no trim: a session's
 * list is bounded by what actually happened on the board while the tab was
 * open, plus the one page of history it opened with — and a board that writes
 * more than a reader can hold in a tab is a different problem than this hook.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { Client } from "./client";
import type { Event, EventPage } from "./types";

/** Rows per page. `verbs/events.py::PAGE` picks the same number for the same
 *  reason (the pane scrolls inside a 620px box), and asking for it explicitly
 *  is what keeps the two from drifting silently. */
export const EVENT_PAGE = 50;

/** How far a single catch-up will walk forward before the feed gives up and
 *  starts over. Twelve pages is six hundred events in one poke — past that the
 *  tab was not reading, it was asleep. */
export const CATCH_UP_PAGES = 12;

/** How long an arrival stays marked as one. A minute is far longer than any
 *  surface draws it (the rail's own tiers are seconds — `components/stream/
 *  model.ts`), which is the point: the MAP is the fact, the fading is each
 *  surface's own arithmetic over it. */
export const ARRIVAL_TTL_MS = 60_000;

export interface EventFeed {
  /** newest first, merged: history below, everything that arrived above */
  events: readonly Event[];
  /** the LOG's length, `null` until the first answer */
  total: number | null;
  /** The board's `seq` at the moment of the last answer, `null` until there has
   *  been one. It is BOTH the cursor this hook catches up from and the one a
   *  second reader derives "what arrived since I last looked" from. */
  head: number | null;
  /** Event id → the client's clock when that row first arrived HERE, live.
   *  Empty for everything the feed opened with: history is not news. Pruned to
   *  `ARRIVAL_TTL_MS`, so it is bounded by the last minute. */
  arrivals: ReadonlyMap<string, number>;
  /** an older page exists */
  more: boolean;
  loading: boolean;
  /** ask for the page behind the last one. A no-op while one is in flight. */
  loadMore: () => void;
}

interface Page {
  events: readonly Event[];
  /** the cursor for the next OLDER page, null at the tail of history */
  older: number | null;
  total: number | null;
  head: number | null;
}

const EMPTY: Page = { events: [], older: null, total: null, head: null };
const NO_ARRIVALS: ReadonlyMap<string, number> = new Map<string, number>();

/** The feed a caller with no wire gets: nothing read, nothing claimed. `total`
 *  is `null` rather than 0 because the pane draws that difference — a "0" there
 *  would be a statement the board never made. Exported for the headless smoke
 *  harness and for `Monitor`'s own default. */
export const EMPTY_FEED: EventFeed = {
  events: [],
  total: null,
  head: null,
  arrivals: NO_ARRIVALS,
  more: false,
  loading: false,
  loadMore: () => {},
};

/** The merge, pure and exported so it is pinned by CALLING it rather than by
 *  watching a socket. `arrived` is newest first, like the list it goes on top
 *  of; an id already held is never added twice, which is what makes a catch-up
 *  that overlaps a page (a retry, a signal that fired twice) a no-op instead of
 *  a doubled row. */
export function merge(have: readonly Event[], arrived: readonly Event[]): readonly Event[] {
  if (arrived.length === 0) return have;
  const held = new Set(have.map((e) => e.id));
  const fresh = arrived.filter((e) => !held.has(e.id));
  if (fresh.length === 0) return have;
  return [...fresh, ...have];
}

/** The arrival stamps after a catch-up: everything past the window dropped,
 *  everything that just landed stamped at `at`. Pure and exported for the same
 *  reason `merge` is — and an id that arrives TWICE keeps its later stamp,
 *  because a row can only arrive once and the second sighting is the bug this
 *  would otherwise hide by re-lighting a settled row. */
export function stamp(
  was: ReadonlyMap<string, number>,
  ids: readonly string[],
  at: number,
  ttlMs: number = ARRIVAL_TTL_MS,
): ReadonlyMap<string, number> {
  if (ids.length === 0) {
    let stale = false;
    for (const when of was.values()) if (at - when >= ttlMs) stale = true;
    if (!stale) return was;
  }
  const next = new Map<string, number>();
  for (const [id, when] of was) if (at - when < ttlMs) next.set(id, when);
  for (const id of ids) if (!next.has(id)) next.set(id, at);
  return next;
}

/** @param client `null` renders the pane with nothing and asks for nothing — the
 *  headless smoke harness and any caller without a wire get the empty state
 *  rather than a crash.
 *  @param signal anything that changes identity when the board moved. */
export function useEvents(client: Client | null, signal: unknown): EventFeed {
  const [page, setPage] = useState<Page>(EMPTY);
  const [arrivals, setArrivals] = useState<ReadonlyMap<string, number>>(NO_ARRIVALS);
  const [loading, setLoading] = useState(false);

  const alive = useRef(true);
  // Which reset this fetch belongs to. A page that comes back after the feed
  // started over is answering a question nobody is asking any more, and taking
  // it would splice rows from two eras into one list.
  const era = useRef(0);
  /** the cursor for the next OLDER page — the reader's own paging */
  const older = useRef<number | null>(null);
  /** the LIVE cursor: the head of the last answer, what `after=` is asked with */
  const head = useRef<number | null>(null);
  /** a catch-up is in flight; a signal that fires during one is remembered, not
   *  run alongside it — two forward walks from one cursor would ask for the
   *  same rows twice. */
  const busy = useRef(false);
  const again = useRef(false);

  const ask = useCallback(
    async (args: Record<string, unknown>): Promise<EventPage | null> => {
      if (!client) return null;
      return await client.rpc<EventPage>("events", { limit: EVENT_PAGE, ...args });
    },
    [client],
  );

  /** Page one, and everything about the reader's position discarded with it.
   *  The rows are NOT cleared first: page one replaces them when it lands.
   *  Blanking would make the pane flash empty on every reset. */
  const first = useCallback(async () => {
    const mine = ++era.current;
    setLoading(true);
    try {
      const answer = await ask({});
      if (!answer || !alive.current || era.current !== mine) return;
      older.current = answer.next;
      head.current = answer.head;
      // History is not news: the opening page stamps nothing (the toasts
      // reached the same conclusion first — `toasts/model.ts::newComments`).
      setArrivals(NO_ARRIVALS);
      setPage({
        events: answer.events,
        older: answer.next,
        total: answer.total,
        head: answer.head,
      });
    } catch {
      // The pane keeps the rows it has. A board that refuses or is unreachable
      // already says so once, from `useBoard`, at the top of the page; saying
      // it a second time inside one pane is noise, not information.
    } finally {
      if (alive.current && era.current === mine) setLoading(false);
    }
  }, [ask]);

  /** Forward from the live cursor, walking `next` until the catch-up is short.
   *  Everything it collects is prepended in one state write, so a burst is one
   *  render and not one per page. */
  const catchUp = useCallback(async () => {
    const from = head.current;
    if (from === null) return;
    const mine = era.current;
    busy.current = true;
    try {
      const arrived: Event[] = [];
      let at = from;
      let walked = 0;
      let last: EventPage | null = null;
      for (;;) {
        const answer = await ask({ after: at });
        if (!answer || !alive.current || era.current !== mine) return;
        last = answer;
        // The verb answers a catch-up OLDEST first; the list is newest first.
        arrived.unshift(...[...answer.events].reverse());
        walked += 1;
        if (answer.next === null) break;
        if (walked >= CATCH_UP_PAGES) {
          // The middle is missing and no cursor can recover it honestly.
          void first();
          return;
        }
        at = answer.next;
      }
      if (!last) return;
      head.current = last.head;
      const landed = last;
      const when = Date.now();
      setArrivals((was) => stamp(was, arrived.map((e) => e.id), when));
      setPage((prev) => {
        const events = merge(prev.events, arrived);
        // A catch-up that found nothing is not a state change. `merge` returns
        // the SAME array when nothing was added, so this keeps the whole feed's
        // identity stable and the panes reading it re-fold nothing.
        if (events === prev.events && prev.total === landed.total && prev.head === landed.head) {
          return prev;
        }
        return { events, older: prev.older, total: landed.total, head: landed.head };
      });
    } catch {
      // Same silence as `first`, and the cursor is left where it was: the next
      // signal asks the same question again, which is the whole retry.
    } finally {
      busy.current = false;
      if (again.current && alive.current && era.current === mine) {
        again.current = false;
        void catchUp();
      }
    }
  }, [ask, first]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // A new client is a new board: everything starts over.
  useEffect(() => {
    head.current = null;
    older.current = null;
    void first();
  }, [first]);

  useEffect(() => {
    if (head.current === null) return; // the opening page is still in flight
    if (busy.current) {
      again.current = true;
      return;
    }
    void catchUp();
  }, [signal, catchUp]);

  const loadMore = useCallback(() => {
    if (loading || older.current === null || !client) return;
    const mine = era.current;
    const before = older.current;
    setLoading(true);
    void (async () => {
      try {
        const answer = await ask({ before });
        if (!answer || !alive.current || era.current !== mine) return;
        older.current = answer.next;
        setPage((prev) => ({
          events: [...prev.events, ...answer.events],
          older: answer.next,
          total: answer.total,
          // An OLDER page does NOT move the live cursor: reading history is not
          // news arriving, and taking its `head` would make the two look alike.
          head: prev.head,
        }));
      } catch {
        // as above
      } finally {
        if (alive.current && era.current === mine) setLoading(false);
      }
    })();
  }, [ask, client, loading]);

  return {
    events: page.events,
    total: page.total,
    head: page.head,
    arrivals,
    more: page.older !== null,
    loading,
    loadMore,
  };
}
