/* The one piece of state the whole app shares, and the live wiring behind it.
 *
 * A single hook rather than a store library: there are four pieces of data (config, board, fleet,
 * the open task) and one refresh path, so anything more would be ceremony. The rule that keeps it
 * simple is that events never patch state — they trigger a refetch, because the board is a
 * projection the server derives and re-reading it is more correct than mirroring it here. */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiFailure, subscribe } from "./api";
import type { Board, Config, Fleet, TaskView } from "./contracts";

export interface Studio {
  config: Config | null;
  board: Board | null;
  fleet: Fleet | null;
  open: TaskView | null;
  live: boolean;
  error: string;
  pulse: number;
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
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [open, setOpen] = useState<TaskView | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const [pulse, setPulse] = useState(0);

  /* The open task id in a ref as well as in state: the refetch callback needs to know which task
   * to reload, and closing over the state value would rebuild the subscription on every task
   * change — tearing down and reopening the SSE stream each time somebody clicks a card. */
  const openId = useRef<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextBoard, nextFleet] = await Promise.all([api.board(), api.fleet()]);
      setBoard(nextBoard);
      setFleet(nextFleet);
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

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    void load();
    const stop = subscribe(
      () => {
        setPulse((n) => n + 1);
        refresh();
      },
      () => {
        /* Refetch on every OPEN, not just the first. A reconnect after a dropped stream has an
         * unknown gap behind it, and this is what closes it — which is why the feed itself needs
         * no replay cursor. */
        setLive(true);
        void load();
      },
    );
    /* A stream that opens and then dies leaves `live` true forever otherwise. `onerror` is the
     * only signal EventSource gives while it retries. */
    const onError = () => setLive(false);
    window.addEventListener("offline", onError);
    return () => {
      stop();
      window.removeEventListener("offline", onError);
    };
  }, [load, refresh]);

  return { config, board, fleet, open, live, error, pulse, openTask, refresh };
}
