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
 * that the board on the other end is the same version. */

/** The only verbs this client speaks. The board's registry has more; the
 *  dashboard is read-only except for the ONE write (`update` with comment=), and
 *  a union rather than `string` is what makes "do not invent a verb" a compile
 *  error instead of a 400 nobody sees. */
export type RpcVerb = "board" | "card" | "report" | "mentions" | "update";

/* ── the stored rows (core/types.py) ─────────────────────────────────────── */

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

export interface Milestone {
  id: string;
  title: string;
  goal: string;
  rules: string[];
  reviews?: boolean;
  branch: string;
  status: string;
  created: number;
}

export interface Event {
  id: string;
  task: string; // "project" for board-level facts
  actor: string;
  kind: string; // KINDS in core/types.py
  body: Record<string, unknown>; // open on purpose: an unknown kind is stored intact
  ts: number;
}

export interface Lease {
  task: string;
  actor: string;
  branch: string;
  acquired: number;
  expires: number;
}

/** Everything a card can be ON SCREEN. Only the first three are stored; the rest
 *  are derived by `core/graph.py` from the graph, the live lease and the thread. */
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
 *  the first, and that difference is the whole group. */
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

/** A blocked row carries what it is waiting for — `graph.blockers`. */
export interface BlockedRow extends BoardRow {
  waiting_on: string[];
}

/** review and changes carry the REASON, not just the id: the submit note is
 *  empty on `review`, and on `changes` it is the reviewer's words verbatim. */
export interface VerdictRow extends BoardRow {
  text: string;
  holder: string | null; // on these two it is the REVIEW lease holder
}

export interface ReviewingRow extends BoardRow {
  holder: string | null; // likewise: whoever is checking right now
}

/** A pending mention — `pulse.py::_mentions`. Not a card row: it is the comment
 *  that named you, and it is the one group the milestone filter does not apply to. */
export interface MentionRow {
  id: string; // the card the comment lives on
  title: string; // "" when the card is unknown to this board
  by: string;
  text: string;
  ts: number;
}

/** The nine groups, in the order `pulse.py` builds them — which IS the order to
 *  act in, so a view that reorders them is contradicting the board. */
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
] as const satisfies readonly (keyof BoardGroups)[];

export type GroupName = (typeof GROUP_ORDER)[number];

export interface TeamMember {
  actor: string;
  seen: number;
  ago: number; // seconds
}

/** The heartbeat that rides on every result — `_context.py::pulse`. */
export interface Pulse {
  milestone: string; // the TITLE, "" when no milestone is in scope
  goal: string;
  counts: { doing: number; ready: number; blocked: number; stalled: number; done: number };
  mentions: number; // addressed to the reader of THIS call, unanswered
}

export interface BoardPayload {
  milestone: Milestone | null;
  milestones: Milestone[]; // the open ones only
  groups: BoardGroups;
  team: TeamMember[];
  hours: ReportPayload | null; // only when the call passed window=
  seq: number;
  pulse: Pulse;
}

/* ── card (verbs/card.py::run → verbs/_context.py::dossier) ──────────────── */

/** How a card stands with its reviewer — `core/review.py::Standing`, sent as a
 *  plain dict and only when it was ever submitted. */
export interface Standing {
  submitted_at: number;
  submitted_by: string;
  verdict: string; // "" | "pass" | "changes"
  note: string;
  reviewed_by: string;
  reviewed_at: number;
}

/** A dependency, a dependent or a subtask, resolved to something readable. */
export interface CardBrief {
  id: string;
  title: string;
  status: string;
  assignee?: string; // absent on the "(unknown)" placeholder
}

/** The parent card, with the sentence that makes this one's spec make sense. */
export interface Epic {
  id: string;
  title: string;
  spec: string;
  status: string;
}

/** Another open card claiming the same FILES. A warning, never a lock. */
export interface Collision {
  id: string;
  title: string;
  files: string[]; // the shared ones only
  holder: string; // the live holder, else whoever it was handed to
  started: boolean; // true when that holder is a live lease
}

/** Who else is working right now, and on what. */
export interface Elsewhere {
  id: string;
  title: string;
  holder: string;
  milestone: string;
}

/** A `commit` event's body — `_facts.commits_of` sends the bodies, not the events. */
export interface CommitRef {
  sha: string;
  subject: string;
  [key: string]: unknown; // an event body is open; extras are kept
}

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

/** `card` answers a SEARCH instead when the call passed query=. */
export interface SearchHit {
  id: string;
  title: string;
  state: CardState;
  assignee: string;
  holder: string | null;
  matched: "title" | "spec";
}

export interface SearchPayload {
  query: string;
  matches: SearchHit[];
}

/* ── report (verbs/report.py::summary) ───────────────────────────────────── */

export interface ActorHours {
  seconds: number;
  human: string; // already formatted by core/hours.py — never re-derive it
  cards: string[];
}

export interface ReportDay {
  day: string; // the calendar label from core/hours.py::windows
  by_actor: Record<string, ActorHours>;
  closed: string[]; // card ids that reached done that day
  commits: number;
}

export interface ReportPayload {
  from: number;
  to: number;
  days: ReportDay[];
  by_actor: Record<string, ActorHours>;
  total: { seconds: number; closed: number };
}

/* ── mentions (verbs/pulse.py::mentions) ─────────────────────────────────── */

export interface MentionsPayload {
  actor: string; // the actor the server RESOLVED — the caller could not have known it
  mentions: MentionRow[];
}
