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
  | "backlog" | "ready" | "claimed" | "in_progress"
  | "blocked" | "review" | "done" | "cancelled";

export const STATUSES: Status[] = [
  "backlog", "ready", "claimed", "in_progress", "blocked", "review", "done", "cancelled",
];

export interface Task {
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
