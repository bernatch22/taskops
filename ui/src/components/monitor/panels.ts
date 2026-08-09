/* THE SEAM. Every Monitor panel's props, as a declared type.
 *
 * Read this before you write a panel. It is the only file in the Monitor
 * milestone that five workers share, and it exists because the last time a prop
 * contract was written as a COMMENT, three pages were built against a version of
 * it that had not been merged when they were written — every card closed green
 * and nothing fitted together. A declared interface is a
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
  CardPayload,
  Event,
  MentionRow,
  Milestone,
  ReportPayload,
  ReviewingRow,
  TeamMember,
} from "../../types";
import type { Tone } from "../board/CardTile";
/** Type-only, and it is the door's client as `links.tsx` declares it —
 *  structurally, so this seam names the reader the cascade already takes rather
 *  than inventing a second spelling of it. */
import type { GitReader } from "../../links";

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
  /** The chapter in focus has LANDED — read only when no lease is held, like
   *  `standing`, and for the same reason one step further.
   *
   *  "Nobody holds a lease right now · 0 ready to pick up · 0 blocked" is true
   *  of a finished chapter and reads as a live board that has gone quiet, which
   *  is the opposite of what happened. A landed chapter has nothing to pick up
   *  BY DEFINITION — `taskops_merge milestone=` refuses while any card is open
   *  — so the two figures that are calls to action are not drawn at all and the
   *  sentence names the state. Optional and defaulting to false: a board one
   *  version behind sends no landed chapter to focus, so the question never
   *  arises there. */
  finished?: boolean;
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
  /** Every OPEN chapter — `board.milestones` filtered by `status === "open"`,
   *  because that list carries the landed ones too (types.ts) and a landed
   *  chapter is history, not something in flight.
   *
   *  This REPLACED a `chapters: number` count. When the server cannot focus one
   *  the pane no longer says how many there are and stops, it LISTS them, one
   *  foldable row each — so it needs the chapters themselves, and a count beside
   *  them would be a second spelling of `open.length`.
   *
   *  Not optional and not nullable: an empty list is the honest "no chapter is
   *  open", which is a state this pane already drew. */
  open: readonly Milestone[];
  /** Every OPEN card row, across groups — `take` + `doing` + `stalled` +
   *  `blocked` + `reviewing` + `review` + `changes` + `merge`, which is every
   *  group except `mentions` (not a card) and `done` (a capped tail, so it
   *  cannot be counted).
   *
   *  The pane folds these by `BoardRow.milestone` to say how many open cards
   *  each row of the accordion carries. The FOLD is the panel's, as this seam's
   *  rule says — Monitor slices and nothing else — and it is a fold and not an
   *  invention: a chapter with no rows reads `0 open`, and a payload where NO
   *  row carries a `milestone` at all (the field is optional, types.ts) draws no
   *  counts on any row rather than `0 open` on all of them.
   *
   *  Only read in the accordion, which only renders when NO chapter is in focus
   *  — and that is exactly when these groups are unfiltered. Focus a chapter and
   *  the server narrows the groups to it, but then `milestone` is non-null and
   *  the pane is drawing one chapter, not counting several. */
  rows: readonly BoardRow[];
  /** Focus a chapter — THE SAME setter the header's milestone picker calls
   *  (`App.tsx::setMilestone`, threaded down through Monitor).
   *
   *  Not a pane-local selection and not a copy of that state: after this fires
   *  the picker and this pane agree because they ARE one fact. Optional so the
   *  pane renders under a harness with no wire; absent, no focus control is
   *  drawn at all — a button that selects nothing is worse than no button. */
  onFocus?: ((id: string) => void) | undefined;
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

/* ── The Worktrees VIEW — not a Monitor pane, and numbered out of the run ───
 *
 * Everything above and below is one of Monitor's NINE panes, in Nova's order.
 * The Worktrees tab is a view of its own and lives here because it is the same
 * kind of contract — a declared props interface several worktrees compile
 * against — not because it is a tenth pane. Numbering it would have made the
 * pane count unreadable, and the pane count is what `tests/test_ui.py::PANES`
 * asserts against the committed bundle. */

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
  /** WHICH CHAPTER this tree belongs to, resolved: the row carries the id
   *  (`BoardRow.milestone`, `pulse.py::_row`) and the payload's `milestones`
   *  list carries the words, so the pair is joined ONCE, where the rows are
   *  built, and every cell below is handed the answer.
   *
   *  `null` covers both honest gaps and they are deliberately not told apart on
   *  screen: a board one version behind sends no `milestone` on the row, and a
   *  chapter that has aged past `milestones`' cap cannot be named. In neither
   *  case does the cell show a raw `ms-…` id — an identifier nobody can read is
   *  not more informative than an empty cell, it is only louder.
   *
   *  `branch` rides in the SAME join, and it is not decoration: it is the BASE
   *  this tree is compared against (`Milestone.branch`, `pulse.py` sends it on
   *  every chapter). A card belongs to a chapter regardless of who is looking
   *  at it, so the base is the ROW's own chapter and never the one the header
   *  happens to have in focus — with "All milestones" selected `board.milestone`
   *  is `null` (`verbs/_facts.py::in_scope` refuses to guess between several),
   *  and a base of `""` made the /git door answer not-found for EVERY tree.
   *  There is no fallback to another chapter's branch: rendering one chapter's
   *  work as another's diff is worse than the empty state it would replace. */
  milestone: { id: string; title: string; branch: string } | null;
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
  /** `board.milestones` — the id → {title, branch} dictionary for
   *  `WorktreeRow.milestone`. Optional: absent, no row can name its chapter and
   *  every one of them says nothing, which is exactly what a board that sends no
   *  chapters can support — and then no row has a base either, which is the
   *  no-base case `links.tsx` already documents ("the trunk the UI does not
   *  know"). */
  milestones?: readonly Milestone[];
  /** `board.repo` — the switch for the compare link on every row. Optional for
   *  the reasons `ChapterProps.repo` sets out. */
  repo?: { host: string; slug: string; url: string } | null | undefined;
  /* There is NO `milestoneBranch` here, and there must not be one again. It
   * carried `board.milestone?.branch` — the chapter IN FOCUS — and with "All
   * milestones" selected that is `""`, so every tree on the index compared
   * against nothing and the diff page said "this host could not read that
   * diff". The base belongs to the row (`WorktreeRow.milestone.branch`),
   * resolved once in `rows()` from this same `milestones` list. A second source
   * of the same fact could only ever contradict the first. */
  /** The `/git` door's client, handed straight down to the diff page. The table
   *  itself never reads it — it is `WorktreeDiffProps.reader` arriving one level
   *  up, because the page that owns the view state is the page that owns the
   *  props of what it switches to. */
  reader?: GitReader | null | undefined;
}

/** THE FULL-WIDTH DIFF PAGE — the second surface this chapter adds.
 *
 *  It is NOT the card Dossier and NOT a modal: the Worktrees page renders this
 *  INSTEAD of its table (an early return on its own `openTree` state), so the
 *  reader is on a page, at full width, with a way back. The drawer keeps its own
 *  Files changed pane, untouched; nothing here replaces it.
 *
 *  Everything it draws comes through `links.tsx::cascade` — numstat → the patch
 *  → the forge link → one honest sentence. No component fetches a patch outside
 *  that function, so this interface hands over the two things the cascade needs
 *  (a `reader` and a `repo`) and the range to ask for, and nothing else. */
export interface WorktreeDiffProps {
  /** The tree the reader clicked — already folded, already named, already
   *  carrying its chapter. The page re-derives none of it: the row IS the
   *  selection, and `row.id` is both the card and the head branch. */
  row: WorktreeRow;
  /** The BASE of the comparison — `row.milestone?.branch`, THIS CARD's chapter
   *  integration branch, never the chapter the header has in focus. Empty only
   *  when the row's chapter cannot be resolved at all (a payload one version
   *  behind, or a chapter aged past `milestones`' cap), and then the door is
   *  asked for nothing and the forge falls back to its own default branch
   *  (`links.tsx`, "the trunk the UI does not know"). */
  base: string;
  /** `board.repo` — step three of the cascade, and the only thing that decides
   *  whether an unreadable diff can still be offered as a link. */
  repo?: { host: string; slug: string; url: string } | null | undefined;
  /** The `/git` door's client. `null` on a host that serves boards and not a
   *  clone, which is not an error: the cascade says so in words. */
  reader?: GitReader | null | undefined;
  /** Back to the table. The page owns no router and no history entry — the
   *  selection is one `useState` in `pages/Worktrees.tsx` and this clears it. */
  onBack: () => void;
}

/** THE CARD'S OWN THREAD, on the diff page — and why it is a SEPARATE interface
 *  rather than four more fields on `WorktreeDiffProps`.
 *
 *  A worktree has no identity apart from its card: `gitwork/trees.py` pins
 *  `tk-<id>` as branch, directory and id at once. So there is no worktree
 *  comment and there must never be one — a second thread would be two places to
 *  say something about one thing, and the reader of the CARD would see half of
 *  it. The page therefore renders the same `Thread` the dossier renders, with
 *  the same `CommentBox`, writing through the same `useBoard::comment` → `update
 *  comment=` door. Nothing there fetches: `App` already opens the card when it
 *  opens the tree, exactly as the drawer does, so the payload arrives as a prop
 *  and there is no second fetch shape to keep in step.
 *
 *  Every field is optional because the thread is the page's SECOND half: the
 *  diff renders whole without any of them, and a caller that has not been taught
 *  to pass a dossier gets the page it had. It was declared inside
 *  `pages/WorktreeDiff.tsx` for the length of one wave — this file was held by
 *  another card — and moved back here at the chapter close, which is what that
 *  file's own comment said would happen. */
export interface ThreadProps {
  /** The card behind the tree — the dossier `verbs/card.py` returns, handed down
   *  by `App`. `null` while it is in flight, and then the page draws its diff and
   *  says the thread is still coming rather than showing an empty one. */
  dossier?: CardPayload | null | undefined;
  /** Who is addressable in the mention picker — `board.team`, the same list the
   *  drawer's box gets. Empty is a picker with nobody in it, not a crash. */
  team?: TeamMember[];
  now?: number;
  /** The dashboard's ONE write. Absent, the thread is read-only and no box is
   *  drawn — a send button with nowhere to send is worse than no box. */
  onComment?: ((text: string, mentions: string[]) => Promise<void>) | undefined;
  /** This window is watching a PUBLIC board as `anon`, so the box renders its
   *  refusal instead of a form it cannot submit (`card/CommentBox.tsx`).
   *  Optional: every caller with a credential passes nothing and is unchanged. */
  readOnly?: boolean;
}

/* ── 9. Swarm topology ────────────────────────────────────────────────────── */

/** What a circle on the ring IS. Four of these are actors and one is a card;
 *  the legend at the foot of the pane names the four actor kinds only, exactly
 *  as the mock draws it — a card is the thing they are attached TO, not a role.
 *
 *  `verifier` is its own kind and not a shade of `worker` for the reason the
 *  board itself keeps two mutexes: a REVIEW lease (`store/reviews.py`) is a
 *  SECOND lease on the same card, so an actor holding one is not doing the same
 *  thing as the actor holding the work lease, and a card carrying both has two
 *  honest edges rather than a duplicate. */
export type SwarmKind = "orchestrator" | "worker" | "verifier" | "lapsed" | "card";

/** A node, already placed. The position is computed by `topology()` — a pure
 *  function of the payload, deterministic by index around one circle — because a
 *  force simulation is an animation loop whose output no headless harness can
 *  assert. `Math.random()` appears nowhere in this pane. */
export interface SwarmNode {
  /** the actor string, or the card id — the two namespaces cannot collide */
  id: string;
  kind: SwarmKind;
  /** the glyphs drawn INSIDE the circle — `initials()` for an actor, the card
   *  id without its `tk-` for a card. Two texts per node is what makes the mock
   *  read as a diagram instead of a bubble chart. */
  glyph: string;
  /** the sub-label under the circle: the card id, or what the actor IS
   *  (`orchestrator`, `worker`, …) — the mock's `dy="46"` text */
  label: string;
  /** the `<title>`: the actor AND its card, because a circle with no text is
   *  unreachable to a screen reader otherwise */
  title: string;
  x: number;
  y: number;
}

/** `lease` is an actor attached to a card — one edge per lease, and the lapsed
 *  variety is an assignment with no lease behind it, drawn faint. Both start at
 *  an AGENT: a `dev:` is refused `take` by the registry, so an edge from a dev
 *  to a card is a claim the server makes impossible.
 *
 *  `owns` is the dev→agent edge, and it is a different KIND of fact — a standing
 *  property of the name (`agent:<dev>/<name>`, `format.ts::ownerOf`, the same
 *  relation `http/auth.py::authorize` enforces on the wire) rather than a live
 *  claim that expires. Drawn hair-thin for exactly that reason, and left out of
 *  the header count: a name is not work.
 *
 *  `contested` is a DASHED edge between two CARDS that declare a path in common
 *  (`BoardRow.files`). It is the same fact the Edit surface pane states, in the
 *  same words: a warning, never a lock. `files` is what a card DECLARED, never
 *  what a worker actually edited — the board never parses source
 *  so this edge can be silent while the tree is wrong and
 *  loud while nothing is. */
export interface SwarmEdge {
  from: string;
  to: string;
  kind: "lease" | "lapsed" | "contested" | "owns";
}

export interface SwarmGraph {
  nodes: SwarmNode[];
  edges: SwarmEdge[];
  /** how many LIVE work/review leases — counted apart from the lapsed and the
   *  ownership edges, which are not somebody working */
  leases: number;
  /** how many `contested` edges — the header count says it out loud */
  contested: number;
  /** nothing is running: no lease, no review, no stalled assignment. The pane
   *  draws one sentence and NO graph — an empty ring pretending to be a graph
   *  is the worst reading of a quiet board. */
  quiet: boolean;
}

/* ── The ACTORS VIEW — the fourth tab, and not a Monitor pane ───────────────
 *
 * Numbered out of the run for the same reason the Worktrees view is: it is a
 * VIEW, and the pane count is what `tests/test_ui.py::PANES` asserts against the
 * committed bundle. It lives here because it is the same kind of contract — a
 * declared props interface that several worktrees compile against.
 *
 * ── What is NOT here, and must never be added ─────────────────────────────
 *
 * A WORKER SLOT. Nova draws the actors screen with a roster of slots — held,
 * free, lapsed, as a pool with a capacity — and that pool does not exist:
 * taskops allocates no worker, `workers=[…]` on `taskops_assign` is a label
 * chosen at the call, and a sub-agent dies with its card (`ARCHITECTURE.md`
 * §11's shape of refusal: the thing that cost time is named, not just banned).
 * So there is no `slots`, no `capacity`, no `free`, and an actor with no card is
 * not an empty slot — it is HISTORY, and `ActorRow` says what it carried instead
 * of `— free —`. Anything with the shape of a fixed pool, under any name, is the
 * thing this chapter refuses.
 *
 * What replaced the slot roster is `Hours worked today`, which is true and is
 * folded out of the report the board already sends. */

/** What an actor IS, from its own name and its live leases — never a stored
 *  field. `dev:` → orchestrator (the one node that never holds a card,
 *  `verbs/__init__.py::REGISTRY`); an agent holding a REVIEW lease is a
 *  verifier, because that is a second mutex on the same card
 *  (`store/reviews.py`); every other agent is a worker. */
export type ActorRole = "orchestrator" | "worker" | "verifier";

/** The pill. Four states and there is no fifth: `doing` and `reviewing` are the
 *  two live leases, `lapsed` is an assignee with nothing running — the state the
 *  board has no repair verb for — and `online` is presence with no card.
 *
 *  `null` is not a state, it is the absence of one: an actor that is only in the
 *  report window has not been seen in 24h (`pulse.py::_team` reads presence over
 *  exactly that span) and wears no pill at all. Inventing a fifth pill for it
 *  would be inventing a status the board does not compute. */
export type ActorState = "online" | "doing" | "reviewing" | "lapsed";

/** One actor card. Every field is a FOLD of `ActorsProps`; nothing here is
 *  fetched and nothing is stored.
 *
 *  The three figures are `number | null` / `string | null` on the rule the whole
 *  chapter follows: absent is drawn as an em dash and never as `0`. A board one
 *  version behind sends `ActorHours` without `closed` and `commits` (types.ts),
 *  and an actor with no hours at all has none of the three. */
export interface ActorRow {
  actor: string;
  /** `initials()` — the same up-to-three glyphs the avatar discs use */
  glyph: string;
  role: ActorRole;
  /** the second line's presence half: `seen 34s`, or that it has not been */
  presence: string;
  state: ActorState | null;
  tone: Tone;
  /** The card it is ON right now — a live lease, or the assignment that lapsed.
   *  `null` is history, not a free slot, and then `carried` is what there is to
   *  say. */
  card: { id: string; title: string } | null;
  /** every card this actor touched INSIDE the report's window
   *  (`ActorHours.cards`) */
  carried: readonly string[];
  /** closed cards and commits inside that same window — `null` when the payload
   *  cannot say (`verbs/report.py::_by_actor`, both optional in types.ts) */
  closed: number | null;
  commits: number | null;
  /** `ActorHours.human`, already formatted by `core/hours.py` — never
   *  re-derived here */
  worked: string | null;
  /** the same figure unformatted, because a DEV's total is the SUM of its
   *  agents' and strings do not add (`ActorHours.seconds`) */
  seconds: number | null;
}

/** THE TOP LEVEL OF THE ACTORS PAGE, and the shape this chapter's first attempt
 *  got wrong.
 *
 *  That version drew one tile per ACTOR, so a session that spawned sixty-seven
 *  ephemeral sub-agents drew sixty-seven tiles beside the one human — each with
 *  the human's layout, none of them a thing that still exists. It contradicted
 *  the chapter's own goal: an actor is a name bound to the RUN of a card, and
 *  `w1` today is not `w1` yesterday.
 *
 *  So the top level is the DEV — the durable identity (`core/types.py::role_of`;
 *  an `agent:<dev>/<name>` carries its dev in the name, `format.ts::ownerOf`,
 *  which is the same relation `http/auth.py::authorize` enforces on the wire) —
 *  and an agent is a LINE inside one. A board with two devs draws two cards,
 *  which is the case this shape exists for; this board has one.
 *
 *  Still no slot, no pool and no capacity: `agents` is who RAN, not who is
 *  allocated, and `live` is a count of held leases at this instant. */
export interface DevRow {
  /** `dev:<name>` — always the qualified string, never the bare name */
  dev: string;
  glyph: string;
  /** the dev's own presence line, or that presence has not seen it */
  presence: string;
  /** the dev's OWN row: it never holds a card, but it comments, commits and
   *  closes, so it has hours of its own. `null` when nothing knows it directly
   *  and it exists only as the owner of its agents. */
  self: ActorRow | null;
  /** every agent of this dev the board can name, live leases first, then most
   *  recently seen. NOT capped here — the cap is a drawing decision and the
   *  view states its own remainder. */
  agents: readonly ActorRow[];
  /** agents holding a live lease RIGHT NOW — work or review. The question
   *  somebody opens this page to answer, so it is on the card unexpanded. */
  live: number;
  /** the cards those live agents are on, so the card can name them without
   *  being opened */
  onCards: readonly { actor: string; id: string; title: string }[];
  /** dev + agents, summed. `null` when some member's own figure was absent:
   *  a total that quietly skipped a member is worse than no total, so the view
   *  draws the dev's own and says the agents' are separate. */
  closed: number | null;
  commits: number | null;
  seconds: number | null;
  worked: string | null;
  /** at least one member could not say one of its figures */
  partial: boolean;
}

export interface ActorsProps {
  /** `board.team` — presence over the last 24h (`verbs/pulse.py::_team`). It is
   *  the ONLY source of "when was this actor last seen", which is why an actor
   *  known only to the report says it has not been seen rather than guessing. */
  team: readonly TeamMember[];
  /** `board.groups.doing` — a live WORK lease; `holder` is the worker */
  doing: readonly BoardRow[];
  /** `board.groups.reviewing` — a live REVIEW lease; `holder` is the verifier */
  reviewing: readonly ReviewingRow[];
  /** `board.groups.stalled` — an `assignee` and nobody running it */
  stalled: readonly BoardRow[];
  /** `board.hours` — the same field Throughput reads, off the same snapshot
   *  (`useBoard` asks every `board` call for `window=`). `null` when the caller
   *  did not ask, and then no figure on the screen is drawn rather than zeroed. */
  report: ReportPayload | null;
  now: number;
  /** Open a CARD's dossier — the same `openCard` every other view uses. The
   *  actor itself is not clickable: there is no actor page and nothing behind
   *  it. */
  onOpen: (id: string) => void;
}

/** Every field is a slice the board already sends. No verb, no payload key, no
 *  store, no second fetch — the pane's own subtitle is its contract. */
export interface SwarmProps {
  /** `board.team` — where the `dev:` actors come from, and the only place they
   *  do: a dev absent from presence is never conjured to hang an agent off. A
   *  dev never holds a card (the role rule, `verbs/__init__.py`), so the centre
   *  of this diagram is the one node with no edge to a CARD — its edges are the
   *  `owns` hairlines out to its own agents. */
  team: readonly TeamMember[];
  /** `board.groups.doing` — a live WORK lease, and `holder` is the worker */
  doing: readonly BoardRow[];
  /** `board.groups.reviewing` — a live REVIEW lease, and `holder` is the verifier */
  reviewing: readonly ReviewingRow[];
  /** `board.groups.stalled` — an `assignee` and no holder anywhere. Nothing
   *  running, nothing written; the state the board has no repair verb for. */
  stalled: readonly BoardRow[];
}
