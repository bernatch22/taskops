/* The dev's work, as a pane per DATE with an hour that folds open inside it.
 *
 * ── What this replaced, and why it is a redesign and not a restyle ─────────
 *
 * The panel that stood here drew a LANE PER AGENT on one wall-clock axis, and
 * the page under it carried an "Hours worked today" panel of bars, one per
 * actor. Both were built to compare actors against each other, and both are
 * deleted rather than adjusted: an agent is a name bound to the RUN of a card
 * (this chapter's own goal), `w1` today is not `w1` yesterday, so comparing two
 * agents compares two labels. A bar chart exists to compare things; there was
 * nothing here to compare.
 *
 * What is left is the one question this panel can answer honestly: WHEN did the
 * work happen. So the window is grouped by calendar day — one pane each, newest
 * FIRST and only the newest open — and inside a day the hours it actually spans
 * are rows, each folding open to the sessions it holds. Every session is the
 * dev's or one of its agents': the sub-agent is not a subject here, it is the
 * name on a session at most.
 *
 * ── An hour is a bucket, never a knife ────────────────────────────────────
 *
 * A SESSION BELONGS TO THE HOUR ITS START FALLS IN, and one that crosses an
 * hour boundary is NOT SPLIT. Splitting it would invent intervals the
 * arithmetic never produced: `core/hours.py::sessions` is the list `spent()`
 * folds into the totals, and a 10:38–11:12 run cut in two would make this
 * screen the only place a 22-minute and a 12-minute interval exist. The hour a
 * session is filed under is a heading; the session is the fact.
 *
 * ── The empty hour is the information ─────────────────────────────────────
 *
 * An hour inside the day's span with nothing counted IS DRAWN and says so. That
 * is where the dropped gaps are — a gap longer than 30 minutes is dropped
 * whole, never capped — and it is why a day's total is smaller than its last
 * session minus its first. Skipping those rows would leave the arithmetic
 * looking wrong with the explanation removed.
 *
 * ── Nothing here is computed twice ────────────────────────────────────────
 *
 * The sessions are `ActorHours.sessions`, straight off `verbs/report.py`. This
 * file buckets and adds them; it decides no interval. The one wording it owns
 * is `span()`, because a day's total across a dev AND its agents is an addition
 * the server never made — every per-actor total on the wire is already
 * formatted by `core/hours.py::human` and is never re-derived.
 */
import { useState } from "react";

import { PaneRow } from "../monitor/Pane";
import type { ActorSession, ReportPayload } from "../../types";

/** One counted interval, with the actor it belongs to and the card's title when
 *  the board could name it. `title` is `null`, never `""`: the payload carries
 *  titles only for cards somebody holds right now (`ActorsProps`), and an
 *  unnamed card is drawn as its id alone. */
export interface SheetSession extends ActorSession {
  actor: string;
  title: string | null;
}

/** One hour of one day. Present even with nothing in it — see the docstring. */
export interface SheetHour {
  /** `<day> <slot>` — the slot, not the hour NUMBER: a pane whose first
   *  session opened at 23:5x the previous local day (the edge rule, below) can
   *  hold two rows labelled `23:00`, and they must fold apart */
  key: string;
  hour: number;
  /** `09:00` */
  label: string;
  seconds: number;
  sessions: SheetSession[];
  /** the distinct cards touched in this hour, in first-seen order */
  cards: string[];
}

/** One calendar day with something counted in it. A day with nothing is not in
 *  the list at all — an empty pane is a row that says nothing. */
export interface SheetDay {
  day: string;
  /** `Friday 8 August` */
  label: string;
  seconds: number;
  /** every hour from the first with a session to the last, so the SHAPE of the
   *  day is visible; never 00–23. When the edge rule filed a midnight-crossing
   *  session here, the first rows are the closing hours of the previous local
   *  day, and their labels say so (`23:00` above `00:00`) */
  hours: SheetHour[];
  /** wall-clock between two sessions that nobody counted */
  gaps: number;
  dropped: number;
  /** the payload truncated somebody's sessions (`verbs/report.py::SESSIONS`) */
  capped: boolean;
}

/** `2h 40m` / `35m` / `—`, the wording of `core/hours.py::human`, for the sums
 *  this screen performs and the server never did. */
export function span(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  if (minutes <= 0) return "—";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours && rest) return `${hours}h ${rest}m`;
  return hours ? `${hours}h` : `${rest}m`;
}

/** `09:12` — real wall-clock, in the reader's own zone. */
export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** `2026-08-08` → `Friday 8 August`. Built from the parts rather than
 *  `new Date(iso)`, which parses a bare date as UTC and prints the day before
 *  it for every reader west of Greenwich. */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

/** The report → one pane per day, NEWEST FIRST.
 *
 *  `report.days` arrives oldest first (`core/hours.py::windows`), and the reader
 *  wants today at the top: the previous panel drew the 7th above the 8th, which
 *  is backwards for a screen somebody opens to see what just happened.
 *
 *  Pure and exported for the reason every fold in this dashboard is: no handler
 *  fires under `react-dom/server`, so a rule left inside a render closure has no
 *  test. */
export function daysheet(
  report: ReportPayload | null,
  actors: readonly string[],
  titles: Readonly<Record<string, string>> = {},
): SheetDay[] {
  const out: SheetDay[] = [];
  for (const day of report?.days ?? []) {
    const all: SheetSession[] = [];
    let capped = false;
    for (const actor of actors) {
      const mine = day.by_actor[actor];
      if (!mine) continue;
      const blocks = mine.sessions ?? [];
      if ((mine.sessions_total ?? blocks.length) > blocks.length) capped = true;
      for (const s of blocks) all.push({ ...s, actor, title: titles[s.task] ?? null });
    }
    if (all.length === 0) continue;
    all.sort((a, b) => a.start - b.start || a.end - b.end);

    /* THE GAPS. Measured against the running LATEST end, not the previous
       session's: a dev and one of its agents working at the same time overlap,
       and reading one after the other would report a negative gap as a positive
       one the moment the shorter session came second. */
    let gaps = 0;
    let dropped = 0;
    let mark = all[0]!.end;
    for (const s of all.slice(1)) {
      if (s.start > mark) {
        gaps += 1;
        dropped += s.start - mark;
      }
      mark = Math.max(mark, s.end);
    }

    /* THE HOUR ROWS — walked by TIMESTAMP, never by hour NUMBER. The server's
       edge rule credits an interval to the day its CLOSING stamp is in
       (core/hours.py), so a session that opens at 23:5x and closes past
       midnight sits in the NEXT day's list — and that day's local hours are
       then not monotone. The loop this replaced, `for (h = firstHour; h <=
       lastHour)`, met such a day and drew 23..23 (one row) or 23..10 (no rows)
       around seventeen counted hours. A SLOT is the local hour's own floor as
       a timestamp: monotone across any midnight, labelled with its wall clock,
       and advanced through its successor's floor so a DST-stretched hour is
       one slot and a skipped one is none. */
    const slotOf = (ts: number): number => {
      const d = new Date(ts * 1000);
      d.setMinutes(0, 0, 0);
      return d.getTime() / 1000;
    };
    const last = slotOf(all[all.length - 1]!.start);
    const hours: SheetHour[] = [];
    for (let slot = slotOf(all[0]!.start); slot <= last; slot = slotOf(slot + 3600)) {
      /* The START decides the bucket, and only the start. */
      const sessions = all.filter((s) => slotOf(s.start) === slot);
      const hour = new Date(slot * 1000).getHours();
      hours.push({
        key: `${day.day} ${slot}`,
        hour,
        label: `${String(hour).padStart(2, "0")}:00`,
        seconds: sessions.reduce((n, s) => n + s.seconds, 0),
        sessions,
        cards: [...new Set(sessions.map((s) => s.task))],
      });
    }

    out.push({
      day: day.day,
      label: dayLabel(day.day),
      seconds: all.reduce((n, s) => n + s.seconds, 0),
      hours,
      gaps,
      dropped,
      capped,
    });
  }
  return out.reverse();
}

/** The rule, in `core/hours.py`'s own words, lifted rather than re-worded: a
 *  second explanation of one computation is a second thing that can go stale. */
export const RULE =
  "The signal is the timestamp of the events themselves. Each interval is credited to the card that CLOSES it — once — and a gap longer than 30 minutes is dropped whole, never capped: nobody knows what happened in that hour.";

/* ── the drawing ──────────────────────────────────────────────────────────── */

const faint: React.CSSProperties = { fontSize: "11px", color: "var(--text-3)" };

const clip: React.CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

/** `all: unset` is the design's own button reset (Pane.tsx); the row grows to
 *  fill so the whole strip is the hit area and not just the glyph. */
const foldButton: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "9px",
  flex: 1,
  minWidth: 0,
};

const arrow: React.CSSProperties = { fontSize: "10px", color: "var(--text-3)", flex: "none" };

/** The indent an hour's label sits at, with or without a fold button, so a full
 *  hour and an empty one line up. */
const GLYPH = "19px";

function Session({
  session,
  onOpen,
}: {
  session: SheetSession;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  return (
    <button
      type="button"
      data-testid="session-row"
      data-card={session.task}
      data-actor={session.actor}
      onClick={() => onOpen(session.task)}
      style={{
        all: "unset",
        cursor: "pointer",
        boxSizing: "border-box",
        width: "100%",
        display: "grid",
        gridTemplateColumns: "124px 56px 1fr",
        gap: "10px",
        alignItems: "baseline",
        padding: `5px 0 5px calc(${GLYPH} + 16px)`,
        fontSize: "11.5px",
      }}
    >
      <span className="num" style={faint}>
        {`${clock(session.start)} – ${clock(session.end)}`}
      </span>
      <span className="num" style={faint}>
        {span(session.seconds)}
      </span>
      <span style={{ ...clip, minWidth: 0 }}>
        <span className="mono" style={{ color: "var(--accent)" }}>
          {session.task}
        </span>
        {session.title === null ? null : (
          <span style={{ color: "var(--text-2)" }}>{` ${session.title}`}</span>
        )}
      </span>
    </button>
  );
}

/** One hour. An hour with nothing counted is drawn with NO fold and NO arrow:
 *  there is nothing behind it, and an arrow glyph that is not a control is the
 *  thing this panel's every fold is a real `<button>` to avoid. */
export function HourRow({
  hour,
  open,
  onFold,
  onOpen,
}: {
  hour: SheetHour;
  open: boolean;
  onFold: () => void;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const empty = hour.sessions.length === 0;
  return (
    <div data-testid="hour-row" data-hour={hour.label} data-empty={empty ? "yes" : "no"}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          padding: "6px 0",
        }}
      >
        {empty ? (
          <span
            className="num"
            style={{ ...faint, flex: 1, minWidth: 0, paddingLeft: `calc(${GLYPH} + 9px)` }}
          >
            {hour.label}
          </span>
        ) : (
          <button
            type="button"
            data-testid="hour-fold"
            aria-expanded={open}
            aria-controls={`hour-body-${hour.key}`}
            onClick={onFold}
            style={foldButton}
          >
            <span className="mono" aria-hidden="true" style={{ ...arrow, width: GLYPH }}>
              {open ? "▾" : "▸"}
            </span>
            <span className="num" style={{ fontSize: "12px", color: "var(--text)" }}>
              {hour.label}
            </span>
          </button>
        )}
        <span
          className="num"
          data-testid="hour-total"
          style={{ ...faint, flex: "none", width: "56px", textAlign: "right" }}
        >
          {span(hour.seconds)}
        </span>
        <span
          data-testid="hour-cards"
          className={empty ? undefined : "mono"}
          style={{ ...faint, flex: "1 1 40%", minWidth: 0, ...clip }}
        >
          {empty ? "nothing counted" : hour.cards.join(" · ")}
        </span>
      </div>
      {open && !empty ? (
        <div id={`hour-body-${hour.key}`}>
          {hour.sessions.map((s) => (
            <Session key={`${s.task}-${s.start}`} session={s} onOpen={onOpen} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** The whole panel. Both folds are VIEW state and remember nothing: not stored,
 *  not a URL, not a preference.
 *
 *  `null` for the day means "nobody has folded anything yet", and then the FIRST
 *  day — the newest — is the open one. Deliberately not seeded with `days[0].day`:
 *  the report is re-sent on every poll and a seeded date would keep pointing at a
 *  day that has rolled over, leaving every pane shut with no explanation. */
export function Daysheet({
  days,
  onOpen,
}: {
  days: readonly SheetDay[];
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const [day, setDay] = useState<string | null>(null);
  const [hour, setHour] = useState<string | null>(null);

  return (
    <div data-testid="daysheet">
      {days.length === 0 ? (
        <div style={faint} data-testid="daysheet-none">
          No counted time in this window — there is nothing to fold open.
        </div>
      ) : (
        days.map((d, i) => {
          const shown = day === null ? i === 0 : day === d.day;
          return (
            <div key={d.day} data-testid="day-pane" data-day={d.day}>
              <PaneRow
                pad="10px 0"
                style={{ display: "flex", alignItems: "baseline", gap: "12px" }}
              >
                <button
                  type="button"
                  data-testid="day-fold"
                  aria-expanded={shown}
                  aria-controls={`day-body-${d.day}`}
                  onClick={() => setDay(shown ? "" : d.day)}
                  style={foldButton}
                >
                  <span className="mono" aria-hidden="true" style={{ ...arrow, width: GLYPH }}>
                    {shown ? "▾" : "▸"}
                  </span>
                  <span style={{ fontSize: "13.5px", fontWeight: 500, letterSpacing: "-0.02em" }}>
                    {d.label}
                  </span>
                </button>
                <span className="num" data-testid="day-total" style={{ ...faint, flex: "none" }}>
                  {span(d.seconds)}
                </span>
              </PaneRow>
              {shown ? (
                <div id={`day-body-${d.day}`} style={{ padding: "6px 0 12px 14px" }}>
                  {d.hours.map((h) => (
                    <HourRow
                      key={h.key}
                      hour={h}
                      open={hour === h.key}
                      onFold={() => setHour(hour === h.key ? null : h.key)}
                      onOpen={onOpen}
                    />
                  ))}
                  <div
                    data-testid="day-dropped"
                    style={{ ...faint, textAlign: "right", paddingTop: "8px" }}
                  >
                    {d.gaps === 0
                      ? "no gap — every minute between the first session and the last was counted"
                      : `${d.gaps} ${d.gaps === 1 ? "gap" : "gaps"} · ${span(d.dropped)} not counted`}
                  </div>
                  {d.capped ? (
                    <div data-testid="day-capped" style={{ ...faint, textAlign: "right" }}>
                      More sessions than one answer carries — the rows are the first of them; the
                      day&apos;s total above is the whole day.
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })
      )}
      <div style={{ ...faint, marginTop: "10px", lineHeight: 1.6 }} data-testid="daysheet-rule">
        {RULE}
      </div>
    </div>
  );
}

export default Daysheet;
