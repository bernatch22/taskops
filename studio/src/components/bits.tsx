/* The small shared pieces. Kept together because each is a few lines and none has a life of its
 * own — splitting them into files would be five imports to read one idea. */

import type { Status } from "../contracts";

/* One glyph per status, matching `render/_text.py`'s STATUS_MARK exactly.
 * Matching matters: a person reading `taskops report board` in a terminal and the studio in a
 * browser must not have to learn two vocabularies for the same eight states. */
export const MARK: Record<Status, string> = {
  backlog: "·", ready: "○", claimed: "◐", in_progress: "●",
  blocked: "✕", review: "◆", done: "✓", cancelled: "—",
};

export const COLUMN_LABEL: Record<Status, string> = {
  backlog: "Backlog", ready: "Ready", claimed: "Claimed", in_progress: "In progress",
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
