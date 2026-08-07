/* The drawer's shared vocabulary: three surfaces and two colour maps.
 *
 * It is one module rather than a duplicated object in each half because the two
 * halves are one document to the reader. A pill in the header and a pill in the
 * thread that were 3px apart would read as a bug nobody could name, and the state
 * colours in particular MUST match the kanban's — a card that reads "stalled" in
 * danger on the board must not read in warn here, which is why `STATE` maps onto
 * `Tone` (CardTile's five) and never onto colours of its own. */
import type { Tone } from "../board/CardTile";
import type { CardState } from "../../types";

export const STATE: Record<CardState, Tone> = {
  open: "neutral",
  ready: "neutral",
  doing: "ok",
  done: "ok",
  dropped: "neutral",
  blocked: "danger",
  stalled: "danger",
  review: "warn",
  reviewing: "accent",
  changes: "danger",
};

/** p0 is urgent and p3 is idle, so the scale runs hot → cold. Same table as the
 *  tile's, for the same reason `STATE` is. */
export const PRIORITY: Record<number, Tone> = { 0: "danger", 1: "warn", 2: "accent", 3: "neutral" };

export const pill: React.CSSProperties = {
  fontSize: "11px",
  padding: "3px 11px",
  borderRadius: "20px",
};

export const soft: React.CSSProperties = {
  borderRadius: "13px",
  background: "var(--pane-2)",
  padding: "14px 16px",
};

export const label: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--text-3)",
  marginBottom: "9px",
};
