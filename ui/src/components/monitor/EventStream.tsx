/* Event stream — Taskops Nova.dc.html lines 385-412, the foot of the sticky
 * right column.
 *
 * BUILT TO SHAPE, WITH NO VERB BEHIND IT. Nothing streams the log to this
 * client: the client's `RpcVerb` is `board | card | report | mentions | update`,
 * the server's registry is `board · mentions · card · report · plan · assign ·
 * merged · take · update · review · bind`, and `BoardPayload` carries no event
 * list. So `Monitor.tsx` hands this panel `events={[]} total={null}` and always
 * will, until somebody adds the verb. The milestone's rule is layout first, data
 * second: the pane is drawn whole and its empty state NAMES what is missing —
 * dropping a pane for lack of data is what got the previous chapter rolled back.
 *
 * What an `events` verb would have to return is written on tk-4b37dd's close
 * note and repeated at `FIXTURE_EVENTS` below.
 *
 * The entry markup is the design's, transcribed: a `54px 1fr` grid; the
 * timestamp over its relative age, right-aligned; a `--hair` left rule with the
 * 8px dot punched THROUGH it by `box-shadow: 0 0 0 3px var(--pane)` — the ring
 * paints the pane's own background over the rule, so the dot reads as sitting on
 * the line rather than crossing it. `Thread.tsx` already draws that same dot for
 * a single card's history; it is the same picture at board scale.
 *
 * No helper is written here that exists elsewhere: `ago` and `shortActor` come
 * from `format.ts`, and the kind → colour map and the one-phrase body summary
 * are `DOT` and `detail` from `Thread.tsx` — the drawer and this pane read the
 * SAME log, and a second vocabulary for it is exactly the drift `format.ts`'s
 * docstring is the post-mortem of. `DOT` gained an `export` and nothing else.
 *
 * `clock()` is local on purpose: nothing else in the UI renders a wall-clock
 * time (every other surface shows an age), and a one-caller formatter in
 * `format.ts` would invite the next panel to fold its own in. */
import { ago, shortActor } from "../../format";
import { DOT, detail } from "../card/Thread";
import { TONE_BG, TONE_FG } from "../board/CardTile";
import { Pane, PaneEmpty } from "./Pane";
import type { Event } from "../../types";
import type { EventStreamProps } from "./panels";

/** The design's `{{ e.ts }}`: the wall clock, 24h, zero-padded. Seconds are
 *  dropped — the column is 54px wide and the relative age under it is the
 *  precision a reader actually uses. */
function clock(ts: number): string {
  const at = new Date(ts * 1000);
  const two = (n: number): string => String(n).padStart(2, "0");
  return `${two(at.getHours())}:${two(at.getMinutes())}`;
}

/** A FIXTURE. Not board data, never rendered by this component, never reachable
 *  from `Monitor.tsx` — it exists so the entry markup above could be developed
 *  against the shapes `store/log.py` actually appends, and so the smoke harness
 *  can drive a populated pane the day it lands.
 *
 *  The shapes are `core/types.py::Event` verbatim (`id · task · actor · kind ·
 *  body · ts`) with the real `KINDS` vocabulary — created, edited, claimed,
 *  released, status, comment, commit, merged, milestone, submitted, reviewed —
 *  rather than the design's demo strings, so the pill vocabulary and the dot
 *  colours match the log this pane will one day be handed.
 *
 *  That handing-over needs a verb this board does not have. It would have to
 *  return `Event[]` — the stored rows, unmodified, `task` included ("project"
 *  for board-level facts) — ordered by `ts` DESCENDING (newest first: this pane
 *  scrolls down into the past), plus the log's TOTAL length for the counter in
 *  the header. Paging by offset would skip or repeat rows as the log grows
 *  under the reader, so it pages by keyset: `before=<ts>` returns the `limit`
 *  events strictly older than that instant, ties broken by the log's stable
 *  arrival order, and the caller passes the last `ts` it received. */
export const FIXTURE_EVENTS: readonly Event[] = [
  { id: "f1", task: "tk-4b37dd", actor: "dev:berna", kind: "created", body: { card: { title: "Panel: Event stream" } }, ts: 0 },
  { id: "f2", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "claimed", body: { branch: "tk-4b37dd" }, ts: 60 },
  { id: "f3", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "commit", body: { sha: "0000000", subject: "the pane is drawn before the verb exists" }, ts: 120 },
  { id: "f4", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "comment", body: { text: "no verb streams the log yet" }, ts: 180 },
  { id: "f5", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "submitted", body: { note: "handed in" }, ts: 240 },
  { id: "f6", task: "tk-4b37dd", actor: "dev:berna", kind: "reviewed", body: { verdict: "pass", note: "" }, ts: 300 },
  { id: "f7", task: "tk-4b37dd", actor: "dev:berna", kind: "status", body: { to: "done" }, ts: 360 },
  { id: "f8", task: "project", actor: "dev:berna", kind: "milestone", body: { op: "opened" }, ts: 420 },
];

const pill: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "2px 9px",
  borderRadius: "20px",
};

/** One entry, exactly as drawn. `div`s, not buttons: the design gives these rows
 *  no `onClick`, so the seam gives this panel no `onOpen` (panels.ts). */
function Entry({ event, now }: { event: Event; now: number }): React.JSX.Element {
  const tone = DOT[event.kind] ?? "neutral";
  return (
    <div
      data-testid="event-row"
      data-kind={event.kind}
      style={{ display: "grid", gridTemplateColumns: "54px 1fr", gap: "14px", padding: "14px 0" }}
    >
      <div style={{ textAlign: "right", paddingTop: "1px" }}>
        <div className="mono num" style={{ fontSize: "11.5px", color: "var(--text-2)" }}>
          {clock(event.ts)}
        </div>
        <div style={{ fontSize: "10px", color: "var(--faint)", marginTop: "2px" }}>
          {ago(now - event.ts)}
        </div>
      </div>
      <div
        style={{
          minWidth: 0,
          borderLeft: "1px solid var(--hair)",
          paddingLeft: "18px",
          paddingBottom: "2px",
          position: "relative",
        }}
      >
        <span
          style={{
            position: "absolute",
            left: "-4.5px",
            top: "5px",
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: TONE_FG[tone],
            boxShadow: "0 0 0 3px var(--pane)",
          }}
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            flexWrap: "wrap",
            marginBottom: "6px",
          }}
        >
          <span style={{ ...pill, background: TONE_BG[tone], color: TONE_FG[tone] }}>
            {event.kind}
          </span>
          <span style={{ fontSize: "12px", color: "var(--text-3)" }} title={event.actor}>
            {shortActor(event.actor)}
          </span>
          <span className="mono" style={{ fontSize: "10.5px", color: "var(--accent)" }}>
            {event.task}
          </span>
        </div>
        <div
          style={{
            fontSize: "13.5px",
            color: "var(--text-2)",
            lineHeight: 1.55,
            letterSpacing: "-0.015em",
          }}
        >
          {detail(event)}
        </div>
      </div>
    </div>
  );
}

export function EventStream({ events, total, now }: EventStreamProps): React.JSX.Element {
  return (
    <Pane
      testId="pane-events"
      title="Event stream"
      subtitle="Complete, ordered, never truncated."
      headAlign="baseline"
      aside={
        <span className="mono" style={{ fontSize: "11px", color: "var(--text-3)" }}>
          {total === null ? "—" : total.toLocaleString()}
        </span>
      }
    >
      {events.length === 0 ? (
        <PaneEmpty>
          The board exposes no events verb yet — nothing streams the log to this
          page, so there is nothing here to show. This pane is drawn to its full
          shape and left honest rather than dropped. It lights up the day a verb
          returns the log: the stored events newest first, with the log's total
          length for the counter above.
        </PaneEmpty>
      ) : (
        <div
          data-testid="event-stream"
          style={{
            padding: "4px 20px 20px",
            display: "flex",
            flexDirection: "column",
            maxHeight: "620px",
            overflowY: "auto",
          }}
        >
          {events.map((event) => (
            <Entry key={event.id} event={event} now={now} />
          ))}
        </div>
      )}
    </Pane>
  );
}
