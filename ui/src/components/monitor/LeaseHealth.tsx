/* Lease health — Taskops Nova.dc.html lines 265-295, transcribed.
 *
 * Header padding `18px 20px 4px`. Body `14px 20px 20px`, flex, gap 20: a 104px
 * donut of concentric `<circle r="41" stroke-width="9">` arcs with
 * `stroke-dasharray`/`stroke-dashoffset` and `transform="rotate(-90 50 50)"`, the
 * tracked count absolutely centred over it, and a legend of `HealthSlice` rows
 * (`9px 1fr auto`, gap 11).
 *
 * ── The arithmetic is COMPUTED, never the design's demo numbers ────────────
 *
 * The .dc.html hardcodes `118 258` / `30 346 @ -124` / `30 346 @ -160` for a
 * six-card board it invented. Those add up to nothing in particular. Here the
 * circumference is derived once (2πr, r = 41 ⇒ 257.61) and each arc is
 * `length = C × n / total`, offset by the cumulative length before it. The three
 * arcs therefore close the circle exactly when the buckets partition the tracked
 * cards, which they do by construction below.
 *
 * ── The thresholds, and why these ones ────────────────────────────────────
 *
 * The pane's own subtitle promises that silence is data, so the cutoffs are
 * stated rather than chosen quietly. The unit is the LEASE TTL: `LEASE_TTL` =
 * 900s, the interval `store/live.py` renews on every call. A worker that is alive
 * and working touches the board well inside one TTL, so the TTL is the natural
 * grain — not a round number of minutes somebody liked.
 *
 *   fresh        `quiet_for === null`, or quiet for LESS than one TTL (< 15m).
 *                `null` means a live lease is held, which is the freshest fact
 *                the board has; under one TTL the lease has not even lapsed yet.
 *   going quiet  one to three TTLs (15m–45m). The lease has lapsed and nobody
 *                renewed it. Not yet evidence of a dead process — a long build,
 *                a long read and a long think all look like this.
 *   stale        three TTLs or more (≥ 45m). Three consecutive missed renewals
 *                is where "busy" stops being the likelier explanation.
 *
 * A warning, never a lock: nothing here writes, and a stale card is still just a
 * card somebody may pick up. The board stores no `doing` to contradict.
 */
import { TONE_FG } from "../board/CardTile";
import { Pane, PaneEmpty } from "./Pane";
import type { BoardRow } from "../../types";
import { LEASE_TTL, type HealthSlice, type LeaseHealthProps } from "./panels";

/** The donut's own geometry, from the design: r 41 in a 100×100 viewBox drawn at
 *  104px, 9px stroke. The circumference follows from r — it is never typed in. */
const R = 41;
const CIRCUMFERENCE = 2 * Math.PI * R; // ≈ 257.61

/** The two cutoffs, in seconds. See the header note for why the TTL is the unit. */
const GOING_QUIET = LEASE_TTL; // 900s — one TTL
const STALE = LEASE_TTL * 3; // 2700s — three missed renewals

const label: React.CSSProperties = {
  fontSize: "12.5px",
  color: "var(--text-2)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

/** How quiet ONE row is. `quiet_for` is null exactly while somebody holds the
 *  WORK lease — the server's own distinction, kept rather than flattened to 0.
 *
 *  `live` says the row's liveness is known from the GROUP it arrived in rather
 *  than from its own number, which is the case for a `reviewing` row and the
 *  same floor-vs-exact caveat `LiveLeases.tsx::checked` already documents: the
 *  review lease's `acquired` is not on the wire, and `pulse.py::_row` fills
 *  `quiet_for` from the WORK lease — null only if a worker happens to still be
 *  alive beside the verifier, otherwise `now - card.updated`, which for a card
 *  handed in an hour ago reads `stale` while a verifier is actively holding the
 *  mutex. The board's own definition of the group guarantees the lease IS live;
 *  the payload just cannot say for how much longer. So the group is believed
 *  over the number, and the row is fresh — a floor, never an overstatement,
 *  because there is no bucket fresher than fresh to be wrong towards. Making it
 *  exact is one field in `pulse.py`, not arithmetic this file can do. */
function bucket(row: BoardRow, live = false): 0 | 1 | 2 {
  if (live || row.quiet_for === null || row.quiet_for < GOING_QUIET) return 0;
  return row.quiet_for < STALE ? 1 : 2;
}

/** The three slices, always all three: a bucket with nobody in it is a legend
 *  row reading 0, not a row that vanishes. A disappearing category is how a
 *  reader stops noticing that "stale" exists at all.
 *
 *  Three, not four: a review lease is a HEALTHY lease by Nova's own arithmetic
 *  (3 doing + 1 review + 1 stalled ⇒ '4 healthy · 1 lapsed', design line 1375),
 *  so it needs no bucket of its own — it needs the fresh one. */
function slices(rows: readonly { row: BoardRow; live: boolean }[]): HealthSlice[] {
  const n: [number, number, number] = [0, 0, 0];
  for (const { row, live } of rows) n[bucket(row, live)] += 1;
  return [
    { label: "fresh", n: n[0], tone: "ok" },
    { label: "going quiet", n: n[1], tone: "warn" },
    { label: "stale", n: n[2], tone: "danger" },
  ];
}

/** `stroke-dasharray` + `stroke-dashoffset` for one arc, given what came before
 *  it. A dash of `len` followed by a gap of the whole circumference guarantees
 *  the pattern never repeats around the ring. */
function arc(n: number, total: number, before: number): { array: string; offset: number } {
  const len = total === 0 ? 0 : (CIRCUMFERENCE * n) / total;
  return {
    array: `${len.toFixed(2)} ${CIRCUMFERENCE.toFixed(2)}`,
    offset: -((CIRCUMFERENCE * before) / (total || 1)),
  };
}

/* `now` is in the props and deliberately not read here: `quiet_for` is already a
 * DURATION the server computed against its own clock, not a timestamp to subtract
 * from. Ageing it by the browser's `now` would add the fetch latency and the two
 * clocks' skew to every bucket, and would move cards across a threshold on a
 * re-render with no new data. The panels that read `now` are the ones handed a
 * `since` timestamp. */
export function LeaseHealth({ doing, reviewing, stalled }: LeaseHealthProps): React.JSX.Element {
  /* Both lease kinds and the lapsed ones. `reviewing` carries `live: true` — its
   * liveness is the group's, not its `quiet_for`'s (see `bucket`). */
  const rows = [
    ...doing.map((row) => ({ row, live: false })),
    ...reviewing.map((row) => ({ row, live: true })),
    ...stalled.map((row) => ({ row, live: false })),
  ];
  const parts = slices(rows);
  const tracked = rows.length;

  let before = 0;
  const arcs = parts.map((part) => {
    const drawn = arc(part.n, tracked, before);
    before += part.n;
    return { ...part, ...drawn };
  });

  return (
    <Pane
      testId="pane-health"
      title="Lease health"
      subtitle="Silence is data, not an error."
      headPad="18px 20px 4px"
    >
      {tracked === 0 ? (
        <PaneEmpty>
          Nothing is tracked: no lease is held and no card has an owner nobody is running. An empty
          donut would be the same picture as a broken one.
        </PaneEmpty>
      ) : (
        <div
          style={{ padding: "14px 20px 20px", display: "flex", alignItems: "center", gap: "20px" }}
        >
          <div style={{ position: "relative", flex: "none" }}>
            <svg viewBox="0 0 100 100" width="104" height="104" role="img" aria-label={`${tracked} tracked cards: ${parts.map((p) => `${p.n} ${p.label}`).join(", ")}`}>
              <circle cx="50" cy="50" r={R} fill="none" stroke="var(--hair)" strokeWidth="9" />
              {arcs.map((a) =>
                a.n === 0 ? null : (
                  <circle
                    key={a.label}
                    data-slice={a.label}
                    cx="50"
                    cy="50"
                    r={R}
                    fill="none"
                    stroke={TONE_FG[a.tone]}
                    strokeWidth="9"
                    strokeLinecap="round"
                    strokeDasharray={a.array}
                    strokeDashoffset={a.offset}
                    transform="rotate(-90 50 50)"
                  />
                ),
              )}
            </svg>
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeItems: "center",
                textAlign: "center",
              }}
            >
              <div>
                <div className="num" style={{ fontSize: "22px", fontWeight: 500, lineHeight: 1 }}>
                  {tracked}
                </div>
                <div style={{ fontSize: "10px", color: "var(--text-3)", marginTop: "2px" }}>
                  tracked
                </div>
              </div>
            </div>
          </div>
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              gap: "11px",
              minWidth: 0,
            }}
          >
            {parts.map((part) => (
              <div
                key={part.label}
                data-bucket={part.label}
                style={{
                  display: "grid",
                  gridTemplateColumns: "9px 1fr auto",
                  gap: "11px",
                  alignItems: "center",
                }}
              >
                <span
                  style={{
                    width: "9px",
                    height: "9px",
                    borderRadius: "3px",
                    background: TONE_FG[part.tone],
                  }}
                />
                <span style={label}>{part.label}</span>
                <span className="num" style={{ fontSize: "13px", fontWeight: 500 }}>
                  {part.n}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Pane>
  );
}
