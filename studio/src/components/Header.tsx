/* The top bar: what you are looking at, whether it is live, and search.
 *
 * The live dot is the most important pixel in the studio. Everything else on screen could be
 * twenty minutes stale and look identical, so a board with no honest liveness signal is a board
 * people stop trusting the first time they are burned by one. */

import { useEffect, useState } from "react";
import { api } from "../api";
import type { Board, Config, Task } from "../contracts";

export function Header({ config, board, live, pulse, onOpen }: {
  config: Config | null;
  board: Board | null;
  live: boolean;
  pulse: number;
  onOpen: (id: string) => void;
}): JSX.Element {
  return (
    <header className="top">
      <div className="brand">
        <span className="logo">✓</span>
        <div>
          <strong>taskops</strong>
          <span className="repo dim">{config ? shorten(config.repo) : "…"}</span>
        </div>
      </div>

      <Search onOpen={onOpen} />

      <div className="top-right">
        {board ? (
          <div className="stats">
            <Stat label="ready" value={board.ready} tone={board.ready > 0 ? "good" : "idle"} />
            <Stat label="total" value={board.total} tone="idle" />
          </div>
        ) : null}
        {config?.readonly ? <span className="badge">read-only</span> : null}
        {/* `key={pulse}` restarts the CSS animation on every event, which is what turns a static
            dot into a visible heartbeat without any JS animation loop. */}
        <span className={`live ${live ? "on" : "off"}`} key={pulse}
              title={live ? "live — streaming changes" : "not connected"}>
          <span className="dot" />
          {live ? "live" : "offline"}
        </span>
      </div>
    </header>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <span className={`stat stat-${tone}`}>
      <b>{value}</b> {label}
    </span>
  );
}

function Search({ onOpen }: { onOpen: (id: string) => void }): JSX.Element {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Task[]>([]);

  /* Debounced, and the timer is cleared on every keystroke AND on unmount. Without the cleanup a
   * fast typist fires a request per character against a server on the same machine as their
   * editor — which is the machine already running the agents. */
  useEffect(() => {
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    const timer = window.setTimeout(() => {
      api.search(query).then(setHits).catch(() => setHits([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  return (
    <div className="search">
      <input
        value={query}
        placeholder="Search titles and specs…"
        onChange={(change) => setQuery(change.target.value)}
      />
      {hits.length > 0 ? (
        <ul className="hits">
          {hits.map((task) => (
            <li key={task.id}>
              <button onClick={() => { onOpen(task.id); setQuery(""); setHits([]); }}>
                <code>{task.id}</code> <span className="dim">{task.status}</span> {task.title}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function shorten(path: string): string {
  /* The last two segments. A board's title bar does not need forty characters of home directory,
   * and the repository name plus its parent is what makes two checkouts distinguishable. */
  const parts = path.split("/").filter(Boolean);
  return parts.slice(-2).join("/");
}
