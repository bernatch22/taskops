/* One task, in a drawer. The ORDER matches the terminal renderer for the same reason it exists
 * there: a reader may stop early, so what they must not miss comes first — what this is, then
 * what would make them collide with somebody, then the spec, then the thread. */

import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  AgentEntry, CommitRef, ContextSlice, Event, Task, TaskView,
} from "../contracts";
import { Actor, MARK, Priority, ago } from "./bits";
/* The fact renderer and the chip live in `facts`, not in the panel that hosts them: the same
 * fact is drawn here, in the project block, in a chapter block and on a profile, and a
 * second renderer would drift — the first thing a copy drops is the id, which is the only
 * part of a fact anybody can act on. */
import { FactBlock, Waiting, countLine } from "./facts";

/* Every move a PERSON makes by hand. `in_progress` was here and is gone with the status; a
 * button that 400s is worse than no button. `ready` is the reject — a card in review going
 * back to its worker, which keeps its assignee, unlike `released`. */
const CLOSING = ["review", "done", "ready", "blocked", "released", "cancelled"];
const LABELS: Record<string, string> = { ready: "send back", released: "hand back" };

export function TaskPanel({ view, readonly, people, onClose, onOpen, onDone }: {
  view: TaskView;
  readonly: boolean;
  /* The actor ids already on this board. The registry says which SPECIALISTS exist; nothing on
   * the server knows which PEOPLE do, so the board itself is the only honest source. */
  people: string[];
  onClose: () => void;
  onOpen: (id: string) => void;
  onDone: () => void;
}): JSX.Element {
  const { task } = view;
  /* ONE fetch per card, read HERE rather than inside the section that shows the facts — because two
   * parts of this drawer need the same answer now: the chapter the card belongs to, which goes
   * under the title, and what applies to it, which goes above the spec. Two components fetching it
   * would be two requests for one card, and the second would arrive after the first had rendered. */
  const slice = useSlice(task.id);
  /* Escape closes it, and it is the TOP surface: a card opened from a profile sits above that
   * modal, and `Overlay` stands down while a drawer exists. Without this, Escape did nothing
   * here at all — the only way out was the ✕ or the backdrop. */
  useEffect(() => {
    const key = (e: KeyboardEvent): void => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="drawer" onClick={onClose}>
      <div className="panel" onClick={(click) => click.stopPropagation()}>
        <header className="panel-head">
          <div>
            <code className="id big">{task.id}</code>
            <Priority value={task.priority} />
            <span className={`status status-${task.status}`}>
              {MARK[task.status]} {task.status}
            </span>
          </div>
          <button className="close" onClick={onClose} aria-label="close">✕</button>
        </header>

        <h1>{task.title}</h1>
        <Belongs slice={slice} />
        <p className="meta dim">
          created by <Actor id={task.created_by} /> · {ago(task.created)}
          {task.assignee ? <> · assigned to <Actor id={task.assignee} /></> : null}
          {task.reviewer ? <> · reviewed by <span className="chip">{task.reviewer}</span></> : null}
          {view.lease ? <> · held by <Actor id={view.lease.actor} /></> : null}
        </p>

        {view.lease?.branch ? (
          <pre className="cmd">git switch {view.lease.branch}</pre>
        ) : null}

        {view.neighbours.length > 0 ? (
          <section className="warn">
            <h3>⚠ Also touching these files</h3>
            <ul>
              {view.neighbours.map((other) => (
                <li key={other.id}>
                  <button className="linkish" onClick={() => onOpen(other.id)}>{other.id}</button>
                  {" "}<span className="dim">({other.status}, {other.created_by})</span> — {other.title}
                </li>
              ))}
            </ul>
            <p className="dim">Message them before editing a shared file, not after the merge.</p>
          </section>
        ) : null}

        <Applies slice={slice} />

        <section>
          <h3>Spec</h3>
          {task.spec
            ? <pre className="spec">{task.spec}</pre>
            : <p className="dim">No spec. An agent picking this up has to guess — that is worth fixing.</p>}
        </section>

        {task.files.length > 0 ? (
          <section>
            <h3>Files</h3>
            <div className="files">{task.files.map((f) => <code key={f}>{f}</code>)}</div>
          </section>
        ) : null}

        <Graph view={view} onOpen={onOpen} />

        {view.commits.length > 0 ? (
          <section>
            <h3>Commits <span className="tally">{view.commits.length}</span></h3>
            <ul className="commits">
              {view.commits.map((commit) => <Commit commit={commit} key={commit.sha} />)}
            </ul>
          </section>
        ) : null}

        <Thread thread={view.thread} />
        {readonly
          ? <p className="dim">Read-only — start it without <code>--readonly</code> to reply.</p>
          : <>
              <Assign task={task} people={people} onDone={onDone} />
              <Compose task={task} onDone={onDone} />
            </>}
      </div>
    </div>
  );
}

/* The card's slice: what the standing context says about THIS card, exactly as the server hands it
 * to the worker holding it (`usecases.context_for`, over `GET /api/task/context`).
 *
 * ONE fetch per card. Not per render and deliberately not on socket events: a standing fact
 * changes about once a week, while a board event arrives every few seconds. */
function useSlice(id: string): ContextSlice | null {
  const [slice, setSlice] = useState<ContextSlice | null>(null);
  useEffect(() => {
    let alive = true;
    /* Cleared first: the drawer stays mounted when you follow a link to another card, so without
     * this the new card would show the previous card's context until its own answer landed. */
    setSlice(null);
    api.taskContext(id).then((got) => { if (alive) setSlice(got); }).catch(() => {});
    return () => { alive = false; };
  }, [id]);
  return slice;
}

/* WHICH CHAPTER this card belongs to, under the title — and it is one line because it is one fact
 * with consequences: the rules below are that chapter's, they end when it does, and a card whose
 * milestone somebody misread is a card working under somebody else's rules invisibly.
 *
 * A card written before this model has none, and it says so rather than showing nothing: those
 * cards are real, they are in somebody's queue, and a blank where every other card names a chapter
 * reads as a bug in the drawer instead of as a card nobody has attached yet.
 *
 * Nothing at all while the slice is in flight — the alternative is a placeholder that flashes on
 * every card open, for a line that is already there a moment later. */
function Belongs({ slice }: { slice: ContextSlice | null }): JSX.Element | null {
  if (!slice) return null;
  const chapter = slice.milestone;
  const counts = chapter ? countLine(slice.counts[chapter.id]) : "";
  return (
    <p className="meta dim">
      <span className="context-mark">◎</span>{" "}
      {chapter ? chapter.text : <em>(sin milestone)</em>}
      {chapter?.horizon ? <> · <span className="context-horizon">by {chapter.horizon}</span></> : null}
      {counts ? <> · {counts}</> : null}
      {chapter?.state === "review" ? <> · <Waiting /></> : null}
    </p>
  );
}

/* What applies HERE, in the order a reader must meet it: the project's rules, then this chapter's,
 * then what was settled about this card's subject.
 *
 * It lived in exactly one place a person could read (the context modal) and nowhere near the work:
 * you could open a card and have no idea what the project had already settled about it, while the
 * agent holding it had been handed precisely that. Now both read the same answer.
 *
 * ABOVE the spec, which is the same argument as the file order at the top of this module: a reader
 * stops early, and something already settled read AFTER the plan it should have shaped is a
 * decision re-litigated in the diff.
 *
 * THE ORDER IS THE MEANING, and it is why this is three sections and not one flat list. A project
 * rule is true in a year; a chapter's rule dies when the chapter ships; a decision about this
 * card's labels is an answer somebody already gave to the question in front of you. A worker
 * deciding whether it may reconsider something needs to know which of the three it is holding, and
 * a merged list makes the first kind look like the third — which is how a permanent rule got
 * re-litigated in a diff. The server decides what REACHES the card; this decides nothing, it only
 * keeps the levels apart. */
function Applies({ slice }: { slice: ContextSlice | null }): JSX.Element | null {
  if (!slice) return null;
  /* Everything settled that reaches this card, whatever its level: the project's decisions are
   * permanent and its chapter's are not, but both are answers to "has this been decided", which is
   * the question a reader is asking here. The chapter's notes join them for the same reason — the
   * server already narrowed all three by this card's subject. */
  const settled = [...slice.project_decisions, ...slice.decisions, ...slice.notes];
  const blocks: [string, string, typeof settled][] = [
    ["Rules", "the project's — every card, every milestone, no exceptions", slice.project_rules],
    ["This milestone's rules", "true until this chapter ships", slice.rules],
    ["Settled for this card", "decisions and notes that name its labels or its files", settled],
  ];
  const shown = blocks.filter(([, , facts]) => facts.length > 0);
  /* Nothing in force for this card renders NOTHING — no heading, no "(none)", the same way the
   * context modal omits an empty group. A card the project has said nothing about is not doing
   * anything wrong, and an empty section on every card is a feature announcing itself. */
  if (!shown.length) return null;
  return (
    <>
      {shown.map(([title, note, facts]) => (
        <section key={title}>
          <h3>{title} <span className="dim">{note}</span></h3>
          <ul className="ctx-list">
            {facts.map((fact) => <FactBlock key={fact.id} fact={fact} />)}
          </ul>
        </section>
      ))}
    </>
  );
}

/* A commit with its subject and the files it touched. The subject is the point: this rendered bare
 * twelve-character hashes for a while, which made a finished card look like it had recorded nothing
 * while the event underneath had carried all of this the whole time. */
function Commit({ commit }: { commit: CommitRef }): JSX.Element {
  return (
    <li className="commit">
      <div className="commit-head">
        <code className="sha">{commit.sha.slice(0, 12)}</code>
        <span className="subject">{commit.subject || "(no subject)"}</span>
      </div>
      {commit.files.length > 0 ? (
        <div className="files">
          {commit.files.slice(0, 6).map((path) => <code key={path}>{path}</code>)}
          {commit.files.length > 6
            ? <code className="dim">+{commit.files.length - 6} more</code> : null}
        </div>
      ) : null}
    </li>
  );
}

function Graph({ view, onOpen }: { view: TaskView; onOpen: (id: string) => void }): JSX.Element | null {
  const groups: [string, Task[]][] = [
    /* First, and it was missing entirely: what this card is FOR is the sentence that makes its
     * spec make sense, and a spec read without it is how a subtask gets solved correctly for
     * the wrong problem. Wrapped in a list because every other row here is one — the shape is
     * "related cards", and one of them is not worth a second component. */
    ["Part of", view.epic ? [view.epic] : []],
    ["Waiting on", view.blocked_by],
    ["Blocking", view.blocks],
    ["Subtasks", view.children],
  ];
  const shown = groups.filter(([, tasks]) => tasks.length > 0);
  if (shown.length === 0) return null;
  return (
    <>
      {shown.map(([label, tasks]) => (
        <section key={label}>
          <h3>{label} <span className="tally">{tasks.length}</span></h3>
          <ul className="graph">
            {tasks.map((other) => (
              <li key={other.id}>
                <span className="mark">{MARK[other.status]}</span>
                <button className="linkish" onClick={() => onOpen(other.id)}>{other.id}</button>
                {" — "}{other.title}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

function Thread({ thread }: { thread: Event[] }): JSX.Element {
  return (
    <section>
      <h3>Thread <span className="tally">{thread.length}</span></h3>
      {thread.length === 0 ? <p className="dim">Nothing said yet.</p> : (
        <ol className="thread">
          {thread.map((event) => (
            <li key={event.id}>
              <div className="msg-head">
                <Actor id={event.actor} />
                {event.kind === "message" ? <span className="tag">directed</span> : null}
                <span className="dim">{ago(event.ts)}</span>
              </div>
              <p className="msg">{String(event.body["text"] ?? "")}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/* Giving the card to somebody. Its own section rather than another button in the row below,
 * because it is the one control here that changes who the SCHEDULER offers the card to — an
 * assigned card is invisible to every other agent, which is a heavier thing than a comment.
 *
 * The picker has two halves and they are not interchangeable: the registry SPECIALISTS, which the
 * server knows and mints an actor id for (`agent:<you>/<name>`), and the PEOPLE already on this
 * board, which nothing on the server knows — so their ids are sent verbatim. Anything else is
 * typed in the same field: free-form is the normal case for an ad-hoc worker, and only a bare
 * name that looks like a specialist is measured against the registry. */
function Assign({ task, people, onDone }: {
  task: Task;
  people: string[];
  onDone: () => void;
}): JSX.Element {
  const [agents, setAgents] = useState<AgentEntry[]>([]);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  const [asked, setAsked] = useState("");

  /* Fetched when the panel opens, not held in the shared state: the registry is read once per
   * card somebody actually assigns, and it does not change while a board is open. A failure is
   * SILENT on purpose — the field still works by hand, and a red line about a picker nobody was
   * using would be noise on top of a card. */
  useEffect(() => {
    let alive = true;
    api.agents().then((listed) => { if (alive) setAgents(listed); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  async function assign() {
    setBusy(true);
    setFailed("");
    setAsked("");
    try {
      const answer = await api.assign(task.id, pick.trim());
      /* A specialist is a REQUEST the orchestrator fulfils in its own order, so the button
       * must not report "assigned" about a decision nobody has made yet. A dev is direct —
       * bookkeeping spawns nothing — and comes back with `assignee`. */
      if (answer.requested) setAsked(answer.requested);
      setPick("");
      onDone();
    } catch (failure) {
      /* The server's message, verbatim — a refused assignee names every specialist this project
       * has, which is the only thing that makes a typo fixable without leaving the board. */
      setFailed(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="compose">
      <h3>Assign {task.assignee ? <span className="chip">{task.assignee}</span> : null}</h3>
      <input
        value={pick}
        list="assignees"
        /* For a specialist this is a REQUEST — the orchestrator dispatches in its own
         * order — and the caption must not claim otherwise, or the board says "assigned"
         * about a decision nobody has made yet. */
        placeholder={task.assignee ? "reassign to: a specialist, dev:ana, agent:ana/one"
                                   : "a specialist, dev:ana, agent:ana/one"}
        onChange={(change) => setPick(change.target.value)}
      />
      <datalist id="assignees">
        {agents.map((agent) => (
          <option value={agent.name} key={agent.name}>{agent.description}</option>
        ))}
        {people.map((who) => <option value={who} key={who} />)}
      </datalist>
      <div className="actions">
        <button className="primary" disabled={busy || !pick.trim()} onClick={() => void assign()}>
          {task.assignee ? "Reassign" : "Assign"}
        </button>
        {asked ? <span className="dim">asked the session to dispatch it to {asked}</span> : null}
      </div>
      {failed ? <p className="failed">{failed}</p> : null}
    </section>
  );
}

/* Talking to the agents, and changing a status. Both in one place because they are one thought
 * for the person doing it: "I have read this and here is my response". */
function Compose({ task, onDone }: { task: Task; onDone: () => void }): JSX.Element {
  const [text, setText] = useState("");
  const [mentions, setMentions] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");

  async function act(status?: string) {
    setBusy(true);
    setFailed("");
    try {
      if (status) await api.status(task.id, status, text);
      else await api.comment(task.id, text, mentions.split(",").map((m) => m.trim()).filter(Boolean));
      setText("");
      setMentions("");
      onDone();
    } catch (failure) {
      /* The server's message, verbatim. A refused `done` explains exactly what is missing, and
       * replacing that with "Failed" throws away the only part worth reading. */
      setFailed(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="compose">
      <h3>Reply</h3>
      <textarea
        value={text}
        placeholder="What the next agent — or you in three weeks — needs to know. Notify somebody below and this reaches the Claude session that is open."
        onChange={(change) => setText(change.target.value)}
        rows={3}
      />
      <input
        value={mentions}
        placeholder="notify — reaches an agent's inbox AND your open Claude session: dev:berna, agent:ana/api"
        onChange={(change) => setMentions(change.target.value)}
      />
      <div className="actions">
        <button className="primary" disabled={busy || !text.trim()} onClick={() => void act()}>
          Comment
        </button>
        {CLOSING.map((status) => (
          <button key={status} disabled={busy} onClick={() => void act(status)}
                  title={status === "released" ? "hand it back to the queue" : `set ${status}`}>
            {LABELS[status] ?? status.replace("_", " ")}
          </button>
        ))}
      </div>
      {failed ? <p className="failed">{failed}</p> : null}
    </section>
  );
}
