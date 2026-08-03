/* The one piece of state the whole app shares, and the live wiring behind it.
 *
 * A single hook rather than a store library: there are three pieces of data (config, board, the
 * open task) and one refresh path, so anything more would be ceremony. The rule that keeps it
 * simple is that events never patch state — they trigger a refetch, because the board is a
 * projection the server derives and re-reading it is more correct than mirroring it here. */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiFailure, subscribe } from "./api";
import type { Board, Config, ContextView, Event, TaskView } from "./contracts";
import { reduce, type Narration } from "./narration";

export interface Studio {
  config: Config | null;
  board: Board | null;
  /* The standing facts and settings. Fetched once and refetched only when an event says they
   * changed — the panel showing them is open all day, and re-reading them on every card move
   * would be a request per keystroke of somebody else's agent for prose that changes weekly. */
  context: ContextView | null;
  open: TaskView | null;
  live: boolean;
  error: string;
  pulse: number;
  /* The narration currently arriving on the socket, or the last one that finished. It lives
   * HERE rather than inside the reports view because the subscription does: one socket for the
   * whole app, and a component that unmounts must not take the stream down with it. */
  narration: Narration | null;
  /* The last event off the socket, kept so a listener can react to ONE kind without refetching.
   * The rule above still holds for the board — it refetches — but the chat thread is not a
   * projection anybody derives, so appending the frame is both cheaper and correct. */
  last: Event | null;
  openTask: (id: string | null) => void;
  refresh: () => void;
}

/* Coalescing window for refetches. A `plan` call writes N events in one transaction, and without
 * this the board would refetch N times in a few milliseconds. 120ms is under the threshold where
 * a person perceives delay, and it collapses a burst into one request. */
const COALESCE_MS = 120;

export function useStudio(): Studio {
  const [config, setConfig] = useState<Config | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [context, setContext] = useState<ContextView | null>(null);
  const [open, setOpen] = useState<TaskView | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const [pulse, setPulse] = useState(0);
  const [narration, setNarration] = useState<Narration | null>(null);
  const [last, setLast] = useState<Event | null>(null);

  /* The open task id in a ref as well as in state: the refetch callback needs to know which task
   * to reload, and closing over the state value would rebuild the subscription on every task
   * change — tearing down and reopening the SSE stream each time somebody clicks a card. */
  const openId = useRef<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      setBoard(await api.board());
      if (openId.current) setOpen(await api.task(openId.current));
      setError("");
    } catch (failure) {
      setError(failure instanceof ApiFailure ? failure.message : String(failure));
    }
  }, []);

  const refresh = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void load();
    }, COALESCE_MS);
  }, [load]);

  const openTask = useCallback((id: string | null) => {
    openId.current = id;
    if (id === null) {
      setOpen(null);
      return;
    }
    api.task(id).then(setOpen).catch((failure: unknown) => {
      setError(failure instanceof ApiFailure ? failure.message : String(failure));
    });
  }, []);

  /* Its own loader, not folded into `load`: that one runs on every event and on every reconnect,
   * and this reads three tables to answer a question whose answer changed last Tuesday. */
  const loadContext = useCallback(() => {
    api.context().then(setContext).catch(() => {});
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    void load();
    loadContext();
    const stop = subscribe(
      (event) => {
        setLast(event);
        setPulse((n) => n + 1);
        refresh();
        /* The two kinds that CAN change it. Anything else moves a card, and a card cannot
         * restate an invariant. */
        if (event.kind === "context" || event.kind === "policy") loadContext();
      },
      () => {
        /* Refetch on every OPEN, not just the first. A reconnect after a dropped stream has an
         * unknown gap behind it, and this is what closes it — which is why the feed itself needs
         * no replay cursor. */
        setLive(true);
        void load();
        loadContext();
      },
      /* NO refetch and NO pulse: a delta is not an event, nothing on the server stored it, and
       * a board that reloaded itself fifty times a second while somebody read a report would be
       * the most expensive way imaginable to render prose. */
      (message) => setNarration((was) => reduce(was, message)),
    );
    /* A stream that opens and then dies leaves `live` true forever otherwise. `onerror` is the
     * only signal EventSource gives while it retries. */
    const onError = () => setLive(false);
    window.addEventListener("offline", onError);
    return () => {
      stop();
      window.removeEventListener("offline", onError);
    };
  }, [load, refresh, loadContext]);

  return { config, board, context, open, live, error, pulse, narration, last, openTask,
           refresh };
}
