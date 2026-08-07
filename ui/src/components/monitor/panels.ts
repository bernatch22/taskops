/* THE SEAM. Every Monitor panel's props, as a declared type.
 *
 * Read this before you write a panel. It is the only file in the Monitor
 * milestone that five workers share, and it exists because the last time a prop
 * contract was written as a COMMENT, three pages were built against a version of
 * it that had not been merged when they were written — every card closed green
 * and nothing fitted together (`docs/fan-out.md`). A declared interface is a
 * compile error in five worktrees at once; a comment is nothing.
 *
 * ── The rule these interfaces follow ──────────────────────────────────────
 *
 * Each Props declares the NARROWEST slice of the payload the design's own
 * bindings need — not `board: BoardPayload`. A panel that says it needs
 * `blocked: readonly BlockedRow[]` has documented its real dependency, and the
 * day the board grows a field, the compiler names the panels that care. A panel
 * that took the whole payload would name none of them.
 *
 * Consequences, both deliberate:
 *   · `Monitor.tsx` does the slicing and NOTHING else. A panel card replaces its
 *     own file and never touches Monitor.tsx or Pane.tsx (criterion 4).
 *   · Derivation lives INSIDE the panel. `Monitor.tsx` passes rows; turning rows
 *     into `LeaseProc`s is the panel's work, and the row types below are the
 *     shared vocabulary for it so two panels cannot name the same thing twice.
 *
 * `now` is passed, never read from the clock inside a panel: eight panels each
 * calling `Date.now()` render eight slightly different "now", and a panel that
 * takes its clock as a prop is the only kind that can be tested.
 *
 * `onOpen` appears on exactly the panels where the design draws a `<button
 * onClick="{{ open }}">` — Live leases, Dependency chain, Addressed to you. Edit
 * surface and Event stream rows are `<div>`s in the design and get no callback;
 * adding one would be inventing an interaction Nova does not have.
 *
 * ── What the board cannot answer (say it, do not substitute) ──────────────
 *
 * Three of the design's bindings have no source in the payload. They are typed
 * as nullable HERE rather than dropped, because the milestone rule is that a
 * pane whose data does not exist is still built to its full drawn shape with an
 * honest empty state:
 *
 *   1. `EventStreamProps.events` — there is NO event-stream verb. The client's
 *      registry is `board | card | report | mentions | update` (`types.ts`,
 *      `RpcVerb`), and `BoardPayload` carries no event list. `Event[]` is the
 *      shape the log would arrive in (`core/types.py`), so the panel is built
 *      against the real type and handed `[]`.
 *   2. `ThroughDay.reviews` — `ReportDay` has `closed` and `commits` and no
 *      review count, so the warn-coloured review line and the "reviews passed"
 *      total in the design have no source. `null` means "not knowable", which is
 *      not the same fact as `0`.
 *   3. `LeaseProc.load` — the design draws a sparkline per lease. Nothing in the
 *      payload is a per-lease time series; `BoardRow` carries two scalars,
 *      `since` and `quiet_for`. `null` says so.
 */
import type {
  BlockedRow,
  BoardRow,
  Event,
  MentionRow,
  Milestone,
  ReportPayload,
} from "../../types";
import type { Tone } from "../board/CardTile";

/** Re-exported so a panel imports its palette from the seam rather than reaching
 *  into the Board's tile. `Tone` is defined ONCE, in CardTile.tsx. */
export type { Tone };

/* ── 1. Live leases ───────────────────────────────────────────────────────── */

/** The lease TTL, in seconds. `store/live.py` renews on every call; a lease that
 *  is not renewed lapses, which is what makes "remaining" a real quantity and
 *  not a countdown the UI invented. */
export const LEASE_TTL = 900;

/** One row of Live leases — the design's `procs`. */
export interface LeaseProc {
  card: string;
  actor: string;
  title: string;
  /** the design's `{{ p.remain }}`: `ago()` of the seconds left on the TTL */
  remain: string;
  /** the design's `{{ p.remainLabel }}`: what that number is ("left", "quiet") */
  remainLabel: string;
  /** the design's `{{ p.state }}` pill */
  state: string;
  tone: Tone;
  /** the sparkline series. `null` — no per-lease series exists (note 3 above). */
  load: readonly number[] | null;
}

export interface LiveLeasesProps {
  /** `board.groups.doing` — somebody holds the lease right now */
  doing: readonly BoardRow[];
  /** `board.groups.stalled` — has an owner, nobody is running it. Same pane on
   *  purpose: a lapsed lease IS the fact this panel is about. */
  stalled: readonly BoardRow[];
  now: number;
  onOpen: (id: string) => void;
}

/* ── 2. Throughput ────────────────────────────────────────────────────────── */

/** One bar of the 14-day chart — the design's `throughDays`. */
export interface ThroughDay {
  /** the calendar label, already formatted by `core/hours.py` */
  day: string;
  closes: number;
  commits: number;
  /** `null` — `ReportDay` carries no review count (note 2 above) */
  reviews: number | null;
}

export interface ThroughputProps {
  /** `board.hours` — only present when the board call passed `window=`. `null`
   *  is the honest state before it does, not an error. */
  report: ReportPayload | null;
}

/* ── 3. Lease health ──────────────────────────────────────────────────────── */

/** One arc of the donut and one line of the legend — the design's `health`. */
export interface HealthSlice {
  label: string;
  n: number;
  tone: Tone;
}

export interface LeaseHealthProps {
  doing: readonly BoardRow[];
  stalled: readonly BoardRow[];
  now: number;
}

/* ── 4. Dependency chain ──────────────────────────────────────────────────── */

/** One node — the design's `dag`. `depth` is the indent, derived from how far
 *  down the `waiting_on` chain the row sits; the design binds it as `d.pad`. */
export interface DagNode {
  id: string;
  title: string;
  depth: number;
  /** the trailing phrase: what it waits for, or that it is clear */
  note: string;
  tone: Tone;
}

export interface DependencyChainProps {
  /** `board.groups.blocked` — each row carries its own `waiting_on` */
  blocked: readonly BlockedRow[];
  /** the rows a blocked one may be waiting ON, so a blocker can be named and not
   *  just its id: `take`, `doing` and `stalled` together. */
  others: readonly BoardRow[];
  onOpen: (id: string) => void;
}

/* ── 5. Edit surface ──────────────────────────────────────────────────────── */

/** One path — the design's `files`. A warning, never a lock: `claims` counts the
 *  open cards naming this path, and `contended` is `claims > 1`. */
export interface FileClaim {
  path: string;
  /** which cards, in words — the design's `{{ f.detail }}` */
  detail: string;
  claims: number;
  contended: boolean;
}

export interface EditSurfaceProps {
  /** every open row that names files: `take` + `doing` + `stalled` + `blocked` */
  rows: readonly BoardRow[];
}

/* ── 6. Chapter in focus ──────────────────────────────────────────────────── */

export interface ChapterProps {
  /** `board.milestone` — `null` when no milestone is open, which the pane says
   *  rather than rendering an empty heading. */
  milestone: Milestone | null;
}

/* ── 7. Addressed to you ──────────────────────────────────────────────────── */

/** One mention — the design's `mentions`. `MentionRow` is already the right
 *  shape (`id` is the card); this names the design's fields onto it. */
export interface MentionCard {
  card: string;
  by: string;
  ago: string;
  text: string;
  title: string;
}

export interface MentionsProps {
  /** `board.groups.mentions` — unanswered, addressed to the reader */
  mentions: readonly MentionRow[];
  now: number;
  onOpen: (id: string) => void;
}

/* ── 8. Event stream ──────────────────────────────────────────────────────── */

/** One entry — the design's `events`. */
export interface StreamEvent {
  ts: string;
  rel: string;
  kind: string;
  actor: string;
  card: string;
  body: string;
  tone: Tone;
}

export interface EventStreamProps {
  /** ALWAYS `[]` today: no verb streams the log (note 1 above). The panel is
   *  built to its full drawn shape and says on its face that the verb is
   *  missing — it is not omitted, and it is not faked. */
  events: readonly Event[];
  /** the design's `1,284` counter. `null` — nothing reports the log's length. */
  total: number | null;
  now: number;
}
