/* The seven numbers that say how the board stands, in Nova's auto-fit rail.
 *
 * Every one is COUNTED from the payload, never stored and never a delta against
 * a number the client remembers from the last poll: the board derives its own
 * states (`core/graph.py`) and the dashboard's job is to show them, not to keep a
 * second, staler arithmetic beside them.
 *
 * `open` is the only one that comes from `pulse.counts` rather than a group,
 * because a card that is merely open belongs to no attention group at all. */
import type { BoardPayload } from "../../types";

export interface Kpi {
  key: string;
  label: string;
  n: number;
  /** The dot's colour — a token, always. */
  dot: string;
}

/** The rail, in the order it reads: what exists, what is moving, what is waiting. */
export function kpis(board: BoardPayload): Kpi[] {
  const c = board.pulse.counts;
  const g = board.groups;
  return [
    { key: "open", label: "open", n: c.doing + c.ready + c.blocked + c.stalled, dot: "var(--text-3)" },
    { key: "flight", label: "in flight", n: g.doing.length + g.reviewing.length, dot: "var(--accent)" },
    { key: "ready", label: "ready", n: g.take.length, dot: "var(--ok)" },
    { key: "blocked", label: "blocked", n: g.blocked.length, dot: "var(--danger)" },
    { key: "mentions", label: "mentions", n: g.mentions.length, dot: "var(--warn)" },
    { key: "merge", label: "to merge", n: g.merge.length, dot: "var(--ok)" },
    // The count behind the cap, not the tail: the rail is a measure, and
    // `groups.done` only carries the newest 20.
    { key: "closed", label: "closed", n: board.done_total, dot: "var(--text-3)" },
  ];
}

const rail: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
  marginBottom: "20px",
  borderRadius: "16px",
  overflow: "hidden",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
};

const cell: React.CSSProperties = {
  background: "var(--pane)",
  padding: "16px 18px 17px",
  display: "flex",
  flexDirection: "column",
  gap: "12px",
  borderLeft: "1px solid var(--hair)",
  borderTop: "1px solid var(--hair)",
  margin: "-1px 0 0 -1px",
};

export function KpiRail({ board }: { board: BoardPayload }): React.JSX.Element {
  return (
    <div style={rail} data-testid="kpis">
      {kpis(board).map((k) => (
        <div key={k.key} style={cell} data-kpi={k.key}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: k.dot,
                flex: "none",
              }}
            />
            <span style={{ fontSize: "12px", color: "var(--text-2)", letterSpacing: "-0.015em" }}>
              {k.label}
            </span>
          </div>
          <span className="num" style={{ fontSize: "30px", fontWeight: 500, lineHeight: 0.95 }}>
            {k.n}
          </span>
        </div>
      ))}
    </div>
  );
}
