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
 * Three of the design's bindings had no source in the payload, and TWO of them
 * still do not (1 was closed by tk-1c407a; the rule and its reading are kept
 * because they are what that card followed). They are typed
 * as nullable HERE rather than dropped, because the milestone rule is that a
 * pane whose data does not exist is still built to its full drawn shape with an
 * honest empty state:
 *
 *   1. RESOLVED (tk-1c407a) — `EventStreamProps.events` was `[]` forever
 *      because no verb returned the log. `events` is now in the registry and in
 *      `RpcVerb`, and the pane pages it by keyset on `seq`. Kept in this list
 *      because it is the one of the four that a card actually closed, and the
 *      shape it was built against turned out to be the shape it got: `Event[]`
 *      from `core/types.py`, unchanged.
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
  BoardGroups,
  BoardRow,
  Event,
  MentionRow,
  Milestone,
  ReportPayload,
  ReviewingRow,
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
  /** `board.groups.reviewing` — a verifier holds a live REVIEW lease, the second
   *  mutex (`store/reviews.py`), and `holder` is that verifier.
   *
   *  NOT the `review` group, and the difference is the whole reason this field
   *  exists: `review` is handed-in-and-waiting — no lease, nobody running, nothing
   *  counting down — so it has no business on a pane about live leases. `reviewing`
   *  is somebody running, which is exactly what this pane draws. Nova's own fifth
   *  pane has such a row (design line 1168: `agent:berna/rv1`, a countdown, WARN)
   *  and counts it among the HEALTHY leases in `leaseHealth` ('4 healthy · 1
   *  lapsed' over 3 doing + 1 review + 1 stalled).
   *
   *  Declared between `doing` and `stalled` because that is its render order in
   *  the design: live and fine, live and being checked, then the lapsed one. */
  reviewing: readonly ReviewingRow[];
  /** `board.groups.stalled` — has an owner, nobody is running it. Same pane on
   *  purpose: a lapsed lease IS the fact this panel is about. */
  stalled: readonly BoardRow[];
  now: number;
  onOpen: (id: string) => void;
  /** What the chapter stands at, read ONLY when no lease is held.
   *
   *  A board holds live leases during a fan-out and at almost no other moment,
   *  so the pane Nova puts first is blank most of the day while six cards sit
   *  ready one tab away. The empty state says what there is instead of only
   *  what there is not. The pane keeps its title, its shape and its subject —
   *  when a lease exists none of this is read, and nothing about the populated
   *  pane changes. */
  standing: { ready: number; blocked: number; closed: number };
}

/* ── 2. Throughput ────────────────────────────────────────────────────────── */

/** How many calendar days the chart draws. The design's viewBox divides its
 *  380 units into exactly this many slots and the subtitle says "Last 14 days",
 *  so the number is the pane's, not the fetcher's — `useBoard` imports it and
 *  asks the board for that window rather than picking one of its own. Two
 *  places choosing 14 independently is how the two drift. */
export const THROUGHPUT_DAYS = 14;

/** The same number in the board verb's own spelling (`verbs/report.py::days`). */
export const THROUGHPUT_WINDOW = `${THROUGHPUT_DAYS}d`;

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
  /** `board.hours`, and it really does arrive as a prop: `useBoard` asks every
   *  `board` call for `window=THROUGHPUT_WINDOW` and the browser's IANA zone, so
   *  the field is populated on the same snapshot as every other pane's rows.
   *
   *  `pulse.py::run` builds `hours` ONLY when the call passes `window=` — a
   *  caller that forgets it gets `null`, which is why this stays nullable and
   *  the pane keeps an empty state naming the missing argument. It is the
   *  fallback for a server or a caller that did not ask, not the normal path. */
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
  /** `board.groups.reviewing` — the SECOND lease kind the board has. The pane
   *  whose whole job is lease health has to count it, or it is blind to half of
   *  what it claims to measure: a verifier holding the review mutex is a live
   *  lease by the group's own definition.
   *
   *  It is not a fourth bucket. Nova's own arithmetic settles it — 3 doing + 1
   *  review + 1 stalled reads '4 healthy · 1 lapsed' (design line 1375), so a
   *  review lease is healthy exactly as a work lease is. See LeaseHealth.tsx
   *  `bucket()` for why the row's `quiet_for` may not say so on its own. */
  reviewing: readonly ReviewingRow[];
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
  /** `board.milestone` — `null` when no milestone is open AND when several are:
   *  the server refuses to guess between chapters. The pane needs the count to
   *  tell those two apart, because "no milestone is open" is a false statement
   *  on a board with two.
   *
   *  The pane reads `title`, `goal`, `rules`, `criteria` and `branch`. It is the
   *  ONLY place a chapter's `criteria` is drawn in the whole dashboard
   *  (tk-77dc9c): the field existed in `core/types.py` and had no TypeScript
   *  transcription at all, so widening the slice past `Milestone` — say, to the
   *  three fields Nova draws — would have hidden the drift instead of catching
   *  it. The narrow-slice rule above applies to the PAYLOAD, not to a stored
   *  row that already is one thing. */
  milestone: Milestone | null;
  /** `board.milestones.length` — how many chapters are open. */
  chapters: number;
  /** `board.repo` — where this repo lives on the web, so the integration branch
   *  in the footer can be the chapter's diff against the trunk (`links.tsx`).
   *
   *  OPTIONAL, and not only for the two version-skew reasons `links.tsx` gives:
   *  a prop that a call site has not been taught to pass must still compile,
   *  because this seam is edited from several worktrees at once and the failure
   *  mode of a REQUIRED prop landing before its caller does is a red build in
   *  everybody else's tree. Absent, the pane is what it was. */
  repo?: { host: string; slug: string; url: string } | null | undefined;
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
  /** One keyset page of the log at a time, newest first, from the `events` verb
   *  (`EventPage` in types.ts). Note 1 above is now history: the pane is fed.
   *
   *  The panel stays PURE — it is handed rows and a callback and owns no fetch,
   *  which is what keeps it renderable under `react-dom/server` with no wire.
   *  `EventStreamPane` in EventStream.tsx is the container that has the client,
   *  exactly as `Dossier` is exported beside `Drawer`. */
  events: readonly Event[];
  /** the design's `1,284` counter: the LOG's length, not this page's. `null`
   *  until the first answer — an unfetched log and an empty one are not the
   *  same picture. */
  total: number | null;
  now: number;
  /** an older page exists behind the last row */
  more: boolean;
  /** a page is in flight */
  loading: boolean;
  /** ask for it. The design draws no infinite scroll, so neither does this. */
  onMore: () => void;
}

/* ── 9. Worktrees ─────────────────────────────────────────────────────────── */

/** Where `gitwork/trees.py` pins a card's worktree: `.taskops/trees/<id>`, for
 *  life. The path is a CONSTRUCTION, not a field — `BoardRow` carries no
 *  directory and no verb reports one, and there is nothing to fetch because
 *  there is nothing to disagree with: one branch, one directory, permanent. */
export const TREE_DIR = ".taskops/trees/";

/** One line of the Worktrees table — the design's `trees`.
 *
 *  `id` is BOTH the card and the branch: a branch name is the card id and
 *  nothing else (no slug — `ARCHITECTURE.md` §11), so the Branch column and the
 *  row's identity are the same string, which is why there is no `branch` field
 *  here to drift from it. */
export interface WorktreeRow {
  id: string;
  title: string;
  /** `TREE_DIR + id` */
  dir: string;
  /** ALWAYS `null`, and the column draws `—`.
   *
   *  A fourth binding with no source, on the same rule as the three above: the
   *  pane is built to its full drawn shape and says what is missing rather than
   *  inventing a number. `BoardRow` (`pulse.py::_row`) carries no commit count,
   *  and commits are not a card field at all — each one is a `commit` EVENT on
   *  the card (`CardPayload.commits` is `_facts.commits_of` folding them, and
   *  only the dossier pays for that).
   *
   *  What it would take: a `commits: int` on the row, counted in
   *  `pulse.py::_row` from the card's commit events. The cost is the reason it
   *  is not here — `_row` runs per row on every board poll, so that is ONE
   *  extra events read per card per poll, on the hot path that every open tab
   *  hits on a timer. Adding it is a server card, not this one. */
  commits: number | null;
  /** WHO carries this tree, as two distinguishable facts.
   *
   *  `dev` is `format.ts::ownerOf` applied to the row's actor — the PERSON to
   *  talk to, the same fold the header's AvatarStack does (a row of processes
   *  says nothing about who is around). `worker` is `shortActor` of that same
   *  actor — WHICH process holds the directory — and is `null` when the actor
   *  is a dev already, because then there is no process to name and
   *  `dev:berna · berna` would only be saying it twice.
   *
   *  BOTH are `null` when the row has neither a live `holder` nor an
   *  `assignee`: a `take` row nobody is on. The cell says so in words rather
   *  than rendering blank — an empty cell in an ownership column reads as a
   *  payload that failed, not as "free". */
  dev: string | null;
  worker: string | null;
  /** the design's `{{ w.merged }}` pill */
  status: string;
  tone: Tone;
}

export interface WorktreesProps {
  /** The whole grouping, unsliced — and the ONE place in this seam where that is
   *  the narrowest honest slice: the table's five states are folded from SEVEN
   *  groups (`take`, `doing`, `stalled`, `reviewing`, `blocked`, `merge`,
   *  `done`), which is every group except `mentions` (not a card row) and
   *  `changes`. Naming seven fields would be listing `BoardGroups` with two
   *  holes in it. */
  groups: BoardGroups;
  onOpen: (id: string) => void;
  /** `board.repo` — the switch for the compare link on every row. Optional for
   *  the reasons `ChapterProps.repo` sets out. */
  repo?: { host: string; slug: string; url: string } | null | undefined;
  /** `board.milestone?.branch` — the BASE a row's branch is compared against.
   *  A row's own head is `tk-<id>`, which is `WorktreeRow.id` by construction;
   *  the base is the one thing the table does not already hold. Empty when no
   *  chapter is in focus, and then the compare falls back to the forge's own
   *  default branch (`links.tsx`, "the trunk the UI does not know"). */
  milestoneBranch?: string;
}
