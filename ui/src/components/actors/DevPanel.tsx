/* A dev, opened: the drawn timesheet, the figures, and its agents as rows.
 *
 * ── Why this is a full overlay and not a fold ─────────────────────────────
 *
 * The first attempt at this screen revealed the detail IN PLACE, on the tile,
 * on the grounds that the drawer belongs to a CARD and a dev is not one. That
 * reasoning was about routing and the thing on screen is a DRAWING: lanes on a
 * shared time axis, one per agent, which inside a 300px grid cell is an axis
 * nobody can read. So it is an overlay, at the width a time axis needs.
 *
 * It REUSES `shared/Overlay` — the portal, the scrim, and the one `overlayStack`
 * that owns Escape. There is deliberately no second implementation of any of
 * that: a second keydown listener is the exact bug `overlayStack.ts` exists to
 * prevent, and two piles that each think they are the top-most one close the
 * wrong panel. The only thing this panel asked the overlay for is a `width`.
 *
 * ── The split is the dossier's split, for the dossier's reason ────────────
 *
 * `DevPanel` is the portal and renders NOTHING under `react-dom/server`;
 * `DevDetail` is the whole document and renders anywhere. That is what lets the
 * headless harness read the same tree a browser draws — the same seam
 * `Drawer` / `Dossier` was built on (CLAUDE.md, "the dashboard is built").
 *
 * ── Every figure is somebody's, and sums say whose ────────────────────────
 *
 * A dev's totals are dev + agents. When a member cannot say one of its figures
 * (a board one version behind sends `ActorHours` without `closed`/`commits`),
 * `devRows()` returns `null` rather than a sum that silently skipped it, and
 * this file draws the dev's OWN figure and says the agents' are counted
 * separately. Nothing here invents a total.
 */
import { TONE_BG, TONE_FG } from "../board/CardTile";
import { Overlay } from "../shared/Overlay";
import { PaneRow } from "../monitor/Pane";
import { Timesheet, timesheet } from "./Timesheet";
import type { TimesheetDay } from "./Timesheet";
import type { ActorRow, DevRow } from "../monitor/panels";
import type { ReportPayload } from "../../types";

/** The standing spelling for not-knowable in this UI. Never `0`. */
const DASH = "—";

/** Agent rows drawn in the detail. Beyond it the panel says how many more
 *  rather than truncating silently — the pattern `done_total` set. */
export const AGENT_ROWS = 24;

/** The lanes a dev's timesheet draws: its own, then its agents', in the order
 *  `devRows()` put them. One helper so the panel and the harness ask for the
 *  same thing. */
export function devDays(row: DevRow, report: ReportPayload | null): TimesheetDay[] {
  return timesheet(report, [row.dev, ...row.agents.map((a) => a.actor)]);
}

export interface DevPanelProps {
  row: DevRow;
  report: ReportPayload | null;
  onOpen: (id: string) => void;
  onClose: () => void;
}

export function DevPanel(props: DevPanelProps): React.JSX.Element {
  return (
    <Overlay onClose={props.onClose} label={props.row.dev} width="min(1180px, 100%)">
      <DevDetail {...props} />
    </Overlay>
  );
}

const label: React.CSSProperties = { fontSize: "11px", color: "var(--text-3)" };

const clip: React.CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

function Figure({ value, label: text }: { value: string; label: string }): React.JSX.Element {
  return (
    <div>
      <div className="num" style={{ fontSize: "19px", fontWeight: 500 }}>
        {value}
      </div>
      <div style={{ ...label, marginTop: "2px" }}>{text}</div>
    </div>
  );
}

/** One agent, as a ROW — not a tile. A tile per ephemeral sub-agent is what
 *  this card is undoing. */
function AgentRow({
  row,
  onOpen,
}: {
  row: ActorRow;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const card = row.card;
  return (
    <div
      data-testid="dev-agent"
      data-actor={row.actor}
      data-state={row.state ?? ""}
      style={{
        display: "grid",
        gridTemplateColumns: "180px 84px 1fr 60px 60px 74px",
        gap: "10px",
        alignItems: "center",
        padding: "8px 0",
        borderTop: "1px solid var(--hair)",
        fontSize: "12px",
      }}
    >
      <span className="mono" style={{ ...clip, fontSize: "11.5px" }} title={row.actor}>
        {row.actor}
      </span>
      {row.state ? (
        <span
          data-testid="dev-agent-state"
          style={{
            fontSize: "10.5px",
            padding: "2px 9px",
            borderRadius: "20px",
            background: TONE_BG[row.tone],
            color: TONE_FG[row.tone],
            justifySelf: "start",
          }}
        >
          {row.state}
        </span>
      ) : (
        <span style={label}>{row.role}</span>
      )}
      {card ? (
        <button
          type="button"
          data-testid="dev-agent-card"
          data-card={card.id}
          onClick={() => onOpen(card.id)}
          style={{ all: "unset", cursor: "pointer", minWidth: 0, ...clip }}
        >
          <span className="mono" style={{ color: "var(--accent)", fontSize: "11.5px" }}>
            {card.id}
          </span>
          <span style={{ color: "var(--text-2)" }}>{` ${card.title}`}</span>
        </button>
      ) : (
        <span style={{ ...label, ...clip }} data-testid="dev-agent-history">
          {row.carried.length === 0
            ? "on no card in this window"
            : `carried ${row.carried.length} ${row.carried.length === 1 ? "card" : "cards"}`}
        </span>
      )}
      <span className="num" style={{ ...label, textAlign: "right" }}>
        {row.closed === null ? DASH : row.closed}
      </span>
      <span className="num" style={{ ...label, textAlign: "right" }}>
        {row.commits === null ? DASH : row.commits}
      </span>
      <span className="num" style={{ ...label, textAlign: "right" }}>
        {row.worked ?? DASH}
      </span>
    </div>
  );
}

export function DevDetail({ row, report, onOpen, onClose }: DevPanelProps): React.JSX.Element {
  const days = devDays(row, report);
  const shown = row.agents.slice(0, AGENT_ROWS);
  const rest = row.agents.length - shown.length;

  return (
    <>
      <div
        style={{
          padding: "22px 26px 18px",
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: "18px",
          alignItems: "start",
          borderBottom: "1px solid var(--hair)",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h2
            className="mono"
            style={{ margin: "0 0 6px", fontSize: "22px", fontWeight: 500, letterSpacing: "-0.03em" }}
          >
            {row.dev}
          </h2>
          <div style={{ ...label, fontSize: "12px" }} data-testid="dev-presence">
            {`${row.presence} · ran ${row.agents.length} ${row.agents.length === 1 ? "agent" : "agents"} in this window`}
          </div>
        </div>
        <button
          type="button"
          data-testid="close"
          aria-label="Close"
          onClick={onClose}
          style={{
            all: "unset",
            boxSizing: "border-box",
            cursor: "pointer",
            width: "34px",
            height: "34px",
            display: "grid",
            placeItems: "center",
            borderRadius: "11px",
            color: "var(--text-3)",
            fontSize: "17px",
            background: "var(--pane-2)",
          }}
        >
          ×
        </button>
      </div>

      <div style={{ overflowY: "auto", padding: "20px 26px 26px" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
            gap: "14px",
            marginBottom: "18px",
          }}
          data-testid="dev-figures"
        >
          <Figure value={row.closed === null ? DASH : String(row.closed)} label="closed" />
          <Figure value={row.commits === null ? DASH : String(row.commits)} label="commits" />
          <Figure value={row.worked ?? DASH} label="worked" />
          <Figure value={String(row.agents.length)} label="agents ran" />
          <Figure value={String(row.live)} label="on a card now" />
        </div>
        {row.partial ? (
          <div style={{ ...label, marginBottom: "16px" }} data-testid="dev-partial">
            One member of this dev could not say one of its figures, so nothing above is a sum:
            each figure is this dev&apos;s own, and its agents&apos; are counted separately in the
            rows below.
          </div>
        ) : (
          <div style={{ ...label, marginBottom: "16px" }} data-testid="dev-sum">
            Every figure above is this dev and its agents together, over the report&apos;s window.
          </div>
        )}

        <h3 style={{ margin: "0 0 4px", fontSize: "14px", fontWeight: 500 }}>
          Timesheet — one lane per agent, one axis
        </h3>
        <div style={{ ...label, marginBottom: "6px" }}>
          Two lanes that overlap were working at the same time; the space between blocks is
          wall-clock nobody counted.
        </div>
        <Timesheet days={days} onOpen={onOpen} />

        <h3 style={{ margin: "22px 0 2px", fontSize: "14px", fontWeight: 500 }}>
          Agents — live lease first, then most recently seen
        </h3>
        {row.agents.length === 0 ? (
          <div style={label} data-testid="dev-agents-none">
            This dev ran no agent in the window — the hours above are its own.
          </div>
        ) : (
          <div data-testid="dev-agents">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "180px 84px 1fr 60px 60px 74px",
                gap: "10px",
                ...label,
                paddingBottom: "4px",
              }}
            >
              <span>agent</span>
              <span>state</span>
              <span>card</span>
              <span style={{ textAlign: "right" }}>closed</span>
              <span style={{ textAlign: "right" }}>commits</span>
              <span style={{ textAlign: "right" }}>worked</span>
            </div>
            {shown.map((agent) => (
              <AgentRow key={agent.actor} row={agent} onOpen={onOpen} />
            ))}
            {rest > 0 ? (
              <PaneRow pad="9px 0">
                <span style={label} data-testid="dev-agents-more">
                  {`${rest} more ${rest === 1 ? "agent" : "agents"} not drawn — the figures above already count ${row.agents.length}.`}
                </span>
              </PaneRow>
            ) : null}
          </div>
        )}
      </div>
    </>
  );
}

export default DevPanel;
