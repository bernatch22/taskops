/* The wire types, mirroring `src/taskops/contracts/` by hand.
 *
 * By hand and not generated, deliberately: there are eleven of them, they change rarely, and a
 * generator would be a build step plus a toolchain plus a thing to debug at 2am for types a
 * person can read in one screen. The Python side is TypedDicts, so what arrives IS this shape —
 * there is no serialisation layer between them to disagree.
 *
 * If these drift from the Python, the symptom is a field reading `undefined` in the UI. The fix
 * is here, not a cast at the call site. */

export type Status =
  | "backlog" | "ready" | "claimed"
  | "blocked" | "review" | "done" | "cancelled";

export const STATUSES: Status[] = [
  "backlog", "ready", "claimed", "blocked", "review", "done", "cancelled",
];

export interface Task {
  /* The chapter it belongs to, or "" for one planned before milestones existed. Every new card
   * names one — that is what makes a chapter a todo-list, and what bounds a worker's slice. */
  milestone: string;
  id: string;
  title: string;
  spec: string;
  status: Status;
  priority: number;
  parent: string | null;
  labels: string[];
  files: string[];
  created_by: string;
  /* Whose card it is — an actor id, or "". Not a lease: a lease belongs to a process that is
   * alive, this is a decision that outlives one. The scheduler offers an assigned card to
   * nobody else, which is why the board draws it. */
  assignee: string;
  /* Who closes it: `human`/`dev:…` for a person, a registered agent's name for a specialist,
   * empty for the project default. It is POLICY, not a hint — the engine refuses a `done` that
   * disagrees with it — so it belongs where the decision is read. */
  reviewer: string;
  created: number;
  updated: number;
}

/* One entry of the specialist registry, as `GET /api/agents` serves it — the picker's whole
 * vocabulary. Never the agent file's text: that is what materialisation needs, not a dropdown. */
export interface AgentEntry {
  name: string;
  description: string;
  labels: string[];
}

export interface Lease {
  task: string;
  actor: string;
  session: string;
  branch: string;
  acquired: number;
  expires: number;
}

export interface Event {
  id: string;
  task: string;
  actor: string;
  kind: string;
  /* Open by design on the Python side: a reader that does not know a kind must still be able to
   * store and forward it, because a newer taskops on a teammate's machine writes kinds this one
   * has never seen. So `unknown` here, read defensively at the point of use. */
  body: Record<string, unknown>;
  ts: number;
}

export interface Card {
  task: Task;
  lease: Lease | null;
  blocked_by: number;
  blocks: number;
  commits: number;
}

export interface Column {
  status: Status;
  cards: Card[];
}

export interface Board {
  repo: string;
  columns: Column[];
  ready: number;
  total: number;
}

export interface ActorRoll {
  actor: string;
  /* Distinct tasks, not events: forty comments on one card is less work than four cards closed,
   * and counting events would rank them the other way round. */
  tasks: number;
  commits: number;
  comments: number;
  done: number;
  first_seen: number;
  last_seen: number;
}

export interface Activity {
  repo: string;
  since: number;
  /* Newest first — a timeline is read from the top. */
  events: Event[];
  titles: Record<string, string>;
  actors: ActorRoll[];
  kinds: string[];
  truncated: boolean;
}

export interface CommitRef {
  sha: string;
  subject: string;
  files: string[];
  actor: string;
  ts: number;
}

export interface TaskView {
  task: Task;
  lease: Lease | null;
  blocked_by: Task[];
  blocks: Task[];
  children: Task[];
  /* The card this one is PART OF, resolved. `task.parent` is only an id, and an id is not
   * something anybody can read — so a child never showed what it belonged to while its parent
   * had listed it all along. One direction of a tree is not a tree. */
  epic: Task | null;
  neighbours: Task[];
  thread: Event[];
  commits: CommitRef[];
  history: Event[];
}

export interface Config {
  version: string;
  repo: string;
  readonly: boolean;
}

export interface ApiError {
  error: string;
  code: string;
}

/* The reports. `ReportEntry` is a ROW in the list; `ReportFile` is the one you clicked, with its
 * markdown. Two shapes and not one, because a listing that carried thirty dossiers would ship a
 * megabyte of text to draw thirty labels. */
export interface ReportEntry {
  /* Opaque: today it is a date, tomorrow it is a range (`2026-07-22..2026-07-28`, `all`). Pass it
   * back as it came — never parse it. */
  label: string;
  path: string;
  exists: boolean;
  stale: boolean;
  missing_events: number;
  has_narration: boolean;
  bytes: number;
}

/* An EPHEMERAL frame, mirroring `contracts/wire.py`. It arrives on the live socket, under
 * `type: "narration"`, and it is the opposite of an `Event`: nothing stored it, nothing replays
 * it, and a browser that reconnects has simply missed whatever went by. The file on disk is the
 * durable copy — this is the window onto it being written. */
export interface WireMessage {
  /* `narration.delta` | `narration.pass` | `narration.done` | `narration.failed`. Open, like
   * `Event.kind`: an unknown one is dropped, never guessed at. */
  kind: string;
  /* Which report. Two narrations can be in flight, and a delta with no label would be appended
   * to whichever panel happens to be open. */
  label: string;
  text: string;
}

/* What `POST /api/report/digest` answers now: it STARTED. The prose does not come back on the
 * response — it arrives frame by frame on the socket, because the call takes minutes. */
export interface DigestStarted {
  status: string;
  label: string;
}

export interface ReportFile {
  date: string;
  path: string;
  /* The file when there is one, otherwise the dossier that WOULD be written — so a day nobody
   * wrote up still has something to read instead of an empty pane and a button. */
  dossier_md: string;
  exists: boolean;
  stale: boolean;
  missing_events: number;
}

/* ── the standing context: what a worker must know that its card cannot carry ─────────────── */

/* One fact, as `storage.context` reconstructs it from its event. `id` is the EVENT id — the
 * content hash — which is why it is the same string on every machine and what `retire` takes. */
export interface Fact {
  id: string;
  sort: "objective" | "rule" | "decision" | "note";
  text: string;
  /* The scope: which cards this reaches. Empty means every card in its chapter. Rules are never
   * narrowed by it — a decision that misses a card costs a re-litigation, a rule that misses one
   * costs the breakage it existed to prevent. */
  labels: string[];
  files: string[];
  horizon: string;
  owner: string;
  /* WHERE it lives, and therefore how long. `project` outlives every milestone; `milestone`
   * belongs to the chapter open when it was written and leaves every slice when that closes. */
  level: "project" | "milestone";
  milestone: string;
  actor: string;
  ts: number;
  retired: boolean;
}

/* A chapter — the thing that ends. Several are active at once on any real board, which is why the
 * slice is bounded by a CARD's chapter rather than by there being only one. `review` still counts
 * as active: an agent reported it finished, and nothing archives on an agent's word. */
export interface Milestone {
  id: string;
  /* Three or five words — what somebody calls this chapter out loud. It is what the selector, a
   * card's badge and the log print. A pre-0.5.0 chapter has no title of its own and the fold maps
   * its one sentence here, so this CAN be long: truncate on display, never in the data. */
  title: string;
  /* What done means, and what is out of scope. Prose, usually an agent's, and "" on a chapter
   * nobody has written it for yet — which is the normal state of one just opened. */
  goal: string;
  horizon: string;
  state: "planned" | "in_force" | "review" | "reached" | "abandoned";
  created_by: string;
  created: number;
  updated: number;
  /* Who VERIFIED it, "" until somebody did. Never the reporter. */
  closed_by: string;
  note: string;
}

/* A project SETTING: a value the engine obeys, validated when it was written. Beside the facts
 * on the wire because they are one question on screen — what has this project already decided —
 * and kept apart in the payload because they are not the same kind of answer. */
export interface Policy {
  name: string;
  value: string;
  actor: string;
  ts: number;
}

/* What is in force for ONE reader — the Python `ContextSlice`, verbatim. `GET /api/context` answers
 * the board's, everything the project has stated; `GET /api/task/context?id=…` answers one CARD's,
 * narrowed to what reaches it. Same shape on purpose, because the card drawer has to show what the
 * worker holding it was handed rather than a second filter over the same facts. */
export interface ContextSlice {
  /* The chapter THIS slice is for: a card's own, or null for the board's overview and for a
   * project that has none yet — a state the UI names rather than hides, since planning refuses
   * without one. Singular even though several may be active: that is the bound. */
  milestone: Milestone | null;
  /* Every chapter being worked on. Read by the board and by an orchestrator, which are the only
   * readers that choose between them; a card's drawer shows `milestone` instead. */
  active: Milestone[];
  /* Cards by status, keyed by milestone id. With several running, "how far along" is a question
   * per chapter. */
  counts: Record<string, Record<string, number>>;
  /* Written down, not started. Titles only — a planned chapter carries no facts and no cards, and
   * showing more of it would let it read as something to work on. */
  planned: Milestone[];
  /* `level: "project"` — permanent, outside every chapter, true whatever anybody is working on.
   * Rendered BEFORE the chapter for that reason: inside it they would look like they expire. */
  project_rules: Fact[];
  project_decisions: Fact[];
  /* The chapter's own. In a CARD slice, `decisions` and `notes` are narrowed by subject and
   * `rules` are not. */
  rules: Fact[];
  decisions: Fact[];
  notes: Fact[];
  /* Whoever asked, when they have an objective of their own. Null in the board's view, which
   * belongs to nobody. */
  yours: Fact | null;
  /* Every dev's objective in the open chapters — the OVERVIEW, never a worker's slice. */
  objectives: Fact[];
}

/* `GET /api/context`. One call, because the panel that shows it is open all the time and two
 * spinners for one panel is two spinners too many. The policies ride along and only here: a
 * setting is project-wide, so it does not narrow to a card and a card's slice does not carry it. */
export interface ContextView extends ContextSlice {
  policies: Policy[];
}
