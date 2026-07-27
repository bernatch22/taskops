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
  created: number;
  updated: number;
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

export type EntryKind = "prompt" | "thinking" | "text" | "tool" | "result" | "other";

export interface LogEntry {
  kind: EntryKind;
  text: string;
  /* For a tool call, a one-line summary — which file, which command — never the whole payload. */
  tool: string;
  ts: number;
  session: string;
}

export interface SessionLog {
  task: string;
  sessions: string[];
  entries: LogEntry[];
  /* Where the transcripts were read from. Shown when there is nothing, because an empty pane cannot
   * distinguish "the agent said nothing" from "we looked in the wrong place". */
  source: string;
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

export interface FleetMember {
  actor: string;
  session: string;
  task: string;
  branch: string;
  alive: boolean;
  last_seen: number;
  doing: string;
}

export interface Fleet {
  repo: string;
  members: FleetMember[];
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
