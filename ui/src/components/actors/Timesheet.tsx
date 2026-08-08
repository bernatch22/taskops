/* A timesheet is a DRAWING, not a paragraph with a new name.
 *
 * It opens inside the DEV's detail overlay (`DevPanel.tsx`) and answers by eye
 * what no figure answers: WHEN the work happened, and who was on the board at
 * the same time. A horizontal axis in real wall-clock, one filled block per
 * counted session placed and sized by its own start and duration, the time
 * nobody counted left as visible empty space, and ONE LANE PER AGENT on the one
 * shared axis.
 *
 * The first version of this file drew the axis but set a list of card ids
 * joined by dots under it, and the reader read the list. It is gone: the ids are
 * in the block titles, where they belong to a position in time.
 *
 * ── Nothing here is computed twice ────────────────────────────────────────
 *
 * The blocks are `ActorHours.sessions`, which is `core/hours.py::sessions` —
 * the very list `spent()` folds into the totals. That is the whole point of the
 * seam: a timeline and a total that each decided for themselves what an
 * interval is would drift, and the drift would be invisible until somebody
 * added the blocks up by hand. This file adds NO arithmetic to it; it only
 * places what it is handed on an axis, and subtracts to find the space between.
 *
 * ── The gaps are the honest half ──────────────────────────────────────────
 *
 * Between two blocks there is time deliberately NOT counted: a gap longer than
 * 30 minutes is dropped WHOLE, never capped (v1 capped it and every break added
 * a phantom half hour). A timesheet that drew only the counted time would
 * silently claim the rest did not happen, so the gap is drawn as real space AND
 * said as a figure — how many, and how much wall-clock they hold.
 *
 * ── One axis per day, shared by every actor ───────────────────────────────
 *
 * A day's extent is taken over ALL actors' sessions that day, never over the
 * lanes being drawn. Lanes scaled to their own extents would put 09:00 and
 * 14:00 at the same x and answer "who was working in parallel" wrongly, which
 * is the one question a timeline is for. So `timesheet()` reads `day.by_actor`
 * whole and every lane it returns is measured against the same `from`/`to` —
 * which also means a dev's lane and its agents' lanes line up by construction,
 * and so do two devs' panels opened one after the other.
 */
import type { ActorSession, ReportPayload } from "../../types";
import { shortActor } from "../../format";

/** A counted block, positioned on the day's shared axis (percent of it). */
export interface Block extends ActorSession {
  left: number;
  width: number;
}

/** Wall-clock between two blocks — time nobody counted. Positioned on the same
 *  axis, and never clickable: there is no event in it to open. */
export interface Gap {
  start: number;
  end: number;
  seconds: number;
  left: number;
  width: number;
}

/** One actor's row on the shared axis. A lane is per ACTOR and not per card:
 *  the card is what a block IS, and a block that changed lane when the card
 *  changed would stop answering "who worked at the same time". */
export interface Lane {
  actor: string;
  /** `shortActor` — the axis is already inside that actor's dev */
  label: string;
  blocks: Block[];
  gaps: Gap[];
  /** seconds counted, and `core/hours.py::human`'s own formatting of them —
   *  never re-derived here */
  seconds: number;
  human: string;
  /** seconds the gaps hold: measured, and deliberately not counted */
  dropped: number;
  /** the payload truncated this actor's blocks (`verbs/report.py::SESSIONS`) */
  capped: boolean;
}

/** An hour mark on the axis. Drawn once, above every lane, because the axis is
 *  one axis: repeating it per lane would suggest each row had its own. */
export interface Tick {
  at: number;
  left: number;
  label: string;
}

export interface TimesheetDay {
  day: string;
  /** the day's SHARED axis, over every actor that worked it */
  from: number;
  to: number;
  ticks: Tick[];
  /** one per requested actor that has blocks this day, in the order asked */
  lanes: Lane[];
}

/** `2h 40m` / `35m` / `—`, the wording of `core/hours.py::human`.
 *
 *  Local and not in `format.ts` on that file's own rule: what makes a helper
 *  shared is a SECOND caller, and the counted totals arrive already formatted by
 *  Python. Only the DROPPED time and the dev's SUMMED time have no server-side
 *  wording — both are subtractions and additions this screen performs — so this
 *  is where that wording lives, and `DevPanel` imports it from here rather than
 *  deriving a second one. */
export function span(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  if (minutes <= 0) return "—";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours && rest) return `${hours}h ${rest}m`;
  return hours ? `${hours}h` : `${rest}m`;
}

/** `09:12` — the block's real wall-clock, in the reader's own zone. */
export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** At most this many hour marks. More than eight on a fortnight-wide axis is a
 *  ruler nobody reads; the step widens instead of the labels shrinking. */
const TICKS = 8;

function ticksOf(from: number, to: number): Tick[] {
  const width = Math.max(1, to - from);
  const step = 3600 * Math.max(1, Math.ceil(width / 3600 / TICKS));
  const out: Tick[] = [];
  // Strictly AFTER `from` and strictly before `to`: a tick on either edge is a
  // label with nothing on one side of it, and the range is already printed
  // under the lanes in full.
  for (let at = Math.floor(from / step) * step + step; at < to; at += step) {
    out.push({ at, left: ((at - from) / width) * 100, label: clock(at) });
  }
  return out;
}

/** The report → the days these actors worked, oldest first, one lane each.
 *
 *  Pure and exported for the reason `devRows()` and `submit()` are: no handler
 *  fires under `react-dom/server`, so a rule left inside a render closure has no
 *  test.
 *
 *  A day none of them worked is not in the list at all — an axis with no block
 *  on it is a row that says nothing, and the view says the nothing in words
 *  instead. */
export function timesheet(
  report: ReportPayload | null,
  actors: readonly string[],
): TimesheetDay[] {
  const out: TimesheetDay[] = [];
  for (const day of report?.days ?? []) {
    /* THE SHARED AXIS — every actor's blocks that day, not the ones asked for. */
    let from = Infinity;
    let to = -Infinity;
    for (const hours of Object.values(day.by_actor)) {
      for (const s of hours.sessions ?? []) {
        from = Math.min(from, s.start);
        to = Math.max(to, s.end);
      }
    }
    if (!Number.isFinite(from) || !Number.isFinite(to)) continue;
    const width = Math.max(1, to - from);
    const place = (start: number, end: number) => ({
      left: ((start - from) / width) * 100,
      width: ((end - start) / width) * 100,
    });

    const lanes: Lane[] = [];
    for (const actor of actors) {
      const mine = day.by_actor[actor];
      const blocks = mine?.sessions ?? [];
      if (blocks.length === 0) continue;

      const placed = blocks.map((s) => ({ ...s, ...place(s.start, s.end) }));
      const gaps: Gap[] = [];
      for (let i = 1; i < placed.length; i += 1) {
        const before = placed[i - 1]!;
        const after = placed[i]!;
        const seconds = after.start - before.end;
        /* Two blocks that touch are two cards, not a gap: only wall-clock that
           was dropped counts, and a zero-length one is not a fact about time. */
        if (seconds > 0) {
          gaps.push({
            start: before.end,
            end: after.start,
            seconds,
            ...place(before.end, after.start),
          });
        }
      }
      lanes.push({
        actor,
        label: shortActor(actor),
        blocks: placed,
        gaps,
        seconds: mine?.seconds ?? 0,
        human: mine?.human ?? "—",
        dropped: gaps.reduce((n, g) => n + g.seconds, 0),
        capped: (mine?.sessions_total ?? blocks.length) > blocks.length,
      });
    }
    if (lanes.length === 0) continue;
    out.push({ day: day.day, from, to, ticks: ticksOf(from, to), lanes });
  }
  return out;
}

/* ── the drawing ──────────────────────────────────────────────────────────── */

/** The rule, in `core/hours.py`'s own words, lifted rather than re-worded: a
 *  second explanation of one computation is a second thing that can go stale,
 *  and this sentence is the difference between a number somebody trusts and a
 *  number somebody argues with. */
export const RULE =
  "The signal is the timestamp of the events themselves. Each interval is credited to the card of the event that CLOSES it — once — and a gap longer than 30 minutes is dropped whole, never capped: nobody knows what happened in that hour.";

/** The lane label column. One value, so a tick's `left` and a block's `left` are
 *  measured against the identical track. */
const LANES = "132px 1fr 84px";

const label: React.CSSProperties = { fontSize: "11px", color: "var(--text-3)" };

const track: React.CSSProperties = {
  position: "relative",
  height: "22px",
  borderRadius: "6px",
  background: "var(--pane-2)",
  overflow: "hidden",
};

function Ruler({ day }: { day: TimesheetDay }): React.JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: LANES, gap: "10px", alignItems: "end" }}>
      <span className="mono" style={label}>
        {day.day}
      </span>
      <div style={{ position: "relative", height: "15px" }} data-testid="timesheet-ruler">
        {day.ticks.map((tick) => (
          <span
            key={tick.at}
            data-testid="timesheet-tick"
            className="num"
            style={{
              position: "absolute",
              left: `${tick.left}%`,
              bottom: 0,
              transform: "translateX(-50%)",
              fontSize: "10px",
              color: "var(--text-3)",
              whiteSpace: "nowrap",
            }}
          >
            {tick.label}
          </span>
        ))}
      </div>
      <span className="num" style={{ ...label, textAlign: "right" }}>
        worked
      </span>
    </div>
  );
}

function LaneRow({
  lane,
  onOpen,
}: {
  lane: Lane;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  return (
    <div
      data-testid="timesheet-lane"
      data-actor={lane.actor}
      style={{
        display: "grid",
        gridTemplateColumns: LANES,
        gap: "10px",
        alignItems: "center",
        padding: "3px 0",
      }}
    >
      <span
        className="mono"
        style={{ ...label, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        title={lane.actor}
      >
        {lane.label}
      </span>
      <div style={track} data-testid="timesheet-axis">
        {/* The gaps first, so a block never disappears under one. They carry
            their figure in the title and are NOT buttons: there is no event in
            a gap to open. */}
        {lane.gaps.map((gap) => (
          <span
            key={`gap-${gap.start}`}
            data-testid="timesheet-gap"
            data-seconds={Math.round(gap.seconds)}
            title={`${span(gap.seconds)} not counted — ${clock(gap.start)} to ${clock(gap.end)}`}
            style={{
              position: "absolute",
              left: `${gap.left}%`,
              width: `${gap.width}%`,
              top: 0,
              bottom: 0,
              background: "repeating-linear-gradient(45deg, transparent 0 3px, var(--hair) 3px 6px)",
            }}
          />
        ))}
        {lane.blocks.map((block) => (
          <button
            key={`${block.task}-${block.start}`}
            type="button"
            data-testid="timesheet-block"
            data-card={block.task}
            onClick={() => onOpen(block.task)}
            title={`${block.task} · ${clock(block.start)}–${clock(block.end)} · ${span(block.seconds)}`}
            style={{
              all: "unset",
              cursor: "pointer",
              position: "absolute",
              left: `${block.left}%`,
              /* A minute-long block is still a fact; below a hairline it would
                 be an invisible one. */
              width: `${Math.max(block.width, 0.8)}%`,
              top: "3px",
              bottom: "3px",
              background: "var(--accent)",
              borderRadius: "4px",
            }}
          />
        ))}
      </div>
      <span className="num" style={{ ...label, textAlign: "right" }} data-testid="timesheet-lane-total">
        {lane.human}
      </span>
    </div>
  );
}

function Day({
  day,
  onOpen,
}: {
  day: TimesheetDay;
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const dropped = day.lanes.reduce((n, l) => n + l.dropped, 0);
  const gaps = day.lanes.reduce((n, l) => n + l.gaps.length, 0);
  const capped = day.lanes.filter((l) => l.capped);
  return (
    <div data-testid="timesheet-day" data-day={day.day} style={{ padding: "10px 0 14px" }}>
      <Ruler day={day} />
      <div style={{ margin: "4px 0 6px" }}>
        {day.lanes.map((lane) => (
          <LaneRow key={lane.actor} lane={lane} onOpen={onOpen} />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", ...label }}>
        <span className="num" data-testid="timesheet-range">
          {`${clock(day.from)} – ${clock(day.to)}`}
        </span>
        <span data-testid="timesheet-dropped">
          {gaps === 0
            ? "no gap"
            : `${gaps} ${gaps === 1 ? "gap" : "gaps"} · ${span(dropped)} not counted`}
        </span>
      </div>
      {capped.length > 0 ? (
        <div style={{ ...label, marginTop: "4px" }} data-testid="timesheet-capped">
          More blocks than one answer carries — {capped.map((l) => l.label).join(", ")} drawn from
          the first blocks only; the total beside each lane is the whole day.
        </div>
      ) : null}
    </div>
  );
}

/** The whole drawing. `days` is `timesheet()`'s answer, so every lane of a day
 *  was already measured against that day's one axis and the rows compare by eye
 *  by construction. */
export function Timesheet({
  days,
  onOpen,
}: {
  days: readonly TimesheetDay[];
  onOpen: (id: string) => void;
}): React.JSX.Element {
  return (
    <div data-testid="timesheet">
      {days.length === 0 ? (
        <div style={label} data-testid="timesheet-none">
          No events in this window — there is no timesheet to draw.
        </div>
      ) : (
        days.map((day) => <Day key={day.day} day={day} onOpen={onOpen} />)
      )}
      <div style={{ ...label, marginTop: "8px", lineHeight: 1.6 }} data-testid="timesheet-rule">
        {RULE}
      </div>
    </div>
  );
}

export default Timesheet;
