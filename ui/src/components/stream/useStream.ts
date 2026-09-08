/* The Stream's container half: the filter, the scroll position, and ONE timer.
 *
 * It exists because there are TWO mounts of the same picture — the full page
 * (`pages/Stream.tsx`) and the rail inside the Editor (`Stream.tsx::StreamRail`)
 * — and every stateful decision they make is identical: which family is
 * selected, which card is being followed, whether the reader is at the top, and
 * what time it is for the freshness windows. Two copies of that is how the two
 * surfaces come to disagree about what "new" means, which is the drift
 * `format.ts`'s docstring is the post-mortem of, one level up.
 *
 * What it does NOT do: fetch. It is handed the `EventFeed` App already owns
 * (`useEvents.ts`) — one read of the log, three surfaces reading it.
 *
 * The timer runs only while something is still inside its freshness window and
 * clears itself the moment nothing is, so an idle surface has no clock. It is
 * restarted by a NEW arrival (`youngest` changes identity), which is the whole
 * scheduling rule; `useToasts` reached the same shape from the same premise.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { prefersReducedMotion } from "../board/flip";
import { FRESH_MS, fresh, keep, moments, type Filter, type Moment } from "./model";
import type { EventFeed } from "../../useEvents";

/** How often the surface re-judges what is still lit. Finer than the toasts'
 *  500ms because the window it draws is shorter (`ENTER_MS` is 1.2s). */
export const TICK_MS = 250;

export interface StreamState {
  /** newest first, filtered and folded */
  moments: readonly Moment[];
  /** the reader's clock in MILLISECONDS, for the freshness windows */
  at: number;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  task: string | null;
  onTask: (task: string | null) => void;
  /** how many entries arrived above a reader who scrolled away from the top */
  waiting: number;
  onTop: () => void;
  onList: (el: HTMLDivElement | null) => void;
  onScroll: () => void;
  /** which moments have their prose open, by key. A SET and not a flag per
   *  entry: the reader opens two comments to compare them as often as one, and
   *  a single-open accordion would close the first one to answer the second. */
  expanded: ReadonlySet<string>;
  onExpand: (key: string) => void;
  reduced: boolean;
}

export function useStream(feed: EventFeed): StreamState {
  const [filter, setFilter] = useState<Filter>("all");
  const [task, setTask] = useState<string | null>(null);
  const [atTop, setAtTop] = useState(true);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set<string>());
  const [at, setAt] = useState<number>(() => Date.now());
  const box = useRef<HTMLDivElement | null>(null);

  const shown = useMemo(
    () => moments(keep(feed.events, filter, task)),
    [feed.events, filter, task],
  );

  const youngest = useMemo(() => {
    let latest = 0;
    for (const stamp of feed.arrivals.values()) if (stamp > latest) latest = stamp;
    return latest;
  }, [feed.arrivals]);

  useEffect(() => {
    setAt(Date.now());
    if (youngest === 0) return;
    const timer = setInterval(() => {
      const tick = Date.now();
      setAt(tick);
      if (tick - youngest >= FRESH_MS) clearInterval(timer);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [youngest]);

  /* Asked LIVE, every render, never read once at import: a reader who turns
     motion off mid-session is obeyed on the next frame (`flip.ts`). */
  const reduced = prefersReducedMotion(typeof window === "undefined" ? undefined : window);

  const top = (smooth: boolean): void => {
    box.current?.scrollTo({ top: 0, behavior: smooth && !reduced ? "smooth" : "auto" });
    setAtTop(true);
  };

  return {
    moments: shown,
    at,
    filter,
    onFilter: (next) => {
      setFilter(next);
      top(false);
    },
    task,
    onTask: (next) => {
      setTask(next);
      top(false);
    },
    // Both halves must be true: something arrived AND the reader is not at the
    // top. A reader watching the top simply sees the rows land, no chrome.
    waiting: atTop ? 0 : fresh(shown, feed.arrivals, at),
    onTop: () => top(true),
    onList: (el) => {
      box.current = el;
    },
    onScroll: () => setAtTop((box.current?.scrollTop ?? 0) <= 4),
    expanded,
    onExpand: (key) =>
      setExpanded((was) => {
        const next = new Set(was);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      }),
    reduced,
  };
}
