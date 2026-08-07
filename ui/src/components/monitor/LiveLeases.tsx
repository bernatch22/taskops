/* Live leases — Taskops Nova.dc.html lines 176-217, transcribed.
 *
 * The pane the whole "derive, don't write" idea is visible in: `doing` is not a
 * stored status, it is somebody holding a 15-minute lease, and `stalled` is that
 * same card once nobody is renewing it. Both live in ONE pane on purpose
 * (panels.ts) — a lapsed lease is the fact this panel is about.
 *
 * Row geometry is the design's, verbatim: a four-column grid
 * `minmax(150px,1.6fr) minmax(70px,1fr) 72px 78px`, gap 12, padding 14px 20px,
 * a hairline top border, `var(--pane-2)` on hover and an inset accent focus
 * ring — the last four of which are `PaneButton`'s, not re-derived here.
 */
import { ago, shortActor } from "../../format";
import { TONE_BG, TONE_FG } from "../board/CardTile";
import { Pane, PaneEmpty, PaneButton, PaneRow, LIST_CAP } from "./Pane";
import { LEASE_TTL } from "./panels";
import type { BoardRow } from "../../types";
import type { LeaseProc, LiveLeasesProps, Tone } from "./panels";

/* ── the sparkline ────────────────────────────────────────────────────────────
 *
 * WHAT IT PLOTS: one horizontal line, whose HEIGHT is the single real scalar the
 * row has — for a held card the fraction of the 15-minute TTL still unspent, for
 * a stalled one the silence measured against that same TTL, inverted so a longer
 * silence sits lower. Left to right it says nothing, because nothing in the
 * payload varies left to right.
 *
 * WHAT IS MISSING: a per-lease time series. `BoardRow` carries two scalars,
 * `since` and `quiet_for` (panels.ts note 3, hence `LeaseProc.load: null`); the
 * board has no verb that returns a lease's history, so there is no fourth
 * dimension to draw and none is invented. Nova draws its own fifth row flat
 * (`spark(..., flat = true)`, line 1169) — a flat line is the design's own
 * vocabulary for "nothing is moving here", not a substitution.
 *
 * The geometry — viewBox 210x30, the 4 / H-3 clamp, the area closed down to the
 * baseline — is `spark()` at line 1093 of the design. A flat line needs no
 * bezier chain: two points ARE the curve those C-segments would collapse to. */
const W = 210;
const H = 30;

/** `level` is 0..1, 1 = full. Returns the design's two paths. */
function spark(level: number): { line: string; area: string } {
  const y = Math.max(4, Math.min(H - 3, H - 4 - level * (H - 12)));
  const line = `M 0 ${y.toFixed(1)} L ${W} ${y.toFixed(1)}`;
  return { line, area: `${line} L ${W} ${H} L 0 ${H} Z` };
}

/* ── rows ─────────────────────────────────────────────────────────────────── */

/** A held card: the lease is live, and what is worth reading is how much of the
 *  TTL is left. `since` is the lease's `acquired` for a row with a holder. */
function held(row: BoardRow, now: number): LeaseProc {
  const left = Math.max(0, LEASE_TTL - (now - row.since));
  return {
    card: row.id,
    actor: shortActor(row.holder ?? row.assignee),
    title: row.title,
    remain: ago(left),
    remainLabel: "lease left",
    state: "doing",
    tone: "ok",
    load: null,
  };
}

/** A stalled card: an owner, nobody running it. The number that matters flips —
 *  not what is left of a lease (there is none) but how long the silence is. */
function lapsed(row: BoardRow, now: number): LeaseProc {
  const quiet = row.quiet_for ?? now - row.since;
  return {
    card: row.id,
    actor: shortActor(row.assignee || (row.holder ?? "")),
    title: row.title,
    remain: ago(quiet),
    remainLabel: "quiet for",
    state: "stalled",
    tone: "danger",
    load: null,
  };
}

/** The level the flat line sits at, per state — the only real quantity there is.
 *  Kept beside the row builders so the two readings of "the number" (left, and
 *  silence) cannot drift from the two shapes drawn for them. */
function level(p: LeaseProc, row: BoardRow, now: number): number {
  if (p.state === "doing") {
    return Math.max(
      0,
      Math.min(1, (LEASE_TTL - (now - row.since)) / LEASE_TTL),
    );
  }
  const quiet = row.quiet_for ?? now - row.since;
  return Math.max(0, Math.min(1, 1 - quiet / LEASE_TTL));
}

const dot = (tone: Tone): React.CSSProperties => ({
  width: "7px",
  height: "7px",
  borderRadius: "50%",
  background: TONE_FG[tone],
  boxShadow: `0 0 0 3px ${TONE_BG[tone]}`,
  flex: "none",
});

const ellipsis: React.CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

/* ── the empty pane ───────────────────────────────────────────────────────────
 *
 * Drawn in the design's OWN vocabulary for numbers, not as a sentence: the
 * three-cell strip on a hairline, a 21px tabular figure over an 11.5px label,
 * cells split by `border-left` — the same shape Throughput's totals row uses
 * (design lines 285-296). A paragraph of grey text on a designed surface reads
 * as a placeholder somebody forgot to finish, which is exactly what it was.
 *
 * The figures carry tone where tone means something: ready is what you can act
 * on, blocked is what is stuck. Closed stays neutral — it is history, not a
 * call to do anything. */
const figure: React.CSSProperties = { fontSize: "21px", fontWeight: 500, lineHeight: 1 };
const figureLabel: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  marginTop: "3px",
};

export function LiveLeases({
  doing,
  stalled,
  now,
  onOpen,
  standing,
}: LiveLeasesProps): React.JSX.Element {
  const rows: { row: BoardRow; p: LeaseProc }[] = [
    ...doing.map((row) => ({ row, p: held(row, now) })),
    ...stalled.map((row) => ({ row, p: lapsed(row, now) })),
  ];

  return (
    <Pane
      testId="pane-leases"
      title="Live leases"
      subtitle="15-minute TTL, renewed on every call. A dead process is a lapsing lease."
      aside={
        <span style={{ fontSize: "11.5px", color: "var(--text-3)" }}>
          {`${doing.length} healthy · ${stalled.length} lapsed`}
        </span>
      }
    >
      {rows.length === 0 ? (
        <>
          <PaneEmpty>Nobody holds a lease right now.</PaneEmpty>
          <div
            data-testid="standing"
            style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)" }}
          >
            <PaneRow>
              <div className="num" style={{ ...figure, color: TONE_FG.ok }}>
                {standing.ready}
              </div>
              <div style={figureLabel}>ready to pick up</div>
            </PaneRow>
            <PaneRow style={{ borderLeft: "1px solid var(--hair)" }}>
              <div
                className="num"
                style={{
                  ...figure,
                  ...(standing.blocked > 0 ? { color: TONE_FG.danger } : {}),
                }}
              >
                {standing.blocked}
              </div>
              <div style={figureLabel}>blocked</div>
            </PaneRow>
            <PaneRow style={{ borderLeft: "1px solid var(--hair)" }}>
              <div className="num" style={figure}>
                {standing.closed}
              </div>
              <div style={figureLabel}>closed this chapter</div>
            </PaneRow>
          </div>
        </>
      ) : (
        <div style={LIST_CAP}>
          {rows.map(({ row, p }) => {
            /* Derived from the card id, never from the row's index: several rows
             * render at once and an SVG id collides DOCUMENT-wide, so two panes
             * sharing an index would silently paint one gradient over the other. */
            const gradId = `tk-lease-grad-${p.card}`;
            const s = spark(level(p, row, now));
            return (
              <PaneButton
                key={p.card}
                testId="lease-row"
                cardId={p.card}
                onOpen={onOpen}
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "minmax(150px, 1.6fr) minmax(70px, 1fr) 72px 78px",
                  gap: "12px",
                  alignItems: "center",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "11px",
                    }}
                  >
                    <span style={dot(p.tone)} />
                    <span
                      style={{
                        fontSize: "14.5px",
                        fontWeight: 450,
                        letterSpacing: "-0.02em",
                        ...ellipsis,
                      }}
                    >
                      {p.title}
                    </span>
                  </div>
                  <div
                    className="mono"
                    style={{
                      fontSize: "11px",
                      color: "var(--text-3)",
                      marginTop: "5px",
                      paddingLeft: "18px",
                      ...ellipsis,
                    }}
                  >
                    {`${p.card} → ${p.actor}`}
                  </div>
                </div>
                <div style={{ minWidth: 0 }}>
                  <svg
                    viewBox={`0 0 ${W} ${H}`}
                    width="100%"
                    height={H}
                    preserveAspectRatio="none"
                    style={{ display: "block", overflow: "visible" }}
                  >
                    <defs>
                      <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                        <stop
                          offset="0%"
                          stopColor={TONE_FG[p.tone]}
                          stopOpacity="0.28"
                        />
                        <stop
                          offset="100%"
                          stopColor={TONE_FG[p.tone]}
                          stopOpacity="0"
                        />
                      </linearGradient>
                    </defs>
                    <path d={s.area} fill={`url(#${gradId})`} />
                    <path
                      d={s.line}
                      fill="none"
                      stroke={TONE_FG[p.tone]}
                      strokeWidth="1.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div
                    className="mono num"
                    style={{ fontSize: "13.5px", fontWeight: 500 }}
                  >
                    {p.remain}
                  </div>
                  <div
                    style={{
                      fontSize: "10.5px",
                      color: "var(--text-3)",
                      marginTop: "2px",
                    }}
                  >
                    {p.remainLabel}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span
                    style={{
                      fontSize: "11px",
                      padding: "4px 11px",
                      borderRadius: "20px",
                      background: TONE_BG[p.tone],
                      color: TONE_FG[p.tone],
                      letterSpacing: "-0.01em",
                    }}
                  >
                    {p.state}
                  </span>
                </div>
              </PaneButton>
            );
          })}
        </div>
      )}
    </Pane>
  );
}
