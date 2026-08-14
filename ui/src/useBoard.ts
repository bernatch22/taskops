/* The one hook that fetches. No component calls the client directly.
 *
 * There is exactly one owner of "what the board says right now", and it is this
 * file. That is not tidiness: the feed is a signal, so a refetch must be
 * coalesced across every reason to refetch at once, and a second component with
 * its own effect would fetch on its own clock and paint a board half a second
 * older than the one next to it.
 *
 * Nothing here renders a frame. A frame pokes `refresh`, `refresh` asks the
 * board, and the board's answer is the only thing that ever reaches state. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { RpcError, type Client } from "./client";
import { chapterComplete } from "./completed";
import { THROUGHPUT_WINDOW } from "./components/monitor/panels";
import type { ActivityPayload, BoardPayload, CardPayload } from "./types";

/** One window for a burst of writes. Long enough that an orchestrator's
 *  plan-of-nine is one refetch, short enough to read as instant. */
const COALESCE_MS = 150;

/* ── Why the hours window is asked for HERE ───────────────────────────────────
 *
 * `pulse.py::run` returns `"hours": _hours(...) if window else None` — the field
 * exists only when the call asks for it. Monitor's Throughput pane was wired to
 * `board.hours` and therefore drew its empty state forever.
 *
 * Two ways to fix it, and this is the deliberate one: the ONE fetcher asks for
 * the window, always. The alternative — Throughput owning a `report` call of its
 * own — contradicts the rule at the top of this file. There is exactly one owner
 * of "what the board says right now"; a second component with its own effect
 * fetches on its own clock and paints a chart from a different snapshot than the
 * rows beside it, and every socket frame would then have to fan out to two
 * fetchers instead of one coalesced refetch.
 *
 * The cost of doing it here was measured against the live board (14 days, 20
 * cards closed, 145 events) rather than guessed. `verbs/report.py::summary` runs
 * one `cache.window` over the whole span plus one per day — 15 SQLite reads —
 * and folds them with `core/hours.py`:
 *
 *     board {}                            ~2.9 ms    8.8 KB
 *     board {window:"14d", tz:"…"}        ~4.2 ms   14.5 KB
 *
 * +1.3 ms and +5.7 KB per refetch, on a request that is already coalesced to one
 * per 150 ms burst. That is the price of every pane sharing one snapshot, and it
 * is paid on the Board tab too — cheaper than the tab-dependent fetch that would
 * avoid it, which would turn switching tabs into a refetch.
 *
 * The zone must be the browser's real IANA zone: `core/hours.py` buckets by
 * calendar day between two local midnights, so a hardcoded UTC silently shifts
 * every bar. `""` from a runtime with no zone data falls back to the board's own
 * default rather than to a guess. */
/* `milestone` joins them for the same reason and by the same route: the chapter
 * in focus is an ARGUMENT to the one `board` call, held by App beside the tab and
 * carried by every refetch the socket triggers. It is OMITTED when empty rather
 * than sent as `""` — `verbs/pulse.py::_which` reads an absent milestone as
 * "resolve the open one yourself", which is exactly the unfiltered behaviour that
 * "all chapters" has to keep reaching. */
function boardArgs(milestone: string): Record<string, unknown> {
  const args: Record<string, unknown> = { window: THROUGHPUT_WINDOW, tz: browserZone() };
  if (milestone) args["milestone"] = milestone;
  return args;
}

function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export interface Board {
  board: BoardPayload | null;
  card: CardPayload | null;
  /** The chapter's STORY — the `activity` answer for the milestone in focus,
   *  fetched by the same `fetchAll` as everything else, and only when the
   *  chapter is complete (`completed.ts::chapterComplete`). `null` the rest of
   *  the time: an open chapter has columns, not a story. Headline depth on
   *  purpose — the 76-card budget in `verbs/activity.py`'s docstring is why
   *  `depth=full` is never asked for here. */
  story: ActivityPayload | null;
  /** The feed is connected. False means the page may be stale. */
  live: boolean;
  /** Open a card's dossier, or null to close it. */
  openCard: (task: string | null) => void;
  openId: string | null;
  /** The last failure, kept until something succeeds. A refusal's message names
   *  the call that fixes it, so it is shown as the server wrote it. */
  error: RpcError | null;
  /** True until the first answer arrives — an empty board and an unfetched one
   *  are not the same picture. */
  loading: boolean;
  /** The ONE write. Refetch comes from the feed's own change signal. */
  comment: (text: string, mentions?: string[]) => Promise<void>;
  /** Force a refetch: after pasting a token, or a manual reload. */
  refresh: () => void;
}

/** @param milestone the chapter in focus, "" for all of them. Changing it makes a
 *  new `fetchAll`, which the mount effect depends on — so a pick refetches at
 *  once, and every later socket frame carries the same choice. */
export function useBoard(client: Client, milestone: string = ""): Board {
  const [board, setBoard] = useState<BoardPayload | null>(null);
  const [card, setCard] = useState<CardPayload | null>(null);
  const [story, setStory] = useState<ActivityPayload | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<RpcError | null>(null);
  const [loading, setLoading] = useState(true);

  // The open card is read from inside a timer that outlives the render that
  // scheduled it, so it travels in a ref. Reading state there would refetch the
  // card that was open when the socket connected, forever.
  const open = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  const fetchAll = useCallback(async () => {
    try {
      const next = await client.rpc<BoardPayload>("board", boardArgs(milestone));
      if (!alive.current) return;
      setBoard(next);
      setError(null);
      // The chapter story rides the SAME fetch path — one owner, one clock. It
      // is asked for only when a milestone is in focus and reads as complete;
      // otherwise the story is null and no `activity` call is made at all.
      if (next.milestone && chapterComplete(next)) {
        const tale = await client.rpc<ActivityPayload>("activity", {
          milestone: next.milestone.id,
        });
        if (!alive.current) return;
        setStory(tale);
      } else {
        setStory(null);
      }
      const task = open.current;
      if (task) {
        const dossier = await client.rpc<CardPayload>("card", { task });
        // Still the same card? The drawer may have moved while this was in
        // flight, and writing a stale dossier into it is a visible glitch.
        if (alive.current && open.current === task) setCard(dossier);
      }
    } catch (err) {
      if (alive.current) setError(asRpcError(err));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [client, milestone]);

  /** Every reason to refetch goes through here, so N reasons in one window are
   *  one request. Criterion 1: a frame arrives → exactly one refetch. */
  const poke = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      void fetchAll();
    }, COALESCE_MS);
  }, [fetchAll]);

  useEffect(() => {
    alive.current = true;
    void fetchAll(); // the mount fetch is immediate: nothing to coalesce with
    const stop = client.subscribe(poke, setLive);
    return () => {
      alive.current = false;
      if (timer.current !== null) clearTimeout(timer.current);
      stop();
    };
  }, [client, fetchAll, poke]);

  const openCard = useCallback(
    (task: string | null) => {
      open.current = task;
      setOpenId(task);
      setCard(null); // never show the previous card's thread under a new title
      if (!task) return;
      void (async () => {
        try {
          const dossier = await client.rpc<CardPayload>("card", { task });
          if (alive.current && open.current === task) setCard(dossier);
        } catch (err) {
          if (alive.current) setError(asRpcError(err));
        }
      })();
    },
    [client],
  );

  const comment = useCallback(
    async (text: string, mentions: string[] = []) => {
      const task = open.current;
      if (!task || !text.trim()) return;
      // The same door every agent uses: `update` with comment=, and mentions=
      // riding on it. No status, no take, no merge — the browser does not move
      // a card, and a second way to move one is a second way to disagree.
      await client.rpc("update", { task, comment: text, mentions });
      // No refetch here on purpose: the write produced an event, the event
      // publishes a change frame, and the frame pokes the one refresh path.
    },
    [client],
  );

  return useMemo(
    () => ({ board, card, story, live, openCard, openId, error, loading, comment, refresh: poke }),
    [board, card, story, live, openCard, openId, error, loading, comment, poke],
  );
}

function asRpcError(err: unknown): RpcError {
  if (err instanceof RpcError) return err;
  // A network failure is not an envelope: `unreachable` is the board's own word
  // for it (_errors.py), so the UI has one vocabulary and not two.
  return new RpcError("unreachable", err instanceof Error ? err.message : String(err));
}
