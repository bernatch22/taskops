/* The left pane, VS Code's Explorer / NERDTree in shape: a small-caps header
 * naming the worktree with its two actions, folders that arrive CLOSED except
 * the chain above every working-set file, those files highlighted, chevrons
 * that turn, indentation guides per level, a badge on a closed folder saying
 * how much of the working set is inside, and the keyboard: ↑/↓ move, → opens
 * a folder or steps into it, ← closes one or climbs to the parent, Enter
 * opens a file.
 *
 * WHAT IS OPEN IS THE PAGE'S STATE, not this component's — a Set of OPEN
 * folders (`pages/Editor.tsx`), seeded with the working set's ancestors and
 * only ever grown by a re-read, so a listing that arrives every second cannot
 * close what the reader opened, and a file that enters the working set opens
 * its chain. It used to be a Set of CLOSED folders here; that memory could
 * not be seeded and had every folder open, which on a 185-file tree is a wall.
 * While a filter is typed every folder is open whatever the set says — a
 * match inside a closed folder would read as "no match".
 *
 * The working set (`tree.ts::working`) is drawn three ways at once, none of
 * them colour alone: the state glyph (M A S U C D), a tinted row, and the
 * count on the folder. A `deleted` file is struck through and opens nothing —
 * there are no bytes to read. Every fold is a real `<button>` with
 * `aria-expanded`, every file a `<button>` with `aria-current` on the open
 * one; the container is a `tree` with a `treeitem` per row. */
import { useEffect, useRef, useState } from "react";

import { TONE_FG } from "../board/CardTile";
import type { FileState } from "../../types";
import { FileGlyph, FolderGlyph } from "./Icon";
import { STATE_GLYPH, visibleRows, working, type TreeNode } from "./tree";

/** The status pair the gutter already wears (`links.tsx`'s rule): added is
 *  `--ok`, changed is `--warn`, an untracked file — added, but to nobody's
 *  index yet — the accent, the branch's committed work the accent too, and
 *  a deletion `--danger`. */
export const STATE_INK: Record<FileState, string> = {
  clean: "var(--text-2)",
  modified: TONE_FG.warn,
  added: TONE_FG.ok,
  staged: TONE_FG.ok,
  untracked: TONE_FG.accent,
  committed: TONE_FG.accent,
  deleted: TONE_FG.danger,
};

const INDENT = 14;

const row: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "5px",
  width: "100%",
  padding: "2px 8px 2px 0",
  borderRadius: "5px",
  fontSize: "12.5px",
  lineHeight: 1.55,
  whiteSpace: "nowrap",
  overflow: "hidden",
};

const glyph: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  width: "11px",
  textAlign: "center",
  flex: "none",
};

const chevron = (open: boolean): React.CSSProperties => ({
  display: "inline-block",
  width: "12px",
  flex: "none",
  textAlign: "center",
  fontSize: "10px",
  color: "var(--text-3)",
  transform: open ? "rotate(90deg)" : "none",
  transition: "transform 120ms ease",
});

const header: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 8px 6px 12px",
  fontSize: "10.5px",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "var(--text-3)",
};

const action: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  padding: "2px 6px",
  borderRadius: "6px",
  fontSize: "12px",
  color: "var(--text-2)",
  textTransform: "none",
  letterSpacing: 0,
};

const badge: React.CSSProperties = {
  marginLeft: "auto",
  marginRight: "2px",
  fontSize: "10px",
  fontWeight: 600,
  minWidth: "16px",
  padding: "0 5px",
  borderRadius: "9px",
  textAlign: "center",
  background: "var(--accent-soft)",
  color: "var(--accent)",
};

/** The guides: one hairline per level, drawn as the row's own left cells so
 *  they line up between rows without a second element per level. */
function Guides({ depth }: { depth: number }): React.JSX.Element {
  return (
    <>
      {Array.from({ length: depth }, (_, i) => (
        <span
          key={i}
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: `${INDENT}px`,
            alignSelf: "stretch",
            flex: "none",
            borderLeft: "1px solid var(--hair-2)",
            marginLeft: i === 0 ? "13px" : 0,
          }}
        />
      ))}
    </>
  );
}

export interface FileTreeProps {
  /** the worktree's name — the header's small caps */
  name: string;
  nodes: readonly TreeNode[];
  /** the OPEN folders, the page's state */
  open: ReadonlySet<string>;
  onToggle: (path: string) => void;
  /** back to the default: the working set open, the rest closed */
  onCollapseAll: () => void;
  /** the quick-open palette */
  onQuickOpen: () => void;
  /** the file open in the active tab, drawn `aria-current` and revealed */
  active: string | null;
  onOpen: (path: string) => void;
  /** a filter is typed: every folder stays open */
  filtering: boolean;
}

export function FileTree(p: FileTreeProps): React.JSX.Element {
  const box = useRef<HTMLDivElement>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const opened = p.filtering ? new Set([...p.open, ...allFolders(p.nodes)]) : p.open;
  const rows = visibleRows(p.nodes, opened);

  // The active file is REVEALED: its row scrolled into view when the tab
  // changes (the page has already opened its chain).
  useEffect(() => {
    box.current?.querySelector<HTMLElement>('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
  }, [p.active]);

  function onKey(e: React.KeyboardEvent<HTMLDivElement>): void {
    const at = Math.max(0, rows.findIndex((r) => r.node.path === (focused ?? p.active)));
    const here = rows[at];
    if (!here) return;
    const go = (i: number): void => {
      const next = rows[Math.min(rows.length - 1, Math.max(0, i))];
      if (next) setFocused(next.node.path);
    };
    switch (e.key) {
      case "ArrowDown":
        go(at + 1);
        break;
      case "ArrowUp":
        go(at - 1);
        break;
      case "ArrowRight":
        if (here.node.kind === "folder") {
          if (opened.has(here.node.path)) go(at + 1);
          else p.onToggle(here.node.path);
        }
        break;
      case "ArrowLeft":
        if (here.node.kind === "folder" && opened.has(here.node.path)) p.onToggle(here.node.path);
        else {
          const parent = here.node.path.slice(0, here.node.path.lastIndexOf("/"));
          const up = rows.findIndex((r) => r.node.path === parent);
          if (up >= 0) go(up);
        }
        break;
      case "Enter":
        if (here.node.kind === "file") {
          if (here.node.file.state !== "deleted") p.onOpen(here.node.path);
        } else p.onToggle(here.node.path);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: "1 1 0px" }}>
      <div style={header} data-testid="editor-tree-header">
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</span>
        <span style={{ flex: "1 1 auto" }} />
        <button type="button" data-testid="editor-quick-open" title="quick open (⌘P / Ctrl+P)" onClick={p.onQuickOpen} style={action}>
          ⌕
        </button>
        <button type="button" data-testid="editor-collapse-all" title="collapse all — the working set stays open" onClick={p.onCollapseAll} style={action}>
          ⊟
        </button>
      </div>
      <div
        ref={box}
        role="tree"
        tabIndex={0}
        data-testid="editor-tree"
        aria-label={`${p.name} files`}
        onKeyDown={onKey}
        onMouseLeave={() => setHovered(null)}
        style={{ minHeight: 0, overflow: "auto", padding: "0 6px 16px 0", outline: "none" }}
      >
        {rows.map(({ node, depth }) => {
          const isFocus = focused === node.path;
          if (node.kind === "folder") {
            const isOpen = opened.has(node.path);
            return (
              <div key={node.path} role="treeitem" aria-expanded={isOpen} aria-level={depth + 1}>
                <button
                  type="button"
                  data-testid="editor-folder"
                  data-path={node.path}
                  data-changed={node.changed}
                  aria-expanded={isOpen}
                  onClick={() => {
                    setFocused(node.path);
                    p.onToggle(node.path);
                  }}
                  onMouseEnter={() => setHovered(node.path)}
                  title={node.changed ? `${node.path} — ${node.changed} in the working set` : node.path}
                  style={{
                    ...row,
                    color: "var(--text-2)",
                    background: isFocus ? "var(--pane-3)" : hovered === node.path ? "var(--hair)" : "transparent",
                  }}
                >
                  <Guides depth={depth} />
                  <span style={chevron(isOpen)}>▸</span>
                  <FolderGlyph open={isOpen} />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{node.name}</span>
                  {/* Something under it moved: a badge with the count while
                      closed (the reader cannot see inside), a dot while open. */}
                  {node.changed > 0 ? (
                    isOpen ? (
                      <span data-testid="editor-folder-changed" aria-label={`${node.changed} changed`} style={{ color: TONE_FG.warn, fontSize: "9px" }}>
                        ●
                      </span>
                    ) : (
                      <span data-testid="editor-folder-badge" aria-label={`${node.changed} changed inside`} style={badge}>
                        {node.changed}
                      </span>
                    )
                  ) : null}
                </button>
              </div>
            );
          }
          const on = node.path === p.active;
          const hot = working(node.file.state);
          const gone = node.file.state === "deleted";
          return (
            <div key={node.path} role="treeitem" aria-level={depth + 1} aria-selected={on}>
              <button
                type="button"
                data-testid="editor-file"
                data-path={node.path}
                data-state={node.file.state}
                data-working={hot ? "true" : undefined}
                aria-current={on ? "true" : undefined}
                aria-disabled={gone || undefined}
                onClick={() => {
                  setFocused(node.path);
                  if (!gone) p.onOpen(node.path);
                }}
                onMouseEnter={() => setHovered(node.path)}
                title={gone ? `${node.path} — deleted on this branch` : node.path}
                style={{
                  ...row,
                  color: on ? "var(--text)" : hot ? STATE_INK[node.file.state] : "var(--text-2)",
                  background: on
                    ? "var(--pane-3)"
                    : isFocus
                      ? "var(--pane-3)"
                      : hot
                        ? "var(--accent-soft)"
                        : hovered === node.path
                          ? "var(--hair)"
                          : "transparent",
                  fontWeight: hot ? 500 : 400,
                  textDecoration: gone ? "line-through" : undefined,
                  opacity: gone ? 0.7 : 1,
                  cursor: gone ? "default" : "pointer",
                }}
              >
                <Guides depth={depth} />
                <span style={{ ...glyph, color: STATE_INK[node.file.state] }} aria-label={node.file.state}>
                  {STATE_GLYPH[node.file.state]}
                </span>
                <FileGlyph path={node.path} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{node.name}</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Every folder path in a tree — what a filter opens. */
export function allFolders(nodes: readonly TreeNode[]): string[] {
  const out: string[] = [];
  const walk = (list: readonly TreeNode[]): void => {
    for (const n of list) {
      if (n.kind === "folder") {
        out.push(n.path);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return out;
}
