/* Throughput — Taskops Nova.dc.html lines 221-263, transcribed.
 *
 * Header padding is `18px 20px 6px` (narrower than the pane default, because the
 * legend sits tight above the chart) and the legend is the `aside`. Body: one SVG
 * `viewBox="0 0 380 130"` at `height=150` with `preserveAspectRatio="none"`, two
 * rounded rects per day, then a `repeat(14, 1fr)` strip of 10px day labels, then
 * a three-cell totals row on a hairline (`PaneRow`).
 *
 * ── THE GAP, named rather than papered over ───────────────────────────────
 *
 * The design draws a THIRD series: a 1.8px `var(--warn)` polyline for reviews,
 * and a "reviews passed" total under it. `ReportDay` (types.ts, from
 * `verbs/report.py::_day`) carries exactly `day`, `by_actor`, `closed` and
 * `commits` — there is NO review count in the payload, at day granularity or any
 * other. `ThroughDay.reviews` is therefore `number | null` and is `null` here for
 * every day (panels.ts, note 2). `null` is not `0`: zero would assert that no
 * review passed on Tuesday, which nothing in the board knows.
 *
 * So the series is kept EVERYWHERE it can be honestly kept and faked nowhere:
 *   · the legend still carries its `--warn` bar — dropping it would hide the gap;
 *   · a footnote under the chart names the missing field in words;
 *   · the polyline is not drawn, because a line through unknown points is an
 *     invented number, and a flat line at 0 is the same invention;
 *   · the "reviews passed" total renders `—`, the standing spelling for
 *     not-knowable in this UI, not `0`.
 * ── What would have to exist for the series to light up ───────────────────
 *
 * Naming it here so it does not have to be rediscovered by reading this file.
 * `verbs/report.py::_day` builds one day's dict from `stores.cache.window(start,
 * end)`; it must gain ONE key beside `closed` and `commits`:
 *
 *     "reviews": sum(1 for e in events
 *                    if e["kind"] == "reviewed"
 *                    and e["body"].get("verdict") == "pass")
 *
 * — the same shape as the `_closed()` predicate right below it, which already
 * counts `kind == "status"` events whose `body["to"] == "done"`. The verdict is
 * an event and never a mutated field (`verbs/review.py` appends `reviewed`,
 * `core/review.py::Standing` folds it), so the day window already contains the
 * rows: nothing new has to be stored and no schema changes. Note it is a count of
 * PASS VERDICTS THAT DAY, not of cards currently standing passed — a card
 * bounced and re-passed contributes on both days, which is what a throughput
 * chart should show and what `closed` already does. Then:
 *
 *   1. `ReportDay` in `ui/src/types.ts` gains `reviews: number`;
 *   2. `ThroughDay.reviews` in `panels.ts` loses its `| null` (panels.ts note 2
 *      is the paper trail and should be struck at the same time);
 *   3. here, `toDays()` passes `d.reviews` through instead of `null`, and
 *      `reviewLine()` starts returning a path on its own — its `some(reviews ===
 *      null)` guard simply stops firing;
 *   4. the "reviews passed" footer cell renders the sum instead of `—`, and the
 *      footnote under the chart comes out.
 *
 * The `—` and the missing polyline are the ONLY two places a number is withheld,
 * so that list is exhaustive.
 *
 * ── The scale ─────────────────────────────────────────────────────────────
 *
 * ONE linear scale for both series, from 0 to the largest value in either. They
 * are both counts of events over the same day, so a second y-axis would be the
 * dual-axis mistake: it lets the drawer choose which series looks bigger. The
 * closes bar is drawn OVER the commits bar at the same x and the same baseline,
 * exactly as the design layers them — closes are a subset of the day's activity,
 * so the taller `--hair-2` bar reads as the ground the `--accent` one stands on.
 */
import { Pane, PaneEmpty, PaneRow } from "./Pane";
import type { ThroughDay, ThroughputProps } from "./panels";

/* The design's own viewBox. Bars are 16 wide with rx 5, 14 to a row. */
const VIEW_W = 380;
const VIEW_H = 130;
const BAR_W = 16;
const SLOT = VIEW_W / 14;
/** The baseline sits a hair off the bottom edge and the tallest bar off the top,
 *  so a full-height bar's rounded cap is not clipped by the viewBox. */
const BASE = 126;
const TOP = 8;

const legendSwatch = (background: string, w: string, h: string): React.CSSProperties => ({
  width: w,
  height: h,
  borderRadius: h === "2px" ? "2px" : "3px",
  background,
  flex: "none",
});

const legendItem: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  display: "flex",
  alignItems: "center",
  gap: "6px",
};

const total: React.CSSProperties = { fontSize: "21px", fontWeight: 500 };
const totalLabel: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  marginTop: "1px",
};

/** `ReportDay` → the design's `throughDays`. `closed` is a list of card ids, so
 *  the bar's height is its LENGTH; `commits` is already a count. */
function toDays(days: ThroughputProps["report"]): ThroughDay[] {
  if (days === null) return [];
  return days.days.map((d) => ({
    day: d.day,
    closes: d.closed.length,
    commits: d.commits,
    reviews: null, // no source — see the header note
  }));
}

/** The shared ceiling. `1` when everything is zero, so an all-quiet fortnight
 *  draws a flat empty axis instead of dividing by zero. */
function ceiling(days: readonly ThroughDay[]): number {
  return Math.max(1, ...days.map((d) => Math.max(d.closes, d.commits)));
}

/** The design's label strip is 14 columns of a 380px-wide pane at 10px — roughly
 *  27px each — and `core/hours.py` labels a day `2026-07-25`. The full string
 *  does not fit and the strip collides into a smear. So the DAY-OF-MONTH is
 *  drawn and the full label is the `title`: the same datum, narrowed to the
 *  column, never a different one. (Said on the card too — this is the one place
 *  the transcription could not be literal.) */
function dayLabel(day: string): string {
  const parts = day.split("-");
  return (parts.length === 3 ? parts[2] : day) ?? day;
}

function barX(i: number): number {
  return i * SLOT + (SLOT - BAR_W) / 2;
}

function barH(value: number, max: number): number {
  return (Math.max(0, value) / max) * (BASE - TOP);
}

/** The `--warn` reviews polyline. Returns `null` while no day carries a review
 *  count, which today is always: nothing is drawn rather than a line at zero.
 *  The moment `ThroughDay.reviews` has a source, this draws it and nothing else
 *  in the file changes. */
function reviewLine(days: readonly ThroughDay[], max: number): string | null {
  if (days.length === 0 || days.some((d) => d.reviews === null)) return null;
  return days
    .map((d, i) => `${i === 0 ? "M" : "L"}${barX(i) + BAR_W / 2} ${BASE - barH(d.reviews ?? 0, max)}`)
    .join(" ");
}

export function Throughput({ report }: ThroughputProps): React.JSX.Element {
  const days = toDays(report);
  const max = ceiling(days);
  const line = reviewLine(days, max);
  const closed = days.reduce((n, d) => n + d.closes, 0);
  const commits = days.reduce((n, d) => n + d.commits, 0);

  const legend = (
    <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
      <span style={legendItem}>
        <span style={legendSwatch("var(--accent)", "8px", "8px")} />
        closes
      </span>
      <span style={legendItem}>
        <span style={legendSwatch("var(--hair-2)", "8px", "8px")} />
        commits
      </span>
      <span style={legendItem} title="no source in the report payload">
        <span style={legendSwatch("var(--warn)", "10px", "2px")} />
        reviews
      </span>
    </div>
  );

  return (
    <Pane
      testId="pane-throughput"
      title="Throughput"
      subtitle="Last 14 days"
      headPad="18px 20px 6px"
      aside={legend}
    >
      {days.length === 0 ? (
        <PaneEmpty>
          No window was asked for. The board call carries <code>hours</code> only when it passed{" "}
          <code>window=</code>; until it does there are no days to draw — that is a missing
          question, not an empty fortnight.
        </PaneEmpty>
      ) : (
        <div style={{ padding: "12px 20px 8px" }}>
          <svg
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            width="100%"
            height="150"
            preserveAspectRatio="none"
            style={{ display: "block" }}
            role="img"
            aria-label={`${closed} cards closed and ${commits} commits over ${days.length} days`}
          >
            {days.map((d, i) => {
              const ch = barH(d.commits, max);
              const kh = barH(d.closes, max);
              return (
                <g key={d.day} data-day={d.day}>
                  <rect
                    x={barX(i)}
                    y={BASE - ch}
                    width={BAR_W}
                    height={ch}
                    rx={5}
                    fill="var(--hair-2)"
                  />
                  <rect
                    x={barX(i)}
                    y={BASE - kh}
                    width={BAR_W}
                    height={kh}
                    rx={5}
                    fill="var(--accent)"
                  />
                </g>
              );
            })}
            {line === null ? null : (
              <path
                d={line}
                fill="none"
                stroke="var(--warn)"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}
          </svg>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(14, 1fr)", marginTop: "4px" }}>
            {days.map((d) => (
              <span
                key={d.day}
                title={d.day}
                style={{ fontSize: "10px", color: "var(--faint)", textAlign: "center" }}
              >
                {dayLabel(d.day)}
              </span>
            ))}
          </div>
          <div style={{ fontSize: "11px", color: "var(--faint)", marginTop: "8px", lineHeight: 1.5 }}>
            The reviews line has no source: a report day carries closed cards and commits, and no
            review count. Kept in the legend, drawn nowhere — empty, not zero.
          </div>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)" }}>
        <PaneRow>
          <div className="num" style={total}>
            {closed}
          </div>
          <div style={totalLabel}>cards closed</div>
        </PaneRow>
        <PaneRow style={{ borderLeft: "1px solid var(--hair)" }}>
          <div className="num" style={total}>
            {commits}
          </div>
          <div style={totalLabel}>commits</div>
        </PaneRow>
        <PaneRow style={{ borderLeft: "1px solid var(--hair)" }}>
          <div className="num" style={total} title="no source in the report payload">
            —
          </div>
          <div style={totalLabel}>reviews passed</div>
        </PaneRow>
      </div>
    </Pane>
  );
}
