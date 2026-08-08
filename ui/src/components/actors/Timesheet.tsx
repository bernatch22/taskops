/* An actor's timesheet: when it worked, and why the total is the number it is.
 *
 * It opens INSIDE the Actors view — not a modal, not a second page. This
 * dashboard's drawer belongs to a CARD, and an actor is not one; there is no
 * actor route and nothing behind it, so the detail is a fold of the row that
 * was already on screen.
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
 * one being read. Two rows scaled to their own extents would put 09:00 and
 * 14:00 at the same x and answer "who was working in parallel" wrongly, which
 * is the one question a timeline is for. So `timesheet()` reads
 * `day.by_actor` whole and every row it returns is measured against the same
 * `from`/`to`.
 */
import { PaneRow } from "../monitor/Pane";
import type { ActorSession, ReportPayload } from "../../types";

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

export interface TimesheetDay {
  day: string;
  /** the day's SHARED axis, over every actor that worked it */
  from: number;
  to: number;
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

/** `2h 40m` / `35m` / `—`, the wording of `core/hours.py::human`.
 *
 *  Local and not in `format.ts` on that file's own rule: what makes a helper
 *  shared is a SECOND caller, and the counted totals arrive already formatted by
 *  Python. Only the DROPPED time has no server-side wording — it is a
 *  subtraction this screen performs — so this is the one place that needs it. */
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

/** The report → one actor's days, oldest first. Pure and exported for the
 *  reason `actorRows()` and `submit()` are: no handler fires under
 *  `react-dom/server`, so a rule left inside a render closure has no test.
 *
 *  A day this actor did not work is not in the list at all — an axis with no
 *  block on it is a row that says nothing, and the view says the nothing in
 *  words instead. */
export function timesheet(report: ReportPayload | null, actor: string): TimesheetDay[] {
  const out: TimesheetDay[] = [];
  for (const day of report?.days ?? []) {
    const mine = day.by_actor[actor];
    const blocks = mine?.sessions ?? [];
    if (blocks.length === 0) continue;

    /* THE SHARED AXIS — every actor's blocks that day, not this actor's. */
    let from = Infinity;
    let to = -Infinity;
    for (const hours of Object.values(day.by_actor)) {
      for (const s of hours.sessions ?? []) {
        from = Math.min(from, s.start);
        to = Math.max(to, s.end);
      }
    }
    const width = Math.max(1, to - from);
    const place = (start: number, end: number) => ({
      left: ((start - from) / width) * 100,
      width: ((end - start) / width) * 100,
    });

    const placed = blocks.map((s) => ({ ...s, ...place(s.start, s.end) }));
    const gaps: Gap[] = [];
    for (let i = 1; i < placed.length; i += 1) {
      const before = placed[i - 1]!;
      const after = placed[i]!;
      const seconds = after.start - before.end;
      /* Two blocks that touch are two cards, not a gap: only wall-clock that
         was dropped counts, and a zero-length one is not a fact about time. */
      if (seconds > 0) {
        gaps.push({ start: before.end, end: after.start, seconds, ...place(before.end, after.start) });
      }
    }

    out.push({
      day: day.day,
      from,
      to,
      blocks: placed,
      gaps,
      seconds: mine?.seconds ?? 0,
      human: mine?.human ?? "—",
      dropped: gaps.reduce((n, g) => n + g.seconds, 0),
      capped: (mine?.sessions_total ?? blocks.length) > blocks.length,
    });
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

const axis: React.CSSProperties = {
  position: "relative",
  height: "14px",
  borderRadius: "7px",
  background: "var(--hair)",
  overflow: "hidden",
};

const label: React.CSSProperties = { fontSize: "11px", color: "var(--text-3)" };

function Day({ day, onOpen }: { day: TimesheetDay; onOpen: (id: string) => void }): React.JSX.Element {
  return (
    <div data-testid="timesheet-day" data-day={day.day} style={{ padding: "9px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", ...label }}>
        <span className="mono">{day.day}</span>
        <span className="num">
          {`${clock(day.from)} – ${clock(day.to)} · ${day.human} worked`}
        </span>
      </div>
      <div style={{ ...axis, margin: "6px 0 5px" }} data-testid="timesheet-axis">
        {/* The gaps first, so a block never disappears under one. They carry
            their figure in the title and are NOT buttons: there is no event in
            a gap to open. */}
        {day.gaps.map((gap) => (
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
              background: "repeating-linear-gradient(45deg, transparent 0 3px, var(--pane) 3px 6px)",
            }}
          />
        ))}
        {day.blocks.map((block) => (
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
              top: 0,
              bottom: 0,
              background: "var(--accent)",
              borderRadius: "7px",
            }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", ...label }}>
        <span className="mono" data-testid="timesheet-cards">
          {[...new Set(day.blocks.map((b) => b.task))].join(" · ")}
        </span>
        <span data-testid="timesheet-dropped">
          {day.gaps.length === 0
            ? "no gap"
            : `${day.gaps.length} ${day.gaps.length === 1 ? "gap" : "gaps"} · ${span(day.dropped)} not counted`}
        </span>
      </div>
      {day.capped ? (
        <div style={{ ...label, marginTop: "4px" }} data-testid="timesheet-capped">
          More blocks than one answer carries — this day is drawn from the first{" "}
          {day.blocks.length}; the total beside it is the whole day.
        </div>
      ) : null}
    </div>
  );
}

/** An actor's whole timesheet. `days` is `timesheet()`'s answer, so the axis was
 *  already measured across every actor and two of these rendered side by side
 *  line up by construction. */
export function Timesheet({
  days,
  onOpen,
}: {
  days: readonly TimesheetDay[];
  onOpen: (id: string) => void;
}): React.JSX.Element {
  return (
    <PaneRow pad="12px 18px">
      <div data-testid="timesheet">
        {days.length === 0 ? (
          <div style={label} data-testid="timesheet-none">
            No events in this window — this actor has no timesheet to draw.
          </div>
        ) : (
          days.map((day) => <Day key={day.day} day={day} onOpen={onOpen} />)
        )}
        <div style={{ ...label, marginTop: "8px", lineHeight: 1.6 }} data-testid="timesheet-rule">
          {RULE}
        </div>
      </div>
    </PaneRow>
  );
}

export default Timesheet;
