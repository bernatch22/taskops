/* The small shared pieces. Kept together because each is a few lines and none has a life of its
 * own — splitting them into files would be five imports to read one idea. */

import type { Status } from "../contracts";

/* One glyph per status, matching `render/_text.py`'s STATUS_MARK exactly.
 * Matching matters: a person reading `taskops report board` in a terminal and `taskops ui` in a
 * browser must not have to learn two vocabularies for the same eight states. */
export const MARK: Record<Status, string> = {
  backlog: "·", ready: "○", claimed: "◐",
  blocked: "✕", review: "◆", done: "✓", cancelled: "—",
};

/* `claimed` reads "In progress" because that is what it means to somebody looking at the board: a
 * person took the card and is on it. "Claimed" is the ENGINE's word for the lease underneath, and a
 * column heading is not the place to teach it. */
export const COLUMN_LABEL: Record<Status, string> = {
  backlog: "Backlog", ready: "Ready", claimed: "In progress",
  blocked: "Blocked", review: "Review", done: "Done", cancelled: "Cancelled",
};

/* Coarse on purpose, like the Python `ago`: nobody acts differently on 187 versus 190 seconds,
 * and a precise duration invites comparing two of them — which is comparing two machines' clocks
 * that may not agree, since these timestamps come from wherever the agent was. */
export function ago(ts: number): string {
  const seconds = Math.max(0, Date.now() / 1000 - ts);
  if (seconds >= 86400) return `${Math.floor(seconds / 86400)}d ago`;
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ago`;
  return "just now";
}

export function Priority({ value }: { value: number }): JSX.Element {
  /* 0 is urgent. Only 0 and 1 get colour: if every card is coloured, none is. */
  const tone = value === 0 ? "urgent" : value === 1 ? "high" : "normal";
  return <span className={`pri pri-${tone}`} title={`priority ${value}`}>P{value}</span>;
}

export function Actor({ id }: { id: string }): JSX.Element {
  /* `agent:berna/one` renders as `berna/one` with the kind as a marker. The prefix is the same on
   * every row, so showing it eight times per column is eight lines of noise. */
  const [kind, rest] = id.includes(":") ? id.split(":", 2) as [string, string] : ["", id];
  return (
    <span className={`actor actor-${kind || "unknown"}`} title={id}>
      {kind === "agent" ? "◆" : "●"} {rest}
    </span>
  );
}

export function Counts({ up, down, commits }: { up: number; down: number; commits: number }) {
  if (!up && !down && !commits) return null;
  return (
    <span className="counts">
      {up ? <span className="count blocked" title={`waiting on ${up}`}>↑{up}</span> : null}
      {down ? <span className="count blocking" title={`blocking ${down}`}>↓{down}</span> : null}
      {commits ? <span className="count commits" title={`${commits} commits`}>◆{commits}</span> : null}
    </span>
  );
}

/* `5400` -> `1h 30m`, `240` -> `4m`, `0` -> "". Zero prints NOTHING rather than `0m`: a card touched
 * once has no span between its one event and nothing, and `0m` beside it reads as a measurement that
 * came out empty instead of a question that cannot be asked. */
export function spell(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (!minutes) return "";
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours}h${minutes % 60 ? ` ${minutes % 60}m` : ""}` : `${minutes}m`;
}

/* The cards somebody touched, GROUPED BY SITTING — a run of their events with no gap past the cap,
 * which is the log's own evidence that two cards were open at once rather than on the same day.
 *
 * A sitting of one card draws as a plain row; only a group of two or more is worth a frame, because
 * the frame is the CLAIM ("these were alternated between") and putting one around a single card
 * would make the claim about nothing.
 *
 * Paged rather than cut: it used to stop at six with no way to see the rest, so a dev with fifteen
 * cards had nine that did not exist as far as this panel was concerned. The rest is already loaded —
 * "more" costs no request, which is why it is a count and not a fetch.
 */

/* How long is long, as three buckets. A colour scale and not a gradient, because the number is a
 * FLOOR and a smooth ramp would suggest a precision it does not have — three steps say "a while",
 * "most of a session", "hours" and stop there. Derived from the value so no caller can label a row
 * wrong, and the thresholds are the ones the cap makes meaningful: `GAP` is thirty minutes, so an
 * hour is two uninterrupted stretches and three hours is a morning. */
export function heat(seconds: number): string {
  if (seconds >= 3 * 3600) return "heat-hot";
  if (seconds >= 3600) return "heat-warm";
  return "heat-cool";
}
