/* The wire, transcribed from the Python that produces it.
 *
 * Every type here is a hand transcription of a real payload — `verbs/pulse.py::run`
 * (board), `verbs/_context.py::dossier` via `verbs/card.py::run` (card),
 * `verbs/report.py::summary` (report) and `core/types.py` (the rows). Nothing is
 * inferred from a sample response: a field that exists in one board's data and not
 * in another is exactly the drift this file exists to catch.
 *
 * The reading rule: what the server MAY omit is `| null` (it sends JSON `null`),
 * what a group row MAY carry is optional. Anything the UI is unsure of, it must
 * treat as absent rather than assert — the payload is a contract, not a promise
 * that the board on the other end is the same version.
 *
 * ── The drift convention, and why it is a convention ──────────────────────
 *
 * `Milestone.criteria` was added to `core/types.py`, travelled through plan,
 * take and the landing gate, and never arrived here: the browser was
 * structurally unable to see a chapter's acceptance criteria and nothing said
 * so (tk-77dc9c). So EVERY interface below now carries a `@source` line naming
 * the Python that produces it — a reader who opens either side is one grep from
 * the other, and a diff that changes a payload has the transcription named in
 * its own review.
 *
 * That is a convention, not a check, and the honest reason is that the two
 * halves are not the same kind of object. Only the four stored ROWS (`Card`,
 * `Milestone`, `Event`, `Lease`) are `TypedDict`s whose keys a test could read
 * mechanically — and a ~30-line test comparing `__annotations__` against a
 * regex over this file WOULD have caught this exact bug, cheaply. Everything
 * below them (`BoardPayload`, `CardPayload`, `ReportPayload`, and every row
 * type inside them) is a dict assembled by hand across `pulse.py`, `card.py`,
 * `_context.py` and `report.py`; there is no declared key set to compare
 * against, and inferring one means parsing Python source — which
 * `docs/fan-out.md` concluded taskops does not do. Anything stronger than the
 * TypedDict test is that machinery, and it is not worth it. The row test is
 * cheap and is proposed on the card; it is not written here because this card's
 * diff is `.ts`-only. */

/** The only verbs this client speaks. The board's registry has more; the
 *  dashboard is read-only except for the ONE write (`update` with comment=), and
 *  a union rather than `string` is what makes "do not invent a verb" a compile
 *  error instead of a 400 nobody sees.
 *
 *  @source the subset of `verbs/__init__.py::REGISTRY` this client speaks */
export type RpcVerb = "board" | "card" | "report" | "mentions" | "update";

/* ── the stored rows (core/types.py) ─────────────────────────────────────── */

/** @source `core/types.py::Card`, sent whole by `verbs/card.py::run` */
export interface Card {
  id: string;
  title: string;
  spec: string;
  criteria: string[];
  status: string; // open | done | dropped — the only three that are STORED
  review?: boolean; // NotRequired in Python: a card older than the feature has no key
  priority: number; // 0 urgent … 3 someday
  milestone: string;
  parent: string | null;
  after: string[];
  files: string[];
  labels: string[];
  assignee: string; // "" is the open pool; NOT a claim — the lease is
  created_by: string;
  created: number;
  updated: number;
}

/** @source `core/types.py::Milestone`, sent whole by `verbs/pulse.py::run` and `verbs/card.py::run` */
export interface Milestone {
  id: string;
  title: string;
  goal: string;
  /** What holds for EVERY card of this chapter. Binding, and it travels into
   *  every take. */
  rules: string[];
  /** What the CHAPTER is accepted against — `rules`' sibling, spec and not
   *  status (`core/types.py::Milestone.criteria`, docs/fan-out.md §10). Shown
   *  to the human at `taskops_merge milestone=`, never judged by the machine.
   *
   *  OPTIONAL, and not because the Python says so — `core/types.py` declares it
   *  required and `core/replay.py::_milestone` materialises it as `[]` for a
   *  chapter planned before the field existed, so a board at this version always
   *  sends the key. It is optional because a board one version BEHIND does not:
   *  rendering the pane against the dashboard actually running on this machine
   *  (2026-08-08, port 54546) threw `Cannot read properties of undefined
   *  (reading 'length')`. That server's `board` payload also had no
   *  `done_total`, which `pulse.py::run` does send — so it is a process older
   *  than both fields, and it is exactly the case a live dashboard hits after a
   *  `join` to a board that has not been redeployed. The same run against the
   *  board verb AT THIS COMMIT returns `criteria: []`, present and empty.
   *
   *  That is the header's rule in the concrete: the payload is a contract,
   *  not a promise that the board on the other end is the same version, and the
   *  UI treats what it is unsure of as absent rather than asserting it.
   *
   *  Absent and `[]` mean the same thing to the reader — "this chapter has no
   *  criteria" — and both draw no section. */
  criteria?: string[];
  reviews?: boolean;
  branch: string;
  status: string;
  created: number;
}

/** @source `core/types.py::Event`, sent whole by `verbs/_context.py::dossier` (history) */
export interface Event {
  id: string;
  task: string; // "project" for board-level facts
  actor: string;
  kind: string; // KINDS in core/types.py
  body: Record<string, unknown>; // open on purpose: an unknown kind is stored intact
  ts: number;
}

/** @source `core/types.py::Lease`, sent by `verbs/_context.py::dossier` */
export interface Lease {
  task: string;
  actor: string;
  branch: string;
  acquired: number;
  expires: number;
}

/** Everything a card can be ON SCREEN. Only the first three are stored; the rest
 *  are derived by `core/graph.py` from the graph, the live lease and the thread.
 *
 *  @source `core/machine.py::state`, via `verbs/_context.py::dossier` */
export type CardState =
  | "open"
  | "done"
  | "dropped"
  | "ready"
  | "doing"
  | "blocked"
  | "stalled"
  | "review"
  | "reviewing"
  | "changes";

/* ── board (verbs/pulse.py::run) ─────────────────────────────────────────── */

/** One line of the board — `pulse.py::_row`. `holder` is the LIVE lease holder
 *  and `assignee` is who it was handed to: a stalled card has the second and not
 *  the first, and that difference is the whole group.
 *
 *  @source `verbs/pulse.py::_row` */
export interface BoardRow {
  id: string;
  title: string;
  priority: number;
  assignee: string;
  holder: string | null;
  since: number; // the lease's acquired, else the card's updated
  quiet_for: number | null; // seconds since the owner spoke; null while somebody holds it
  files: string[];
  labels: string[];
}

/** A blocked row carries what it is waiting for — `graph.blockers`.
 *
 *  @source `verbs/pulse.py::run`, which adds `waiting_on` from `core/graph.py::blockers` */
export interface BlockedRow extends BoardRow {
  waiting_on: string[];
}

/** review and changes carry the REASON, not just the id: the submit note is
 *  empty on `review`, and on `changes` it is the reviewer's words verbatim.
 *
 *  @source `verbs/pulse.py::run` (the `review` and `changes` groups) */
export interface VerdictRow extends BoardRow {
  text: string;
  holder: string | null; // on these two it is the REVIEW lease holder
}

/** @source `verbs/pulse.py::run` (the `reviewing` group) */
export interface ReviewingRow extends BoardRow {
  holder: string | null; // likewise: whoever is checking right now
  /** When the REVIEW lease was acquired — a different lease from the one
   *  `since` describes. `since` is the WORK lease's acquisition (or the card's
   *  `updated`), and the worker may still be alive beside the verifier, so it
   *  says nothing exact about the review: counting the TTL down from it yields
   *  a floor that reads 0 while the review lease is provably still live.
   *  Named `review_since` and never folded into `since` because that ambiguity
   *  IS the bug (`store/reviews.py::Held`).
   *
   *  OPTIONAL by the header's rule, not because the Python may omit it: a board
   *  at this version always sends the key (null only if the lease lapsed between
   *  the two reads inside one call). A board one version BEHIND sends no key at
   *  all, and the UI must fall back to the floor rather than assert it. */
  review_since?: number | null;
}

/** A pending mention — `pulse.py::_mentions`. Not a card row: it is the comment
 *  that named you, and it is the one group the milestone filter does not apply to.
 *
 *  @source `verbs/pulse.py::mentions`, from `core/mentions.py` */
export interface MentionRow {
  id: string; // the card the comment lives on
  title: string; // "" when the card is unknown to this board
  by: string;
  text: string;
  ts: number;
}

/** The nine groups, in the order `pulse.py` builds them — which IS the order to
 *  act in, so a view that reorders them is contradicting the board.
 *
 *  @source `verbs/pulse.py::run` */
export interface BoardGroups {
  merge: BoardRow[];
  mentions: MentionRow[];
  review: VerdictRow[];
  changes: VerdictRow[];
  stalled: BoardRow[];
  take: BoardRow[];
  doing: BoardRow[];
  reviewing: ReviewingRow[];
  blocked: BlockedRow[];
  /** Closed AND integrated — the only place finished work is visible. Capped at
   *  `pulse.DONE_SHOWN` (20) and newest first; `BoardPayload.done_total` is the
   *  real count behind the cap. Every other group is bounded by work in flight;
   *  this one only grows, which is why it is the one group that is a tail.
   *
   *  OPTIONAL by the header's rule, and for exactly the reason `done_total` is:
   *  the two arrived in the SAME commit (a1d1005, "closed work is visible"), so
   *  every board older than that sends nine groups, not ten. The other eight
   *  date from the first commit and no board that speaks this protocol omits
   *  them. Consumers read `?? []`. */
  done?: BoardRow[];
}

export const GROUP_ORDER = [
  "merge",
  "mentions",
  "review",
  "changes",
  "stalled",
  "take",
  "doing",
  "reviewing",
  "blocked",
  "done",
] as const satisfies readonly (keyof BoardGroups)[];

export type GroupName = (typeof GROUP_ORDER)[number];

/** @source `verbs/pulse.py::_team` */
export interface TeamMember {
  actor: string;
  seen: number;
  ago: number; // seconds
}

/** The heartbeat that rides on every result — `_context.py::pulse`.
 *
 *  @source `verbs/_context.py::pulse` */
export interface Pulse {
  milestone: string; // the TITLE, "" when no milestone is in scope
  goal: string;
  counts: { doing: number; ready: number; blocked: number; stalled: number; done: number };
  mentions: number; // addressed to the reader of THIS call, unanswered
}

/** @source `verbs/pulse.py::run` */
export interface BoardPayload {
  milestone: Milestone | null;
  /** Every OPEN chapter, then the most recent landed ones — one list, told
   *  apart by `Milestone.status` (`verbs/_facts.py::chapters`).
   *
   *  It used to be the open ones only, which was correct until `landed` became
   *  a real status and two finished chapters vanished from this dashboard. So
   *  `milestones.length` is NOT "how many chapters are open" any more: every
   *  consumer that means that filters on `status === "open"` — the picker's
   *  count and Monitor's `chapters` prop both do, and the smoke test pins it. */
  milestones: Milestone[];
  /** How many chapters have landed in total, behind `milestones`' cap.
   *
   *  OPTIONAL for the usual reason (types.ts header): a board one version
   *  behind sends neither this nor any landed chapter at all. Consumers read
   *  `?? 0`, and absent then says the true thing about that board — this screen
   *  can reach no landed chapter. `verbs/pulse.py::run`. */
  landed_total?: number;
  groups: BoardGroups;
  team: TeamMember[];
  hours: ReportPayload | null; // only when the call passed window=
  /** How many closed cards the chapter really has, behind `groups.done`'s cap.
   *
   *  OPTIONAL, and not because `pulse.py::run` may omit it — at this version it
   *  always sends the key. It is optional because a board one version BEHIND
   *  does not: the field was added in a1d1005 alongside the `done` group itself,
   *  and a dashboard `join`ed to a board that has not been redeployed since gets
   *  neither. This is the third instance of the drift the header describes
   *  (`Milestone.criteria` crashed with `Cannot read properties of undefined`
   *  before it was made optional; `ReviewingRow.review_since` was written
   *  optional from the start). Consumers read `?? 0` — absent and `0` say the
   *  same thing to a reader: nothing closed that this screen can count. */
  done_total?: number;
  /** Where this repo lives on the web, so a sha can become a link.
   *
   *  Written ONCE by the side that has a clone (`taskops init` / `taskops join`
   *  read `git remote get-url origin`), never read from a repo at render time —
   *  a remote dashboard has none. TWICE optional, and both reasons are real:
   *  a board one version behind never recorded it, and a repo with NO origin
   *  never will. Absent means exactly one thing to a reader — draw plain text,
   *  no links — so there is nothing to distinguish and no fallback beyond `?.`.
   *
   *  `host` is the key that picks a link template (`github.com` → `/commit/x`,
   *  `gitlab.com` → `/-/commit/x`), which is why it is stored beside `url`
   *  instead of being re-parsed out of it by every consumer.
   *
   *  @source `verbs/project.py::_value`, via `verbs/pulse.py::run` */
  repo?: { host: string; slug: string; url: string } | null;
  seq: number;
  pulse: Pulse;
}

/* ── card (verbs/card.py::run → verbs/_context.py::dossier) ──────────────── */

/** How a card stands with its reviewer — `core/review.py::Standing`, sent as a
 *  plain dict and only when it was ever submitted.
 *
 *  @source `core/review.py::Standing`, sent by `verbs/_context.py::dossier` */
export interface Standing {
  submitted_at: number;
  submitted_by: string;
  verdict: string; // "" | "pass" | "changes"
  note: string;
  reviewed_by: string;
  reviewed_at: number;
}

/** A dependency, a dependent or a subtask, resolved to something readable.
 *
 *  @source `verbs/_context.py::_brief` */
export interface CardBrief {
  id: string;
  title: string;
  status: string;
  assignee?: string; // absent on the "(unknown)" placeholder
}

/** The parent card, with the sentence that makes this one's spec make sense.
 *
 *  @source `verbs/_context.py::_epic` */
export interface Epic {
  id: string;
  title: string;
  spec: string;
  status: string;
}

/** Another open card claiming the same FILES. A warning, never a lock.
 *
 *  @source `verbs/_context.py::collisions` */
export interface Collision {
  id: string;
  title: string;
  files: string[]; // the shared ones only
  holder: string; // the live holder, else whoever it was handed to
  started: boolean; // true when that holder is a live lease
}

/** Who else is working right now, and on what.
 *
 *  @source `verbs/_context.py::elsewhere` */
export interface Elsewhere {
  id: string;
  title: string;
  holder: string;
  milestone: string;
}

/** A `commit` event's body — `_facts.commits_of` sends the bodies, not the events.
 *
 *  @source a `commit` event body, selected by `verbs/_facts.py::commits_of` */
export interface CommitRef {
  sha: string;
  subject: string;
  [key: string]: unknown; // an event body is open; extras are kept
}

/** @source `verbs/card.py::run` → `verbs/_context.py::dossier` */
export interface CardPayload {
  card: Card;
  state: CardState;
  standing: Standing | null;
  milestone: Milestone | null;
  history: Event[]; // complete, in order, never cut
  resume: string; // the previous worker's released note, "" if there is none
  commits: CommitRef[];
  merged_into: string; // the branch it landed on, "" if it has not
  epic: Epic | null;
  seconds: number; // how long the card was WORKED, a floor
  blockers: CardBrief[];
  blocks: CardBrief[];
  subtasks: CardBrief[];
  collisions: Collision[];
  elsewhere: Elsewhere[];
  lease: Lease | null;
  branch: string;
  worktree: string;
  pulse: Pulse;
}

/** `card` answers a SEARCH instead when the call passed query=.
 *
 *  @source `verbs/card.py::_search` */
export interface SearchHit {
  id: string;
  title: string;
  state: CardState;
  assignee: string;
  holder: string | null;
  matched: "title" | "spec";
}

/** @source `verbs/card.py::run` when the call passed `query=` */
export interface SearchPayload {
  query: string;
  matches: SearchHit[];
}

/* ── report (verbs/report.py::summary) ───────────────────────────────────── */

/** @source `verbs/report.py::_by_actor`, formatted by `core/hours.py` */
export interface ActorHours {
  seconds: number;
  human: string; // already formatted by core/hours.py — never re-derive it
  cards: string[];
}

/** @source `verbs/report.py::_day` */
export interface ReportDay {
  day: string; // the calendar label from core/hours.py::windows
  by_actor: Record<string, ActorHours>;
  closed: string[]; // card ids that reached done that day
  commits: number;
}

/** @source `verbs/report.py::summary` */
export interface ReportPayload {
  from: number;
  to: number;
  days: ReportDay[];
  by_actor: Record<string, ActorHours>;
  total: { seconds: number; closed: number };
}

/* ── mentions (verbs/pulse.py::mentions) ─────────────────────────────────── */

/** @source `verbs/pulse.py::mentions` */
export interface MentionsPayload {
  actor: string; // the actor the server RESOLVED — the caller could not have known it
  mentions: MentionRow[];
}
