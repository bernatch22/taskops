/* Event stream — Taskops Nova.dc.html lines 385-412, the foot of the sticky
 * right column.
 *
 * IT WAS BUILT TO SHAPE WITH NO VERB BEHIND IT, and for a whole chapter it drew
 * an empty state naming what was missing rather than being dropped. `events` is
 * now a verb (`verbs/events.py`) and this is the pane reading it.
 *
 * TWO EXPORTS, ONE PICTURE, and the split is the seam that keeps this file
 * testable — the same one `Dossier` beside `Drawer` exists for:
 *
 *   · `EventStream` is PURE. Rows in, markup out, no client, no effect. It
 *     renders under `react-dom/server` with no browser and no wire, which is
 *     what lets the smoke harness prove the entry markup rather than only the
 *     empty state.
 *   · `EventStreamPane` is the container: it holds the client and `useEvents`,
 *     and it is the only part of this pane that cannot be rendered headlessly.
 *     `client={null}` is honest and supported — nothing to ask, nothing shown.
 *
 * The pane pages by KEYSET on `seq`, never by `ts`, and the reason is written
 * where the SQL is (`store/cache.py::page`) and where the type is
 * (`EventPage`). The reset-to-page-one on a board change, and why this second
 * read does not contradict `useBoard`'s one-owner rule, are in `useEvents.ts`.
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
import { DOT, oneLine } from "../card/Thread";
import { TONE_BG, TONE_FG } from "../board/CardTile";
import { Pane, PaneEmpty } from "./Pane";
import { useEvents } from "../../useEvents";
import type { Client } from "../../client";
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

/** A FIXTURE. Not board data, never reachable from `Monitor.tsx` — it exists so
 *  the entry markup above could be developed against the shapes `store/log.py`
 *  actually appends, and so the smoke harness can drive a POPULATED pane. That
 *  day has come: `smoke/main.tsx` renders `EventStream` with these rows, which
 *  is the only way a headless harness reaches markup that a real fetch draws.
 *
 *  The shapes are `core/types.py::Event` verbatim (`id · task · actor · kind ·
 *  body · ts`) with the real `KINDS` vocabulary — created, edited, claimed,
 *  released, status, comment, commit, merged, milestone, submitted, reviewed —
 *  rather than the design's demo strings, so the pill vocabulary and the dot
 *  colours match the log this pane will one day be handed.
 *
 *  What the verb settled on is what these rows already were: `Event[]`, the
 *  stored rows unmodified, `task` included ("project" for board-level facts),
 *  newest first, plus the log's TOTAL length for the header counter. One
 *  correction to the shape guessed here at the time — the cursor is a `seq`,
 *  the cache's rowid, and NOT a `ts`. `ts` ties (a plan of nine writes nine
 *  events in one millisecond) and a tying cursor drops or repeats the rows on
 *  the boundary, which is what `test_paging_the_log_crosses_a_boundary…` pins. */
export const FIXTURE_EVENTS: readonly Event[] = [
  { id: "f1", task: "tk-4b37dd", actor: "dev:berna", kind: "created", body: { card: { title: "Panel: Event stream" } }, ts: 0 },
  { id: "f2", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "claimed", body: { branch: "tk-4b37dd" }, ts: 60 },
  { id: "f3", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "commit", body: { sha: "0000000", subject: "the pane is drawn before the verb exists", numstat: { "src/x.py": [3, 1], "logo.png": null } }, ts: 120 },
  { id: "f4", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "comment", body: { text: "no verb streams the log yet" }, ts: 180 },
  { id: "f5", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "submitted", body: { note: "handed in" }, ts: 240 },
  { id: "f6", task: "tk-4b37dd", actor: "dev:berna", kind: "reviewed", body: { verdict: "pass", note: "" }, ts: 300 },
  { id: "f7", task: "tk-4b37dd", actor: "dev:berna", kind: "status", body: { to: "done" }, ts: 360 },
  { id: "f8", task: "project", actor: "dev:berna", kind: "milestone", body: { op: "opened" }, ts: 420 },
];

/** A commit's `numstat`, folded to one phrase — `3 files · +41 −7 · 1 binary`.
 *
 *  The honest-binary rule, the same one `mcp/dossier.py::_sized` follows and
 *  for the same reason: a file whose pair is `null` is one git could not count
 *  (it prints `-` for a binary), which is NOT the same fact as a file that
 *  changed by nothing. It is counted as a binary and never as `+0 −0`. And a
 *  commit event written before commits carried counts has no `numstat` at all —
 *  absent returns null here and the line is simply not drawn, rather than
 *  claiming a commit touched nothing. */
function sizes(event: Event): string | null {
  if (event.kind !== "commit") return null;
  const raw = event.body["numstat"];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const counts = Object.values(raw as Record<string, unknown>);
  if (counts.length === 0) return null;
  let added = 0;
  let deleted = 0;
  let binary = 0;
  for (const pair of counts) {
    if (pair === null) {
      binary += 1;
    } else if (Array.isArray(pair) && pair.length === 2) {
      added += typeof pair[0] === "number" ? pair[0] : 0;
      deleted += typeof pair[1] === "number" ? pair[1] : 0;
    }
  }
  const files = `${counts.length} file${counts.length === 1 ? "" : "s"}`;
  const parts = [files, `+${added} −${deleted}`];
  if (binary > 0) parts.push(`${binary} binary`);
  return parts.join(" · ");
}

const pill: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "2px 9px",
  borderRadius: "20px",
};

/** One entry, exactly as drawn. `div`s, not buttons: the design gives these rows
 *  no `onClick`, so the seam gives this panel no `onOpen` (panels.ts). */
function Entry({ event, now }: { event: Event; now: number }): React.JSX.Element {
  const tone = DOT[event.kind] ?? "neutral";
  const measured = sizes(event);
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
          {/* Phrase AND prose, joined: this row has one line to spend, and a
              close whose note went missing here is the same bug the thread had. */}
          {oneLine(event)}
        </div>
        {measured === null ? null : (
          <div
            className="mono"
            data-testid="event-numstat"
            style={{ fontSize: "10.5px", color: "var(--faint)", marginTop: "4px" }}
          >
            {measured}
          </div>
        )}
      </div>
    </div>
  );
}

const moreButton: React.CSSProperties = {
  marginTop: "6px",
  padding: "9px 0",
  borderRadius: "10px",
  border: "1px solid var(--hair)",
  background: "transparent",
  color: "var(--text-3)",
  fontSize: "12px",
  cursor: "pointer",
};

export function EventStream({
  events,
  total,
  now,
  more,
  loading,
  onMore,
}: EventStreamProps): React.JSX.Element {
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
          {loading
            ? "Reading the log…"
            : total === null
              ? "Nothing has asked the board for the log — this pane pages it itself, and it has not been handed a client to ask with."
              : "The log is empty. Nothing has happened on this board yet: the first plan, claim or commit appears here the moment it is written."}
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
          {/* Nova draws no infinite scroll, so neither does this: paging is a
              deliberate act. The button disappears at the tail of the log —
              "no more" is shown by there being nothing left to press. */}
          {more ? (
            <button
              type="button"
              data-testid="event-more"
              style={moreButton}
              disabled={loading}
              onClick={onMore}
            >
              {loading ? "reading…" : "older"}
            </button>
          ) : null}
        </div>
      )}
    </Pane>
  );
}

/** The container: the client, the paging, and nothing drawn. Everything about
 *  WHY this second read exists and why it opens no socket is in `useEvents.ts`.
 *
 *  `signal` is anything whose identity changes when the board moved — App hands
 *  it the board payload, which is a new object on every answer `useBoard`
 *  receives, so a change frame resets this pane to page one through the ONE
 *  feed that already exists. */
export function EventStreamPane({
  client,
  signal,
  now,
}: {
  client: Client | null;
  signal: unknown;
  now: number;
}): React.JSX.Element {
  const feed = useEvents(client, signal);
  return (
    <EventStream
      events={feed.events}
      total={feed.total}
      now={now}
      more={feed.more}
      loading={feed.loading}
      onMore={feed.loadMore}
    />
  );
}
