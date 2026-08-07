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

/** "agent:berna/w5" → "w5", "dev:berna" → "berna". The board's actor strings are
 *  role-qualified; the avatar is not the place to re-read the role. */
export function shortActor(actor: string): string {
  const tail = actor.split("/").pop() ?? actor;
  return tail.split(":").pop() ?? tail;
}

export function initials(actor: string): string {
  return shortActor(actor).slice(0, 2).toUpperCase();
}

export function ago(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 90) return `${s}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 172800) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

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
  border: "1px solid var(--hair)",
  borderRadius: "13px",
  padding: "14px 15px",
  transition: "border-color 150ms, transform 150ms",
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
  const when = meta(row);
  const who = row.holder ?? row.assignee;
  const style: React.CSSProperties = {
    ...tile,
    ...(marker ? { borderLeft: `3px solid ${TONE_FG[marker]}` } : {}),
    ...(lift ? { borderColor: "var(--accent-line)", transform: "translateY(-2px)" } : {}),
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
      onFocus={() => setLift(true)}
      onBlur={() => setLift(false)}
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

      <div style={{ fontSize: "14px", letterSpacing: "-0.025em", lineHeight: 1.35 }}>
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
          <span
            data-testid="priority"
            title={`priority ${row.priority}`}
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              alignSelf: "center",
              flex: "none",
              background: TONE_FG[PRIORITY[row.priority] ?? "neutral"],
            }}
          />
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
