/* The Event stream's own read — the ONE fetch in this dashboard that is not
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
 *     frame therefore resets this pane to page one for free, and there is no
 *     second listener to keep alive, reconnect or tear down.
 *   · it never writes anything but its own rows. No board state, no card.
 *
 * WHO CALLS IT: `App`, once, and nobody else. It lived inside `EventStreamPane`
 * while the Event stream was its only reader; the moment a SECOND surface wanted
 * the log (the comment toasts, which derive their news from `head`) that
 * placement would have become two hooks on two independent clocks asking the
 * same verb — the exact shape `useBoard`'s one-owner rule exists to forbid, one
 * level down. So the hook is called in App and the `EventFeed` is passed as a
 * prop, the same way the board payload is. The pane draws what it is handed.
 *
 * Resetting to page one on every board answer is the deliberate behaviour, not
 * a limitation: the pane shows the NEWEST events, and a reader who has paged
 * back into history while the board is moving is reading a log that grew above
 * them. Page one is the honest place to put them.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { Client } from "./client";
import type { Event, EventPage } from "./types";

/** Rows per page. `verbs/events.py::PAGE` picks the same number for the same
 *  reason (the pane scrolls inside a 620px box), and asking for it explicitly
 *  is what keeps the two from drifting silently. */
export const EVENT_PAGE = 50;

export interface EventFeed {
  events: readonly Event[];
  /** the LOG's length, `null` until the first answer */
  total: number | null;
  /** The board's `seq` at the moment of the last PAGE-ONE answer, `null` until
   *  there has been one. It is the cursor a second reader derives "what arrived
   *  since I last looked" from, and it is deliberately NOT advanced by an older
   *  page: paging back into history is not news arriving.
   *
   *  Why a head and not a seq per row is argued in `components/toasts/model.ts`
   *  — `verbs/events.py:53` drops the rowid on the way out. */
  head: number | null;
  /** an older page exists */
  more: boolean;
  loading: boolean;
  /** ask for the page behind the last one. A no-op while one is in flight. */
  loadMore: () => void;
}

interface Page {
  events: Event[];
  next: number | null;
  total: number | null;
  head: number | null;
}

const EMPTY: Page = { events: [], next: null, total: null, head: null };

/** The feed a caller with no wire gets: nothing read, nothing claimed. `total`
 *  is `null` rather than 0 because the pane draws that difference — a "0" there
 *  would be a statement the board never made. Exported for the headless smoke
 *  harness and for `Monitor`'s own default. */
export const EMPTY_FEED: EventFeed = {
  events: [],
  total: null,
  head: null,
  more: false,
  loading: false,
  loadMore: () => {},
};

/** @param client `null` renders the pane with nothing and asks for nothing — the
 *  headless smoke harness and any caller without a wire get the empty state
 *  rather than a crash.
 *  @param signal anything that changes identity when the board moved. */
export function useEvents(client: Client | null, signal: unknown): EventFeed {
  const [page, setPage] = useState<Page>(EMPTY);
  const [loading, setLoading] = useState(false);

  const alive = useRef(true);
  // Which reset this fetch belongs to. A page that comes back after the board
  // moved is answering a question nobody is asking any more, and appending it
  // would splice old rows under new ones — the one way this pane could show a
  // sequence the log never had.
  const era = useRef(0);
  const cursor = useRef<number | null>(null);

  const load = useCallback(
    async (before: number | null) => {
      if (!client) return;
      const mine = before === null ? ++era.current : era.current;
      setLoading(true);
      try {
        const args: Record<string, unknown> = { limit: EVENT_PAGE };
        if (before !== null) args["before"] = before;
        const answer = await client.rpc<EventPage>("events", args);
        if (!alive.current || era.current !== mine) return;
        cursor.current = answer.next;
        setPage((prev) => ({
          events: before === null ? answer.events : [...prev.events, ...answer.events],
          next: answer.next,
          total: answer.total,
          // Only page one moves the cursor. An OLDER page is answered with the
          // same `head` the board happens to be at, and taking it would make
          // "read history" look identical to "news arrived".
          head: before === null ? answer.head : prev.head,
        }));
      } catch {
        // The pane keeps the rows it has. A board that refuses or is unreachable
        // already says so once, from `useBoard`, at the top of the page; saying
        // it a second time inside one pane is noise, not information.
      } finally {
        if (alive.current && era.current === mine) setLoading(false);
      }
    },
    [client],
  );

  useEffect(() => {
    alive.current = true;
    cursor.current = null;
    // The rows are NOT cleared here: page one replaces them when it lands
    // (`before === null` above). Blanking first would make the pane flash empty
    // on every board answer, which on a busy board is every 150 ms.
    void load(null);
    return () => {
      alive.current = false;
    };
  }, [load, signal]);

  const loadMore = useCallback(() => {
    if (loading || cursor.current === null) return;
    void load(cursor.current);
  }, [load, loading]);

  return {
    events: page.events,
    total: page.total,
    head: page.head,
    more: page.next !== null,
    loading,
    loadMore,
  };
}
