/* One line of the board, in Nova's row shape.
 *
 * Deliberately NOT typed against `BoardRow`: the nine groups do not carry the
 * same fields (a mention has no priority, a blocked row has a chain, a changes
 * row has the reviewer's words), and the drawer's `waiting_on` list is not a
 * board row at all. So the row takes what it DRAWS — already resolved to
 * strings by whoever owns the payload — and the page decides what each group
 * means. One shape, many callers; no caller has to own the union.
 *
 * `ago` lives here rather than in the page because it is part of that
 * resolution: every caller of this row has a timestamp and needs the same
 * words for it. */

export type Accent = "ok" | "warn" | "danger" | "neutral";

export interface GroupRowProps {
  /** The card id, shown mono — it is what the reader types into a tool call. */
  id: string;
  /** The headline. A mention row has no card title on an unknown card; the
   *  caller passes the id rather than leaving the line blank. */
  title: string;
  /** The second line: the mention's text, the reviewer's verdict, the chain a
   *  blocked card waits on. "" draws nothing — never an empty row. */
  note: string;
  /** Who it belongs to right now: the live holder, else the assignee. */
  who: string;
  /** Already-worded staleness ("12m ago"), or "". */
  when: string;
  /** 0 urgent … 3 idle. `null` on a row that is not a card. */
  priority: number | null;
  accent: Accent;
  onOpen: (id: string) => void;
}

/** The pair (line, wash) for an accent. `neutral` is text-3 on the pane's own
 *  third step, so nine panes do not read as nine alarms. */
export function accentInk(accent: Accent): { ink: string; wash: string } {
  if (accent === "neutral") return { ink: "var(--text-3)", wash: "var(--pane-3)" };
  return { ink: `var(--${accent})`, wash: `var(--${accent}-soft)` };
}

/** Seconds → the words the vanilla page used, so the dashboard and the tool
 *  results say the same thing about the same card. */
export function ago(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`;
}

const row: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  gap: "12px",
  alignItems: "center",
  padding: "9px 10px",
  borderRadius: "10px",
  width: "100%",
  transition: "background 130ms",
};

const titleText: React.CSSProperties = {
  fontSize: "13.5px",
  fontWeight: 450,
  letterSpacing: "-0.02em",
  color: "var(--text)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const idText: React.CSSProperties = {
  fontSize: "10.5px",
  color: "var(--faint)",
  marginLeft: "10px",
  flex: "none",
};

const noteText: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  marginTop: "3px",
  marginLeft: "19px",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const pill: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "3px 10px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
  flex: "none",
};

export function GroupRow(props: GroupRowProps): React.JSX.Element {
  const { ink, wash } = accentInk(props.accent);
  return (
    <button
      type="button"
      style={row}
      data-testid="group-row"
      data-id={props.id}
      onClick={() => props.onOpen(props.id)}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--pane-2)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", minWidth: 0 }}>
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: ink,
              marginRight: "12px",
              flex: "none",
            }}
          />
          <span style={titleText}>{props.title}</span>
          <span className="mono" style={idText}>
            {props.id}
          </span>
        </div>
        {props.note ? <div style={noteText}>{props.note}</div> : null}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: "none" }}>
        {props.priority !== null ? (
          <span className="num" style={{ ...pill, background: wash, color: ink }}>
            p{props.priority}
          </span>
        ) : null}
        {props.who ? (
          <span style={{ fontSize: "11px", color: "var(--text-2)", whiteSpace: "nowrap" }}>
            {props.who}
          </span>
        ) : null}
        {props.when ? (
          <span style={{ fontSize: "11px", color: "var(--faint)", whiteSpace: "nowrap" }}>
            {props.when}
          </span>
        ) : null}
      </div>
    </button>
  );
}
