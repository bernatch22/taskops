/* One task, in a drawer. The ORDER matches the terminal renderer for the same reason it exists
 * there: a reader may stop early, so what they must not miss comes first — what this is, then
 * what would make them collide with somebody, then the spec, then the thread. */

import { useState } from "react";
import { api } from "../api";
import type { CommitRef, Event, Task, TaskView } from "../contracts";
import { Actor, MARK, Priority, ago } from "./bits";

const CLOSING = ["in_progress", "review", "done", "blocked", "released", "cancelled"];

export function TaskPanel({ view, readonly, onClose, onOpen, onDone }: {
  view: TaskView;
  readonly: boolean;
  onClose: () => void;
  onOpen: (id: string) => void;
  onDone: () => void;
}): JSX.Element {
  const { task } = view;
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
        <p className="meta dim">
          created by <Actor id={task.created_by} /> · {ago(task.created)}
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
          ? <p className="dim">Read-only studio — start it without <code>--readonly</code> to reply.</p>
          : <Compose task={task} onDone={onDone} />}
      </div>
    </div>
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
        placeholder="What the next agent — or you in three weeks — needs to know."
        onChange={(change) => setText(change.target.value)}
        rows={3}
      />
      <input
        value={mentions}
        placeholder="notify (optional): agent:ana/api-1, dev:ana"
        onChange={(change) => setMentions(change.target.value)}
      />
      <div className="actions">
        <button className="primary" disabled={busy || !text.trim()} onClick={() => void act()}>
          Comment
        </button>
        {CLOSING.map((status) => (
          <button key={status} disabled={busy} onClick={() => void act(status)}
                  title={status === "released" ? "hand it back to the queue" : `set ${status}`}>
            {status.replace("_", " ")}
          </button>
        ))}
      </div>
      {failed ? <p className="failed">{failed}</p> : null}
    </section>
  );
}
