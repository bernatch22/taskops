/* Hours — what the board actually cost, over calendar days.
 *
 * This is the one page with a read of its own. `useBoard` owns `board` and the
 * open card and coalesces the feed's signal; `report` is not in that payload
 * (pulse.py only carries it when the call passed window=), and the window and
 * the timezone are this page's own state. So the fetch lives here — local,
 * cancelled on unmount, keyed by the window — and nothing about the socket or
 * the board's fetching is duplicated.
 *
 * What the numbers MEAN (core/hours.py): a stretch between two consecutive
 * events by the same actor counts as worked time only when it is 30 minutes or
 * shorter; a longer gap is DROPPED, never capped. So every figure on this page
 * is a FLOOR — real time with the machine on and nothing recorded is invisible.
 * The subtitle says so, because a number labelled "hours worked" that silently
 * omits an afternoon is worse than no number.
 *
 * The chart (dataviz): magnitude over an ordered time axis is a bar chart. ONE
 * series — seconds worked — so one hue (--accent), no legend, no second y-axis:
 * cards closed rides along as a count in the tooltip and in the strip, never as
 * a second scale on the same frame. Bars are anchored at zero, rounded only at
 * the data end, separated by a surface gap. CSS boxes, no chart library: React
 * is bundled and a chart dependency would be paid for in every page load. */

import { useEffect, useMemo, useState } from "react";

import { RpcError, type Client } from "../client";
import { initials } from "../format";
import type { ActorHours, ReportPayload } from "../types";

/** The three the switcher offers. `report.py::days` clamps 1..90 server-side —
 *  these are inside it, so the label always matches what came back. */
export const WINDOWS = ["7d", "14d", "30d"] as const;
export type HoursWindow = (typeof WINDOWS)[number];

export interface HoursProps {
  client: Client;
}

/** The browser's IANA zone. Never "UTC" by default: the days on this chart are
 *  the human's calendar days, and a hardcoded zone moves every boundary. */
export function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Seconds → `h:mm`. `core/hours.py::human` says "2h 41m" for prose; a column of
 *  figures reads better aligned, so the page formats its own and the two never
 *  disagree because only one of them is ever shown. */
export function clock(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

/** Cards that reached `done` on a day this actor was working them. The payload
 *  attributes closes to the DAY, not to a person (report.py::_day), so this is
 *  the only honest join available: the closing event is one of that actor's
 *  events for that card, that day. Two people on one card that day both see it. */
export function closedBy(report: ReportPayload, actor: string): number {
  const cards = new Set<string>();
  for (const day of report.days) {
    const worked = day.by_actor[actor];
    if (!worked) continue;
    const touched = new Set(worked.cards);
    for (const id of day.closed) if (touched.has(id)) cards.add(id);
  }
  return cards.size;
}

function daySeconds(by: Record<string, ActorHours>): number {
  return Object.values(by).reduce((sum, actor) => sum + actor.seconds, 0);
}

/** `2026-08-07` → `07`. The full date is in the tooltip; the axis only has to
 *  keep the columns apart. */
function tick(day: string): string {
  return day.slice(8) || day;
}

const CHART_H = 150;

export function Hours({ client }: HoursProps): React.JSX.Element {
  const [span, setSpan] = useState<HoursWindow>("7d");
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [error, setError] = useState<RpcError | null>(null);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<number | null>(null);
  const tz = useMemo(browserZone, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const next = await client.rpc<ReportPayload>("report", { window: span, tz });
        if (!alive) return;
        setReport(next);
        setError(null);
      } catch (err) {
        // A refusal names the call that fixes it, so it is shown as written.
        if (alive) setError(err instanceof RpcError ? err : new RpcError("unreachable", String(err)));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [client, span, tz]);

  const days = report?.days ?? [];
  const totals = days.map((d) => daySeconds(d.by_actor));
  const peak = Math.max(1, ...totals);
  const actors = Object.entries(report?.by_actor ?? {}).sort((a, b) => b[1].seconds - a[1].seconds);
  const most = Math.max(1, ...actors.map(([, a]) => a.seconds));
  const step = Math.ceil(days.length / 10); // thin the axis so 30 labels do not collide

  return (
    <div style={page} data-testid="hours">
      <section style={pane}>
        <header style={head}>
          <div>
            <h2 style={title}>Hours</h2>
            <div style={sub}>
              Last {days.length || Number.parseInt(span, 10)} days · {tz} · gaps over 30 min are
              dropped, so every figure is a floor
            </div>
          </div>
          <div style={switcher} role="group" aria-label="window">
            {WINDOWS.map((option) => (
              <button
                key={option}
                type="button"
                data-testid={`window-${option}`}
                aria-pressed={option === span}
                onClick={() => setSpan(option)}
                style={option === span ? tabOn : tabOff}
              >
                {option}
              </button>
            ))}
          </div>
        </header>

        {error ? (
          <div style={{ ...sub, padding: "0 20px 18px", color: "var(--danger)" }}>{error.message}</div>
        ) : null}

        <div style={{ padding: "10px 20px 6px", position: "relative" }}>
          {hover !== null && days[hover] ? (
            <div
              style={{
                ...tip,
                left: `${((hover + 0.5) / Math.max(1, days.length)) * 100}%`,
              }}
            >
              <b>{days[hover].day}</b> · {clock(totals[hover] ?? 0)} h ·{" "}
              {days[hover].closed.length} closed · {days[hover].commits} commits
            </div>
          ) : null}
          <div style={{ display: "flex", alignItems: "flex-end", gap: "2px", height: CHART_H }}>
            {days.map((day, i) => (
              <div
                key={day.day}
                data-testid="hours-bar"
                title={`${day.day} — ${clock(totals[i] ?? 0)}`}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                style={{ ...column, background: hover === i ? "var(--pane-2)" : "transparent" }}
              >
                <div
                  style={{
                    width: "100%",
                    height: `${((totals[i] ?? 0) / peak) * 100}%`,
                    minHeight: (totals[i] ?? 0) > 0 ? "3px" : "0",
                    borderRadius: "4px 4px 0 0",
                    background: hover === i ? "var(--accent-hi)" : "var(--accent)",
                    transition: "height 180ms cubic-bezier(0.2,0.8,0.2,1)",
                  }}
                />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: "2px", marginTop: "5px" }}>
            {days.map((day, i) => (
              <span key={day.day} style={axis}>
                {i % step === 0 ? tick(day.day) : ""}
              </span>
            ))}
          </div>
        </div>

        <div style={strip}>
          <Figure value={clock(report?.total.seconds ?? 0)} label="hours worked" />
          <Figure value={String(report?.total.closed ?? 0)} label="cards closed" />
          <Figure value={String(actors.length)} label="people" />
        </div>
      </section>

      <section style={pane}>
        <header style={{ ...head, paddingBottom: "10px" }}>
          <div>
            <h2 style={title}>By actor</h2>
            <div style={sub}>Who the time belongs to.</div>
          </div>
        </header>
        <div style={{ padding: "0 20px 18px", display: "grid", gap: "10px" }}>
          {actors.length === 0 && !loading ? (
            <div style={sub}>Nobody recorded anything in this window.</div>
          ) : null}
          {actors.map(([actor, worked]) => (
            <div key={actor} data-testid="hours-actor" style={row}>
              <span style={avatar}>{initials(actor)}</span>
              <span style={who}>{actor}</span>
              <span style={track}>
                <span
                  style={{
                    display: "block",
                    height: "100%",
                    width: `${(worked.seconds / most) * 100}%`,
                    borderRadius: "4px",
                    background: "var(--accent)",
                  }}
                />
              </span>
              <span className="mono num" style={figure}>
                {clock(worked.seconds)}
              </span>
              <span
                style={closed}
                title="cards that reached done on a day this actor was working them"
              >
                {report ? closedBy(report, actor) : 0} closed
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Figure({ value, label }: { value: string; label: string }): React.JSX.Element {
  return (
    <div style={{ padding: "14px 20px", borderLeft: "1px solid var(--hair)" }}>
      <div className="num" style={{ fontSize: "21px", fontWeight: 500 }}>
        {value}
      </div>
      <div style={{ fontSize: "11.5px", color: "var(--text-3)", marginTop: "1px" }}>{label}</div>
    </div>
  );
}

const page: React.CSSProperties = { display: "grid", gap: "16px", padding: "16px" };

const pane: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
};

const head: React.CSSProperties = {
  padding: "18px 20px 6px",
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
};

const title: React.CSSProperties = {
  margin: 0,
  fontSize: "16px",
  fontWeight: 500,
  letterSpacing: "-0.03em",
};

const sub: React.CSSProperties = { fontSize: "12.5px", color: "var(--text-3)", marginTop: "3px" };

const switcher: React.CSSProperties = {
  display: "flex",
  gap: "2px",
  padding: "2px",
  borderRadius: "10px",
  background: "var(--pane-3)",
};

const tabOff: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  padding: "5px 12px",
  borderRadius: "8px",
  fontSize: "12px",
  color: "var(--text-3)",
};

const tabOn: React.CSSProperties = {
  ...tabOff,
  background: "var(--pane)",
  color: "var(--accent-hi)",
  boxShadow: "0 1px 2px rgba(0,0,0,0.18)",
};

const column: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  height: "100%",
  display: "flex",
  alignItems: "flex-end",
  borderRadius: "5px 5px 0 0",
  outline: "none",
  cursor: "default",
};

const axis: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  textAlign: "center",
  fontSize: "10px",
  color: "var(--faint)",
};

const tip: React.CSSProperties = {
  position: "absolute",
  top: 0,
  transform: "translateX(-50%)",
  whiteSpace: "nowrap",
  padding: "5px 10px",
  borderRadius: "8px",
  background: "var(--pane-3)",
  border: "1px solid var(--hair-2)",
  color: "var(--text-2)",
  fontSize: "11.5px",
  pointerEvents: "none",
  zIndex: 2,
};

const strip: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, 1fr)",
  borderTop: "1px solid var(--hair)",
};

const row: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "24px minmax(0, 1fr) minmax(0, 2fr) auto auto",
  gap: "12px",
  alignItems: "center",
};

const avatar: React.CSSProperties = {
  width: "24px",
  height: "24px",
  borderRadius: "8px",
  display: "grid",
  placeItems: "center",
  background: "var(--accent-soft)",
  border: "1px solid var(--accent-line)",
  color: "var(--accent-hi)",
  fontSize: "10px",
  /* Lowercase, unlike the round discs in the chrome and on the tiles: this glyph
   * pair sits inches from the full actor string it abbreviates ("w6" next to
   * "agent:berna/w6"), and a shouted "W6" beside a lowercase name reads as two
   * different identifiers. `initials()` hands over the actor's own case; the case
   * is each site's to choose. */
  textTransform: "lowercase",
};

const who: React.CSSProperties = {
  fontSize: "12.5px",
  color: "var(--text-2)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const track: React.CSSProperties = {
  height: "8px",
  borderRadius: "4px",
  background: "var(--hair)",
  overflow: "hidden",
};

const figure: React.CSSProperties = { fontSize: "13px", fontWeight: 500, color: "var(--text)" };

const closed: React.CSSProperties = { fontSize: "11.5px", color: "var(--text-3)" };
