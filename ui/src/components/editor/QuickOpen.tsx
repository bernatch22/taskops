/* Quick open — ⌘P / Ctrl+P, VS Code's palette: one input, the fuzzy matches
 * under it (`fuzzy.ts::search`, the tree's own rule), ↑/↓ to move, Enter to
 * open the file in a tab, Esc to close, a click likewise. The matched
 * characters are lit inside each result so the reader sees WHY it matched.
 *
 * Floating over the editor and owned by the page (`open`, `query`, `index`
 * are `pages/Editor.tsx`'s state), so it renders headlessly from props and
 * the harness can pin the list and the lit characters. No fetch: the listing
 * is already in memory, and `search` caps the results at fifty. */
import { useEffect, useRef } from "react";

import { FileGlyph } from "./Icon";
import type { Match } from "./fuzzy";

export interface QuickOpenProps {
  query: string;
  onQuery: (q: string) => void;
  results: readonly Match[];
  index: number;
  onIndex: (i: number) => void;
  onPick: (path: string) => void;
  onClose: () => void;
}

const scrim: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  zIndex: 5,
  display: "flex",
  justifyContent: "center",
  alignItems: "flex-start",
  padding: "48px 0 0",
  background: "transparent",
};

const box: React.CSSProperties = {
  width: "min(640px, 90%)",
  borderRadius: "12px",
  background: "var(--pane)",
  border: "1px solid var(--hair-2)",
  boxShadow: "0 18px 50px rgba(0,0,0,0.35)",
  overflow: "hidden",
  animation: "tk-lift 140ms ease",
};

const input: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  width: "100%",
  padding: "11px 14px",
  fontSize: "13.5px",
  color: "var(--text)",
  borderBottom: "1px solid var(--hair)",
};

const line = (on: boolean): React.CSSProperties => ({
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "8px",
  width: "100%",
  padding: "6px 14px",
  fontSize: "12.5px",
  background: on ? "var(--accent-soft)" : "transparent",
  color: on ? "var(--text)" : "var(--text-2)",
});

/** The path with its matched characters lit. */
export function Lit({ path, positions }: { path: string; positions: readonly number[] }): React.JSX.Element {
  const hot = new Set(positions);
  const cut = path.lastIndexOf("/") + 1;
  return (
    <span className="mono" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
      {[...path].map((ch, i) =>
        hot.has(i) ? (
          <span key={i} data-testid="editor-quick-hit" style={{ color: "var(--accent-hi)", fontWeight: 700 }}>
            {ch}
          </span>
        ) : (
          <span key={i} style={{ color: i >= cut ? "inherit" : "var(--text-3)" }}>
            {ch}
          </span>
        ),
      )}
    </span>
  );
}

export function QuickOpen(p: QuickOpenProps): React.JSX.Element {
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => {
    field.current?.focus();
  }, []);
  useEffect(() => {
    document.querySelector<HTMLElement>('[data-testid="editor-quick-result"][aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [p.index]);

  function onKey(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "ArrowDown") p.onIndex(Math.min(p.results.length - 1, p.index + 1));
    else if (e.key === "ArrowUp") p.onIndex(Math.max(0, p.index - 1));
    else if (e.key === "Enter") {
      const hit = p.results[p.index];
      if (hit) p.onPick(hit.path);
    } else if (e.key === "Escape") p.onClose();
    else return;
    e.preventDefault();
  }

  return (
    <div data-testid="editor-quick" style={scrim} onMouseDown={(e) => e.target === e.currentTarget && p.onClose()}>
      <div style={box} role="dialog" aria-label="quick open">
        <input
          ref={field}
          data-testid="editor-quick-input"
          value={p.query}
          placeholder="type a file name — ↑↓ move · Enter opens · Esc closes"
          onChange={(e) => p.onQuery(e.target.value)}
          onKeyDown={onKey}
          style={input}
        />
        <div role="listbox" style={{ maxHeight: "50vh", overflow: "auto", padding: "4px 0" }}>
          {p.results.length === 0 ? (
            <div data-testid="editor-quick-none" style={{ padding: "12px 14px", fontSize: "12.5px", color: "var(--text-3)" }}>
              nothing matches “{p.query}”
            </div>
          ) : (
            p.results.map((m, i) => (
              <button
                key={m.path}
                type="button"
                role="option"
                data-testid="editor-quick-result"
                data-path={m.path}
                aria-selected={i === p.index}
                onMouseEnter={() => p.onIndex(i)}
                onClick={() => p.onPick(m.path)}
                style={line(i === p.index)}
              >
                <FileGlyph path={m.path} />
                <Lit path={m.path} positions={m.positions} />
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
