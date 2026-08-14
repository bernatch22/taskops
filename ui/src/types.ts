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
 * taskops deliberately does not do. Anything stronger than the
 * TypedDict test is that machinery, and it is not worth it. The row test is
 * cheap and is proposed on the card; it is not written here because this card's
 * diff is `.ts`-only. */

/** The only verbs this client speaks. The board's registry has more; the
 *  dashboard is read-only except for the ONE write (`update` with comment=), and
 *  a union rather than `string` is what makes "do not invent a verb" a compile
 *  error instead of a 400 nobody sees.
 *
 *  @source the subset of `verbs/__init__.py::REGISTRY` this client speaks */
export type RpcVerb = "board" | "card" | "report" | "mentions" | "update" | "events";

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
   *  status (`core/types.py::Milestone.criteria`). Shown
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
  /** Which chapter this card belongs to — the milestone's ID, never its title.
   *  `BoardPayload.milestones` carries `{id, title, …}`, so a view that wants
   *  the words maps id → title from that list; a row that is not in it (aged
   *  past the cap) shows nothing rather than a raw id.
   *
   *  OPTIONAL by the header's rule: a board one version behind sends no such
   *  key and every reader must render, degraded, never crash.
   *
   *  @source `verbs/pulse.py::_row` */
  milestone?: string;
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
  /** Who the SERVER resolved this caller as — `anon` on a public board read
   *  with no credential. OPTIONAL for the usual reason (this file's header): a
   *  board one version behind never sends it, and absent must not read as
   *  anonymous — a viewer's window would then be claimed for every board.
   *  @source `verbs/_context.py::pulse` */
  actor?: string;
  milestone: string; // the TITLE, "" when no milestone is in scope
  goal: string;
  counts: { doing: number; ready: number; blocked: number; stalled: number; done: number };
  mentions: number; // addressed to the reader of THIS call, unanswered
}

/** Why one ready card is held out of the wave: the card it clashes with, and
 *  the exact overlap — EITHER the declared files (a fact the planner wrote) OR
 *  the spec terms (an inference from prose), never both, because `wave` reports
 *  the first clash it finds and prefers the fact.
 *
 *  @source `core/seams.py::_clash` */
export interface WaveClash {
  with: string;
  files?: string[];
  terms?: string[];
}

/** @source `core/seams.py::wave`, via `verbs/pulse.py::run` */
export interface Wave {
  /** Card ids, in the board's own priority order — greedy, not optimal. */
  safe: string[];
  held: { id: string; title: string; why: WaveClash }[];
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
  /** Which READY cards are safe to fan out together, and why each of the rest
   *  waits. Derived per read from `groups.take`, never stored, and ADVICE: a
   *  view that greys out a held card, or refuses a dispatch, is contradicting
   *  the rule the whole thing rests on. NOTHING IN THIS DASHBOARD DRAWS IT YET
   *  — the key is declared here so the pane that eventually does starts from
   *  the server's real shape rather than re-guessing it.
   *
   *  OPTIONAL by the header's rule, and NULL on purpose when there are fewer
   *  than two ready cards: absent means "this board is older than the wave",
   *  null means "there was nothing to decide". Consumers must not collapse the
   *  two into one empty state.
   *
   *  @source `verbs/pulse.py::run`, computed by `core/seams.py::wave` */
  wave?: Wave | null;
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
  /** GitHub's flag: `public` means ANONYMOUS READ, and a write always needs a
   *  registered key — there is no third state. OPTIONAL because a board one
   *  version behind sends nothing, and absent means `private`, which is what
   *  every board was before the flag existed. Nothing on this screen is hidden
   *  by it: it says what KIND of board you are looking at, and the reader's own
   *  standing is `pulse.actor`.
   *  @source `verbs/project.py::visibility`, via `verbs/pulse.py::run` */
  visibility?: "public" | "private";
  /** What OPENS this board: the forge repo whose membership enrols a key, and
   *  the access that counts (`taskops join <board> --github`).
   *
   *  OPTIONAL, and here the optionality is the FEATURE rather than the usual
   *  version drift: a board that declared no forge sends no key at all — never
   *  `null` — so absent covers both "this board is invite-only" and "this board
   *  is one version behind", which are the same sentence to a reader: there is
   *  no GitHub door here that this screen can name. Consumers read `?.` and
   *  draw nothing; the refusal a stranger would get is the server's.
   *
   *  `need` is GitHub's own permission key (`push` | `admin`), not a taskops
   *  word — `pull` is deliberately not among them, since read access to a
   *  public repo is not a membership (`core/forge.py`). It is typed as the pair
   *  and not as `string` because the pair is closed on the server side and a
   *  third value could only arrive from a board this bundle cannot understand.
   *
   *  @source `verbs/project.py::forge`, via `verbs/pulse.py::run` */
  forge?: { host: string; repo: string; need: "push" | "admin" };
  /** The chapter's registered reports, NEWEST FIRST, capped at
   *  `verbs/_facts.py::REPORTS_SHOWN` (20) — scoped to the milestone in focus,
   *  board-wide when none is.
   *
   *  OPTIONAL for the header's usual reason: a board one version behind sends
   *  neither key, and absent says the true thing — this screen can reach no
   *  report. Consumers read `?? []` and `?? 0`.
   *
   *  It is a FOLD over `report` events computed per read, never a table
   *  (`core/reports.py::of`), so a report registered a second ago is in the very
   *  next answer with nothing to keep in step.
   *
   *  @source `verbs/pulse.py::run` */
  reports?: FiledReport[];
  /** How many reports the chapter really has, behind `reports`' cap.
   *  @source `verbs/pulse.py::run` */
  reports_total?: number;
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
  /** `+/−` per file, as `gitwork/bind.py::numstat` measured it at commit time.
   *
   *  OPTIONAL, and this one is optional at the SOURCE as well as across
   *  versions: `commit_facts` writes the key only when git could count
   *  something (`if counted:`), so a commit that touches nothing carries no key
   *  rather than an empty wall of zeros — and a board older than tk-dd6a9b
   *  never wrote it at all. `null` for a path means BINARY: git prints `-`
   *  there, and "cannot be counted" is not "nothing changed". */
  numstat?: Record<string, [number, number] | null>;
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

/* ── the diff, from the viewer's own clone (http/gitdoor.py) ─────────────── */

/** One range's diff, as `GET /<board>/git/commit/<ref>` and
 *  `GET /<board>/git/compare/<a>...<b>` answer it — the same object for both,
 *  so ONE renderer draws a commit and a card-as-PR.
 *
 *  @source `gitwork/diff.py::between`, routed by `http/gitdoor.py::answer`
 *
 *  This is NOT on any board payload and never will be: `events.jsonl` stores
 *  references and measures, never content (the chapter's fourth rule). The door
 *  derives it from the repo on demand, and only a host that sits inside one
 *  mounts the door at all — `taskops ui` does, `taskops serve` does not. Every
 *  consumer therefore has to survive not getting this, which is what the
 *  cascade in `links.tsx` is.
 *
 *  `stat` is EXACTLY `gitwork/bind.py::parse_numstat`'s vocabulary — the same
 *  `[added, deleted] | null` a commit event's `numstat` carries, so `Counts`,
 *  `totals()` and `<Numstat>` read a live diff and a stored event with one set
 *  of eyes. `null` is a binary, never `[0, 0]`.
 *
 *  `truncated` with `cap` rather than a silently short string: a cut patch that
 *  does not say so is a lie, and `cap` is there so the pane can word it. */
export interface GitDiff {
  base: string; // 40-hex — the first parent, the merge-base, or git's empty tree
  head: string; // 40-hex
  stat: Record<string, [number, number] | null>;
  patch: string; // unified diff text, whole range or one file
  truncated: boolean;
  cap: number; // bytes; `gitwork/diff.py::CAP`
}

/** One committed FILE at a rev, as `GET /<board>/git/file/<rev>?path=…` answers
 *  it — the bytes of a report, read out of the reader's own clone.
 *
 *  @source `http/gitdoor.py::_file`
 *
 *  `content_type` IS A FIELD AND NEVER A HEADER, and the whole security posture
 *  of the Reports view rests on that: the envelope is `application/json`
 *  whatever the file is, so this origin — the one the token lives in — can never
 *  be made to serve HTML. Deciding what to do with `text/html` is therefore the
 *  READER'S job, and it is done in exactly one place
 *  (`components/reports/ReportFrame.tsx`). A type this door does not know
 *  degrades to `text/plain`, which no renderer executes. `text/markdown` is
 *  the third and it is NOT a third security case: it is drawn by the
 *  dashboard's own renderer, which builds React elements and emits no HTML —
 *  the frame is for bytes that are a page, and prose never becomes one.
 *
 *  `truncated` + `cap` is `GitDiff`'s vocabulary on purpose: the door reuses it
 *  so one renderer can say "this was cut at N bytes" about a patch and about a
 *  report with one sentence. */
export interface GitFile {
  path: string; // repo-relative, always under `.taskops/reports/`
  rev: string; // 40-hex — the rev asked for, RESOLVED
  content_type: "text/html" | "text/markdown" | "text/plain";
  text: string;
  truncated: boolean;
  cap: number; // bytes; `gitwork/patch.py::CAP`
}

/* ── filed reports (core/reports.py, via verbs/_facts.py::reports) ────────── */

/** One report a chapter has: a POINTER to a committed file, never its prose.
 *
 *  @source `core/reports.py::Report`, via `verbs/_facts.py::reports` and
 *  `verbs/pulse.py::run`
 *
 *  NAMED `FiledReport` and not `Report` because `ReportPayload` above is
 *  something else entirely — the HOURS summary (`verbs/report.py::summary`).
 *  Two unrelated things called "report" met in this file; the one this name
 *  belongs to is the one the `filed` verb registers.
 *
 *  `path` + `sha` is the pair, and neither is useful alone: the path is the
 *  string the `/git` file door takes (guaranteed under `.taskops/reports/` by
 *  `core/reports.py::under()`, checked again at that door) and the sha is the
 *  commit to read it AT. A report is fetched, never pushed — `events.jsonl`
 *  grows by a few hundred bytes whatever the narration weighs. */
export interface FiledReport {
  id: string; // the event id — a stable key for a list
  path: string;
  title: string;
  milestone: string;
  sha: string;
  by: string; // who REGISTERED it
  ts: number;
}

/* ── report (verbs/report.py::summary) ───────────────────────────────────── */

/** @source `verbs/report.py::_by_actor`, formatted by `core/hours.py` */
export interface ActorHours {
  seconds: number;
  human: string; // already formatted by core/hours.py — never re-derive it
  cards: string[];
  /** cards this actor closed INSIDE the report's window — not a lifetime figure.
   *  @source `verbs/report.py::_by_actor` (optional: a board one version behind
   *  sends neither key, and absent is not zero) */
  closed?: number;
  /** commits by this actor inside the same window.
   *  @source `verbs/report.py::_by_actor` */
  commits?: number;
  /** The blocks `seconds` is made of — one run of counted intervals on one card,
   *  in wall-clock, so a timesheet can be drawn on a real axis. NOT a second
   *  computation: `core/hours.py::spent` is a fold of the very same list.
   *  Capped at `verbs/report.py::SESSIONS`; `sessions_total` is the real count.
   *  @source `verbs/report.py::_by_actor` (optional: a board one version behind
   *  sends neither key, and then no timesheet is drawn rather than an empty one) */
  sessions?: ActorSession[];
  /** @source `verbs/report.py::_by_actor` */
  sessions_total?: number;
}

/** @source `core/hours.py::Session` */
export interface ActorSession {
  start: number; // epoch seconds
  end: number;
  task: string; // the card the interval was credited to — the one that CLOSED it
  seconds: number;
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

/* ── the log, paged (verbs/events.py) ────────────────────────────────────── */

/** One keyset page of the whole log, newest first.
 *
 *  @source `verbs/events.py::run`
 *
 *  `next` is a `seq` — the cache's rowid — and is passed straight back as
 *  `before=` to get the page behind this one. It is NOT a timestamp and must
 *  never become one: `ts` ties constantly (a plan of nine writes nine events in
 *  one millisecond) and a tying cursor drops or repeats the rows sharing the
 *  boundary instant. `null` means this page is the tail of the log.
 *
 *  `total` is the LOG's length, not this page's — it is what the pane's header
 *  counter draws. The stream is board-wide on purpose: a stored event carries
 *  no milestone, and `task: "project"` rows are board history belonging to no
 *  chapter, so there is nothing here to filter by and nothing is. */
export interface EventPage {
  events: Event[];
  next: number | null;
  total: number;
  /** the board's sequence at the moment of the read (`store/cache.py::head`) */
  head: number;
}
