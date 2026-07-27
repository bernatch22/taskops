/* The agent's conversation, in the same sidebar the task uses.
 *
 * ONE sidebar, two views — not a second drawer on top of the first. Stacked drawers make a person
 * track which layer they are closing, and there is never a reason to see a task and its transcript at
 * the same time: reading the conversation IS reading about the task.
 *
 * Shaped by what somebody is actually asking, which is not "replay everything": what did it decide,
 * what did it touch, and how did it end. So thinking is marked as thinking, a tool call is one line
 * naming the file, and a tool RESULT is collapsed to a couple of lines — results are the longest
 * entries in any transcript and the least read. */

import { useEffect, useState } from "react";
import { api, ApiFailure } from "../api";
import type { LogEntry, SessionLog } from "../contracts";
import { ago } from "./bits";

export function Conversation({ task, onBack }: {
  task: string;
  onBack: () => void;
}): JSX.Element {
  const [log, setLog] = useState<SessionLog | null>(null);
  const [failed, setFailed] = useState("");

  useEffect(() => {
    let live = true;
    api.log(task)
      .then((found) => { if (live) setLog(found); })
      .catch((error: unknown) => {
        if (live) setFailed(error instanceof ApiFailure ? error.message : String(error));
      });
    return () => { live = false; };
  }, [task]);

  return (
    <>
      <header className="panel-head">
        <button className="back" onClick={onBack}>← task</button>
        <code className="id big">{task}</code>
        {log ? (
          <span className="dim meta-count">
            {log.entries.length} entries · {log.sessions.length} session(s)
            {log.truncated ? " · truncated" : ""}
          </span>
        ) : null}
      </header>

      {failed ? <p className="failed">{failed}</p> : null}
      {!log && !failed ? <p className="dim">Reading the transcript…</p> : null}

      {log && log.entries.length === 0 ? (
        <section>
          <h3>No conversation found</h3>
          {/* The reason, not just the absence: the fix is usually $CLAUDE_CONFIG_DIR, because a
            * second Claude Code home is exactly how the first version of this found nothing. */}
          <p className="dim">{log.source}</p>
        </section>
      ) : null}

      {log && log.entries.length > 0 ? (
        <ol className="convo">
          {log.entries.map((entry, index) => (
            <Entry entry={entry} key={`${entry.ts}-${index}`} />
          ))}
        </ol>
      ) : null}
    </>
  );
}

function Entry({ entry }: { entry: LogEntry }): JSX.Element {
  if (entry.kind === "tool") {
    return (
      <li className="turn turn-tool">
        <span className="tool-name">{entry.tool}</span>
        <code className="tool-arg">{entry.text}</code>
      </li>
    );
  }
  if (entry.kind === "result") {
    return <li className="turn turn-result"><code>{firstLines(entry.text)}</code></li>;
  }
  return (
    <li className={`turn turn-${entry.kind}`}>
      <div className="turn-head">
        <span className="who">{LABEL[entry.kind] ?? entry.kind}</span>
        {entry.ts ? <span className="dim">{ago(entry.ts)}</span> : null}
      </div>
      <p className="turn-text">{entry.text}</p>
    </li>
  );
}

const LABEL: Record<string, string> = {
  prompt: "prompt", thinking: "thinking", text: "agent", other: "system",
};

/* Results are the longest entries in a transcript and the least read — a file's contents came back
 * from a Read, and the reader wants what the agent DID with it. */
function firstLines(text: string, keep = 3): string {
  const lines = text.split("\n").filter((line) => line.trim());
  const shown = lines.slice(0, keep).join(" / ");
  return lines.length > keep ? `${shown} …` : shown || "(empty)";
}
