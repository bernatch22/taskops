/* One card on the kanban — Nova's tile (Taskops Nova.dc.html, the BOARD section).
 *
 * The tile knows NOTHING about groups. Everything that distinguishes a stalled
 * card from a doing one, or a card waiting for review from one being checked,
 * arrives as `chip` + `marker` from `Board.tsx`, which is where the derivation
 * lives. That is deliberate: v1 drew stored statuses straight onto the tile and
 * its teardown (§6) lists exactly what the shortcut hid — "handed over, nobody
 * checking" and "being verified" drew identically. A tile that cannot invent a
 * state cannot lose one either.
 *
 * It is a button, and the only thing it does is open the drawer. There is no
 * write verb on this page and no drag handle: the UI does not move cards. */
import { useState } from "react";

import { ago, initials } from "../../format";
import type { BoardRow } from "../../types";

/** The five ways a thing can be coloured. Nothing here is a literal colour —
 *  the palette lives in theme/tokens.css and nowhere else. */
export type Tone = "accent" | "ok" | "warn" | "danger" | "neutral";

export const TONE_FG: Record<Tone, string> = {
  accent: "var(--accent)",
  ok: "var(--ok)",
  warn: "var(--warn)",
  danger: "var(--danger)",
  neutral: "var(--text-2)",
};

export const TONE_BG: Record<Tone, string> = {
  accent: "var(--accent-soft)",
  ok: "var(--ok-soft)",
  warn: "var(--warn-soft)",
  danger: "var(--danger-soft)",
  neutral: "var(--pane-3)",
};

/** A sub-state, spelled out. The Review column carries three of these and that
 *  is the whole point of merging its three groups into one column. */
export interface Chip {
  label: string;
  tone: Tone;
}

export interface CardTileProps {
  row: BoardRow;
  /** the sub-state badge, when the column has more than one kind of row in it */
  chip?: Chip | undefined;
  /** a coloured spine down the left edge — the danger marker on a stalled card */
  marker?: Tone | undefined;
  /** the reviewer's words, or the submit note; shown verbatim, never summarised */
  note?: string | undefined;
  /** blocked only: the cards this one is waiting for */
  waitingOn?: readonly string[] | undefined;
  onOpen: (id: string) => void;
}

/** p0 is urgent and p3 is idle, so the scale runs hot → cold. */
const PRIORITY: Record<number, Tone> = { 0: "danger", 1: "warn", 2: "accent", 3: "neutral" };

/** The board's own vocabulary, from `schema.py`: "0 urgent … 3 idle".
 *
 *  2 is the DEFAULT every card gets when nobody says otherwise, so it is not
 *  worth a pill on every tile — Nova wraps its priority pill in an `sc-if` for
 *  the same reason. What is left is what somebody chose deliberately. */
const PRIORITY_LABEL: Record<number, string> = { 0: "urgent", 1: "high", 3: "idle" };

/** The mono line at the top right: how long it has been quiet when nobody holds
 *  it, how long the lease has run when somebody does. `quiet_for` is null while
 *  a lease is live — that is the server's own distinction, kept. */
function meta(row: BoardRow): { text: string; tone: Tone } {
  if (row.quiet_for === null) {
    return { text: `${ago(Date.now() / 1000 - row.since)} in`, tone: "neutral" };
  }
  return { text: `quiet ${ago(row.quiet_for)}`, tone: row.assignee ? "warn" : "neutral" };
}

const tile: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "block",
  background: "var(--pane)",
  /* Per-side LONGHANDS, never the `border` shorthand, and React says why out
   * loud: "Updating a style property during rerender (borderColor) when a
   * conflicting property is set (borderLeft) can lead to styling bugs." The
   * hover repaints three sides and the marker owns the fourth, so mixing the
   * shorthand with a per-side one left the border in whichever state React
   * happened to apply last — the grey edge that would not go away. */
  borderStyle: "solid",
  borderWidth: "1px",
  borderColor: "var(--hair)",
  borderRadius: "13px",
  padding: "14px 15px",
  // The design's own easing, not a linear stand-in: `cubic-bezier(0.2,0.8,0.2,1)`
  // overshoots slightly and is what makes the lift feel like a lift.
  transition: "all 150ms cubic-bezier(0.2, 0.8, 0.2, 1)",
};

/** `all: unset` on a button removes the focus ring with everything else, so the
 *  design re-adds one and so must we — a board you can tab through is the whole
 *  reason these are buttons and not divs. Offset outward, because the tile has
 *  no `overflow: hidden` to clip it. */
const focusRing: React.CSSProperties = {
  outline: "2px solid var(--accent)",
  outlineOffset: "2px",
};

const pill: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "3px 9px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
};

export function CardTile(props: CardTileProps): React.JSX.Element {
  const { row, chip, marker, note, waitingOn, onOpen } = props;
  const [lift, setLift] = useState(false);
  const [ring, setRing] = useState(false);
  const when = meta(row);
  const who = row.holder ?? row.assignee;
  const style: React.CSSProperties = {
    ...tile,
    /* THE HOVER DOES NOT TOUCH THE BORDER. Asked for three times, and the first
     * two answers were both wrong because I kept hearing "make it a different
     * colour" instead of "stop changing it": Nova's `--accent-line` composites
     * over `--pane` to rgb(63,60,96) and reads grey, and swapping it for solid
     * `--accent` only made the change louder. A border that recolours under the
     * cursor is the complaint, whatever colour it lands on.
     *
     * So the affordance is ELEVATION, which is what the design was already
     * saying with the half of the hover I kept: the 2px rise, plus the glow
     * borrowed from the dots Nova uses to mark a live thing. The tile lifts off
     * the column; its edges stay exactly where they were. The marker bar is
     * untouched by construction now — nothing repaints a border at all. */
    ...(lift
      ? { boxShadow: "0 0 0 3px var(--accent-soft)", transform: "translateY(-2px)" }
      : {}),
    /* The marker owns the left side, always — hover or not, there is no longer
     * anything competing for it. */
    ...(marker ? { borderLeftWidth: "3px", borderLeftColor: TONE_FG[marker] } : {}),
    ...(ring ? focusRing : {}),
  };

  return (
    <button
      type="button"
      style={style}
      data-testid="tile"
      data-card={row.id}
      onClick={() => onOpen(row.id)}
      onMouseEnter={() => setLift(true)}
      onMouseLeave={() => setLift(false)}
      onFocus={() => {
        setLift(true);
        setRing(true);
      }}
      onBlur={() => {
        setLift(false);
        setRing(false);
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "9px" }}>
        <span className="mono" style={{ fontSize: "10.5px", color: "var(--text-3)" }}>
          {row.id}
        </span>
        <span className="mono" style={{ fontSize: "10.5px", color: TONE_FG[when.tone] }}>
          {when.text}
        </span>
      </div>

      {chip ? (
        <div style={{ marginBottom: "9px" }}>
          <span
            data-testid="chip"
            style={{ ...pill, color: TONE_FG[chip.tone], background: TONE_BG[chip.tone] }}
          >
            {chip.label}
          </span>
        </div>
      ) : null}

      <div
        style={{ fontSize: "14px", fontWeight: 450, letterSpacing: "-0.025em", lineHeight: 1.35 }}
      >
        {row.title}
      </div>

      {note ? (
        <div style={{ fontSize: "11.5px", color: "var(--text-2)", marginTop: "8px" }}>{note}</div>
      ) : null}

      {waitingOn && waitingOn.length > 0 ? (
        <div
          data-testid="waiting"
          style={{ fontSize: "11.5px", color: "var(--text-3)", marginTop: "8px" }}
        >
          waiting on{" "}
          {waitingOn.map((id) => (
            <span key={id} className="mono" style={{ color: "var(--text-2)", marginRight: "6px" }}>
              {id}
            </span>
          ))}
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "8px",
          marginTop: "13px",
        }}
      >
        <div style={{ display: "flex", gap: "5px", flexWrap: "wrap", minWidth: 0 }}>
          {row.labels.map((label) => (
            <span key={label} style={{ ...pill, color: "var(--text-2)", background: "var(--pane-3)" }}>
              {label}
            </span>
          ))}
          {/* Nova draws priority as a pill of TEXT beside the labels, not as a
              dot — a 7px disc in a row of worded pills says "something is
              coloured here" and nothing about which. The geometry is the
              design's, verbatim; the colour follows the priority instead of
              Nova's flat accent, because a board whose p0 and p3 read alike
              would need the reader to hover to find the urgent one. */}
          {PRIORITY_LABEL[row.priority] ? (
            <span
              data-testid="priority"
              title={`priority ${row.priority}`}
              style={{
                ...pill,
                color: TONE_FG[PRIORITY[row.priority] ?? "neutral"],
                background: TONE_BG[PRIORITY[row.priority] ?? "neutral"],
              }}
            >
              {PRIORITY_LABEL[row.priority]}
            </span>
          ) : null}
        </div>
        {who ? (
          <span
            title={who}
            style={{
              width: "23px",
              height: "23px",
              borderRadius: "50%",
              flex: "none",
              display: "grid",
              placeItems: "center",
              fontSize: "9.5px",
              /* The disc upcases; `initials()` returns the actor's own case. */
              textTransform: "uppercase",
              background: row.holder ? "var(--accent-soft)" : "var(--pane-3)",
              color: row.holder ? "var(--accent-hi)" : "var(--text-3)",
            }}
          >
            {initials(who)}
          </span>
        ) : null}
      </div>
    </button>
  );
}
