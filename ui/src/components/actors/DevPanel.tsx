/* A dev, opened: the figures, and the window as a pane per date.
 *
 * ── Why this is a full overlay and not a fold ─────────────────────────────
 *
 * The first attempt at this screen revealed the detail IN PLACE, on the tile, on
 * the grounds that the drawer belongs to a CARD and a dev is not one. That
 * reasoning was about routing; the thing on screen is a document with a nested
 * disclosure in it, and inside a 300px grid cell it is unreadable. So it is an
 * overlay, at the width the rows need.
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
 * ── The sub-agent is not a subject here ──────────────────────────────────
 *
 * The version this replaced drew a LANE PER AGENT on a shared time axis and a
 * table of per-agent rows under it. Both are gone, and gone rather than
 * restyled: an agent is a name bound to the RUN of a card, `w1` today is not
 * `w1` yesterday, so a row per agent is a row per label. What the panel draws
 * instead is WHEN the work happened — `Daysheet`, a pane per calendar day with
 * an hour that folds open inside it — over the dev AND its agents together, the
 * one grouping that is a fact about the person.
 *
 * ── Every figure is somebody's, and sums say whose ────────────────────────
 *
 * A dev's totals are dev + agents. When a member cannot say one of its figures
 * (a board one version behind sends `ActorHours` without `closed`/`commits`),
 * `devRows()` returns `null` rather than a sum that silently skipped it, and
 * this file draws the dev's OWN figure and says so. Nothing here invents a
 * total.
 */
import { Overlay } from "../shared/Overlay";
import { Daysheet, daysheet } from "./Daysheet";
import type { SheetDay } from "./Daysheet";
import type { DevRow } from "../monitor/panels";
import type { ReportPayload } from "../../types";

/** The standing spelling for not-knowable in this UI. Never `0`. */
const DASH = "—";

/** The window, grouped by date, over the dev and every agent that ran under it.
 *  One helper so the panel and the harness ask for the same thing. */
export function devDays(
  row: DevRow,
  report: ReportPayload | null,
  titles: Readonly<Record<string, string>> = {},
): SheetDay[] {
  return daysheet(report, [row.dev, ...row.agents.map((a) => a.actor)], titles);
}

/** The distinct cards this dev and its agents touched in the window — a UNION,
 *  not a sum, so it is knowable even when one member cannot say its counts
 *  (`ActorHours.cards` is not optional; `closed` and `commits` are). */
export function devCards(row: DevRow): number {
  const seen = new Set<string>();
  for (const member of row.self ? [row.self, ...row.agents] : row.agents) {
    for (const id of member.carried) seen.add(id);
  }
  return seen.size;
}

export interface DevPanelProps {
  row: DevRow;
  report: ReportPayload | null;
  /** card id → title, for the cards the board can name right now. A session on a
   *  card nobody holds is drawn as its id alone rather than a guess. */
  titles?: Readonly<Record<string, string>> | undefined;
  onOpen: (id: string) => void;
  onClose: () => void;
}

export function DevPanel(props: DevPanelProps): React.JSX.Element {
  return (
    <Overlay onClose={props.onClose} label={props.row.dev} width="min(980px, 100%)">
      <DevDetail {...props} />
    </Overlay>
  );
}

const label: React.CSSProperties = { fontSize: "11px", color: "var(--text-3)" };

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

export function DevDetail({
  row,
  report,
  titles,
  onOpen,
  onClose,
}: DevPanelProps): React.JSX.Element {
  const days = devDays(row, report, titles ?? {});

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
            {`orchestrator · ${row.presence}`}
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
            marginBottom: "14px",
          }}
          data-testid="dev-figures"
        >
          <Figure value={row.worked ?? DASH} label="worked" />
          <Figure value={row.commits === null ? DASH : String(row.commits)} label="commits" />
          <Figure value={String(devCards(row))} label="cards" />
          <Figure
            value={`${row.live} running now`}
            label={row.live === 1 ? "agent on a card" : "agents on a card"}
          />
        </div>
        {row.partial ? (
          <div style={{ ...label, marginBottom: "16px" }} data-testid="dev-partial">
            One member of this dev could not say one of its figures, so nothing above is a sum:
            each figure is this dev&apos;s own, and its agents&apos; are not folded into it.
          </div>
        ) : (
          <div style={{ ...label, marginBottom: "16px" }} data-testid="dev-sum">
            Every figure above is this dev and its agents together, over the report&apos;s window.
          </div>
        )}

        <Daysheet days={days} onOpen={onOpen} />
      </div>
    </>
  );
}

export default DevPanel;
