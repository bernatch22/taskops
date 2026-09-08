/* The Stream — the log as a live rail, beside the code.
 *
 * WHAT IT ANSWERS, and why it is not the Monitor's Event stream moved. That
 * pane answers "what happened, in order, ever": one row per event, board-wide,
 * paged, read at a desk. This answers "what are the workers doing RIGHT NOW",
 * in a 320px column next to the file you are reading, and the difference is
 * visible in three decisions:
 *
 *   · a run of events by one worker on one card is ONE entry (`model.ts`
 *     argues the fold). Nine rows from one `taskops_plan` would push everybody
 *     else off a column this narrow.
 *   · what ARRIVED while you were looking is marked, and fades by arithmetic —
 *     no badge, no counter, nothing stored (CLAUDE.md: no mark-as-read verb,
 *     ever).
 *   · it never steals the reader's place. New entries land on top; if the
 *     reader has scrolled down into history the list does NOT move under them,
 *     and a pill says how many are waiting above.
 *
 * TWO EXPORTS, ONE PICTURE, the same seam `EventStream` sits behind and for the
 * same reason: `Stream` is PURE — moments in, markup out, no client, no effect,
 * no clock — so the smoke harness renders the real entry markup under
 * `react-dom/server`; `StreamRail` is the container that owns the filter, the
 * scroll position and the one timer.
 *
 * IT OPENS NO FETCH AND NO SOCKET. It is handed the `EventFeed` App already
 * owns (`useEvents.ts`), exactly as the Monitor's pane and the toasts are —
 * three readers, one read. The card popup is `openCard`, the same door every
 * other surface uses; the Drawer is mounted once in App, over whichever page is
 * on, so this rail draws no dossier of its own.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { ago, shortActor } from "../../format";
import { DOT } from "../card/Thread";
import { TONE_FG, type Tone } from "../board/CardTile";
import { prefersReducedMotion } from "../board/flip";
import {
  FILTERS,
  FRESH_MS,
  arrivedAt,
  dayKey,
  dayLabel,
  fresh,
  freshness,
  keep,
  moments,
  roll,
  said,
  type Filter,
  type Moment,
} from "./model";
import { EMPTY_FEED, type EventFeed } from "../../useEvents";

/** How often the rail re-judges what is still lit. Finer than the toasts' 500ms
 *  because the window it draws is shorter (`ENTER_MS` is 1.2s), and it stops
 *  itself the moment nothing is fresh — an idle rail has no timer at all. */
export const TICK_MS = 250;

/** The prose cut, at this column's width. Shorter than the toasts' 120: a
 *  toast is two lines across the bottom of the screen, this is a 320px rail. */
export const SAID_LIMIT = 96;

export interface StreamProps {
  /** newest first, already filtered — the container does the narrowing */
  moments: readonly Moment[];
  /** event id → when it arrived here (`useEvents.ts`) */
  arrivals: ReadonlyMap<string, number>;
  /** the reader's clock in MILLISECONDS, for the freshness windows */
  at: number;
  /** the board's clock in SECONDS, for `ago` */
  now: number;
  /** the LOG's length, `null` when nothing has asked for it */
  total: number | null;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  /** the one card being followed, `null` for every card */
  task: string | null;
  onTask: (task: string | null) => void;
  /** open a card's dossier — App's `openCard`, the one door */
  onOpen: (task: string) => void;
  more: boolean;
  loading: boolean;
  onMore: () => void;
  /** how many entries arrived above a reader who has scrolled away from the top */
  waiting: number;
  onTop: () => void;
  onList: (el: HTMLDivElement | null) => void;
  onScroll: () => void;
  reduced: boolean;
}

const head: React.CSSProperties = {
  flex: "none",
  display: "grid",
  gap: "8px",
  padding: "9px 12px 8px",
  borderBottom: "1px solid var(--hair)",
  background: "var(--pane-2)",
};

const chips: React.CSSProperties = {
  display: "flex",
  gap: "3px",
  overflowX: "auto",
  scrollbarWidth: "none",
};

const chip = (on: boolean): React.CSSProperties => ({
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  flex: "none",
  padding: "3px 9px",
  borderRadius: "8px",
  fontSize: "11px",
  letterSpacing: "-0.01em",
  color: on ? "var(--accent-hi)" : "var(--text-3)",
  background: on ? "var(--accent-soft)" : "transparent",
});

const list: React.CSSProperties = {
  flex: "1 1 0px",
  minHeight: 0,
  overflowY: "auto",
  padding: "2px 0 16px",
};

const divider: React.CSSProperties = {
  position: "sticky",
  top: 0,
  zIndex: 1,
  padding: "6px 12px 5px",
  fontSize: "10px",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--faint)",
  background: "var(--pane)",
  borderBottom: "1px solid var(--hair)",
};

const body = (tone: Tone): React.CSSProperties => ({
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "block",
  width: "100%",
  paddingLeft: "10px",
  borderLeft: `2px solid ${TONE_FG[tone]}`,
});

const note: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--text-3)",
  padding: "22px 14px",
  lineHeight: 1.65,
};

const pill: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  position: "absolute",
  top: "8px",
  left: "50%",
  transform: "translateX(-50%)",
  zIndex: 3,
  padding: "5px 12px",
  borderRadius: "20px",
  fontSize: "11px",
  color: "var(--accent-hi)",
  background: "var(--accent-soft)",
  border: "1px solid var(--hair-2)",
  boxShadow: "0 4px 14px rgba(0,0,0,0.24)",
};

const moreButton: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "block",
  width: "calc(100% - 24px)",
  margin: "8px 12px 0",
  padding: "8px 0",
  textAlign: "center",
  borderRadius: "9px",
  border: "1px solid var(--hair)",
  color: "var(--text-3)",
  fontSize: "11.5px",
};

/** The tint an entry wears, by how new it is. `entering` also lifts — the same
 *  `tk-lift` the toasts use, so two live surfaces move the same way. */
function skin(state: "entering" | "fresh" | "rest"): React.CSSProperties {
  if (state === "rest") return {};
  const lit: React.CSSProperties = { background: "var(--accent-soft)" };
  if (state === "fresh") return lit;
  return { ...lit, animation: "tk-lift 260ms cubic-bezier(0.2,0.8,0.2,1)" };
}

/** One entry: who, on what, how long ago, what they did, and what they said. */
function Entry({
  moment,
  state,
  now,
  onOpen,
  onTask,
}: {
  moment: Moment;
  state: "entering" | "fresh" | "rest";
  now: number;
  onOpen: (task: string) => void;
  onTask: (task: string) => void;
}): React.JSX.Element {
  const tone: Tone = DOT[moment.events[0]!.kind] ?? "neutral";
  const spoken = said(moment, SAID_LIMIT);
  return (
    <li
      data-testid="stream-entry"
      data-task={moment.task}
      data-fresh={state}
      style={{ ...skin(state), listStyle: "none", padding: "9px 12px", borderBottom: "1px solid var(--hair)" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "7px", marginBottom: "4px" }}>
        <span
          aria-hidden="true"
          style={{ width: "7px", height: "7px", borderRadius: "50%", background: TONE_FG[tone], flex: "none" }}
        />
        <span style={{ fontSize: "11.5px", color: "var(--text-2)" }} title={moment.actor}>
          {shortActor(moment.actor)}
        </span>
        {/* The card id NARROWS the rail; the entry itself OPENS the card. Two
            buttons side by side and never nested: a button inside a button is
            markup no browser agrees about, and these are two different acts. */}
        <button
          type="button"
          data-testid="stream-follow"
          className="mono"
          title={`follow ${moment.task}`}
          onClick={() => onTask(moment.task)}
          style={{ ...chip(false), color: "var(--accent)", fontSize: "10.5px", padding: "1px 5px" }}
        >
          {moment.task}
        </button>
        <span style={{ flex: "1 1 auto" }} />
        <span className="num" style={{ fontSize: "10.5px", color: "var(--faint)" }}>
          {ago(now - moment.ts)}
        </span>
      </div>
      <button
        type="button"
        data-testid="stream-open"
        aria-label={`open ${moment.task}`}
        onClick={() => onOpen(moment.task)}
        style={body(tone)}
      >
        <span
          style={{
            display: "block",
            fontSize: "12.5px",
            color: "var(--text-2)",
            lineHeight: 1.5,
            letterSpacing: "-0.01em",
          }}
        >
          {roll(moment)}
        </span>
        {spoken.map((line) => (
          <span
            key={line.id}
            data-testid="stream-said"
            style={{ display: "block", fontSize: "12px", color: "var(--text)", marginTop: "5px", lineHeight: 1.5 }}
          >
            {line.text}
          </span>
        ))}
      </button>
    </li>
  );
}

export function Stream(p: StreamProps): React.JSX.Element {
  let day = "";
  return (
    <section
      data-testid="stream"
      style={{ minHeight: 0, display: "flex", flexDirection: "column", background: "var(--pane)", position: "relative" }}
    >
      <div style={head}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "12px", color: "var(--text)", letterSpacing: "-0.02em" }}>Stream</span>
          <span style={{ flex: "1 1 auto" }} />
          {p.task ? (
            <button
              type="button"
              data-testid="stream-unfollow"
              onClick={() => p.onTask(null)}
              style={{ ...chip(true), fontSize: "10.5px" }}
              className="mono"
            >
              {p.task} ✕
            </button>
          ) : null}
          <span className="mono num" style={{ fontSize: "10.5px", color: "var(--text-3)" }}>
            {p.total === null ? "—" : p.total.toLocaleString()}
          </span>
        </div>
        <div style={chips} data-testid="stream-filters">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              data-filter={f.id}
              aria-pressed={p.filter === f.id}
              onClick={() => p.onFilter(f.id)}
              style={chip(p.filter === f.id)}
            >
              {f.name}
            </button>
          ))}
        </div>
      </div>

      {/* The reader's place is never taken. The pill appears only when both
          halves are true — something arrived AND the reader is not at the top —
          so a reader who is watching the top of the list simply sees the rows
          land, with no chrome about it. */}
      {p.waiting > 0 ? (
        <button type="button" data-testid="stream-waiting" onClick={p.onTop} style={pill}>
          ↑ {p.waiting} new
        </button>
      ) : null}

      <div style={list} ref={p.onList} onScroll={p.onScroll} data-testid="stream-list">
        {p.moments.length === 0 ? (
          <div style={note} data-testid="stream-empty">
            {p.total === null
              ? "Nothing has asked the board for the log — this rail is drawn with no client to ask with."
              : p.filter === "all" && p.task === null
                ? "Nothing has happened on this board yet. The first plan, claim or commit appears here the moment it is written."
                : "Nothing here matches. Widen the filter, or stop following that card."}
          </div>
        ) : (
          <ul style={{ margin: 0, padding: 0 }}>
            {p.moments.map((moment) => {
              const label = dayKey(moment.ts) === day ? null : dayLabel(moment.ts, p.now);
              day = dayKey(moment.ts);
              const state = freshness(arrivedAt(moment, p.arrivals), p.at, p.reduced);
              return (
                <li key={moment.key} style={{ listStyle: "none" }}>
                  {label ? (
                    <div style={divider} data-testid="stream-day">
                      {label}
                    </div>
                  ) : null}
                  <ul style={{ margin: 0, padding: 0 }}>
                    <Entry
                      moment={moment}
                      state={state}
                      now={p.now}
                      onOpen={p.onOpen}
                      onTask={p.onTask}
                    />
                  </ul>
                </li>
              );
            })}
            {p.more ? (
              <li style={{ listStyle: "none" }}>
                <button
                  type="button"
                  data-testid="stream-more"
                  disabled={p.loading}
                  onClick={p.onMore}
                  style={moreButton}
                >
                  {p.loading ? "reading…" : "older"}
                </button>
              </li>
            ) : null}
          </ul>
        )}
      </div>
    </section>
  );
}

/** The container: the filter, the scroll position, and ONE timer.
 *
 *  The timer runs only while something is still inside its freshness window and
 *  clears itself the moment nothing is — an idle rail has no clock. It is
 *  restarted by a NEW arrival (`youngest` changes identity), which is the whole
 *  scheduling rule: `useToasts` reached the same shape from the same premise. */
export function StreamRail({
  feed,
  now,
  onOpen,
}: {
  feed: EventFeed;
  /** the board's clock in seconds — App's, so the rail cannot disagree with the page */
  now: number;
  onOpen: (task: string) => void;
}): React.JSX.Element {
  const [filter, setFilter] = useState<Filter>("all");
  const [task, setTask] = useState<string | null>(null);
  const [atTop, setAtTop] = useState(true);
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

  return (
    <Stream
      moments={shown}
      arrivals={feed.arrivals}
      at={at}
      now={now}
      total={feed.total}
      filter={filter}
      onFilter={(next) => {
        setFilter(next);
        box.current?.scrollTo({ top: 0 });
        setAtTop(true);
      }}
      task={task}
      onTask={setTask}
      onOpen={onOpen}
      more={feed.more}
      loading={feed.loading}
      onMore={feed.loadMore}
      waiting={atTop ? 0 : fresh(shown, feed.arrivals, at)}
      onTop={() => {
        box.current?.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
        setAtTop(true);
      }}
      onList={(el) => {
        box.current = el;
      }}
      onScroll={() => setAtTop((box.current?.scrollTop ?? 0) <= 4)}
      reduced={reduced}
    />
  );
}

/** The rail a caller with no wire gets — the harness, and any mount before the
 *  board has answered. Same honesty as `EMPTY_FEED`: nothing read, nothing
 *  claimed, and the empty state says which of the two it is. */
export function EmptyRail({ now }: { now: number }): React.JSX.Element {
  return <StreamRail feed={EMPTY_FEED} now={now} onOpen={() => {}} />;
}
