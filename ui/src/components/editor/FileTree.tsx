/* The left pane: the worktree's files as a tree of folders, each file wearing
 * its git state, each folder saying whether anything under it moved.
 *
 * DRAWN FROM `tree.ts::folded`, which is where every decision about shape and
 * order lives; this file only paints nodes and remembers which folders the
 * reader closed. That memory is view state — a `Set` of folder paths in a
 * `useState`, forgotten with the page — and it closes rather than opens,
 * because a tree that arrives folded hides the modified file the reader came
 * to see. While a filter is typed every folder is open whatever the memory
 * says: a filter that matched a file inside a closed folder would show
 * nothing, which reads as "no match".
 *
 * Every fold is a real `<button>` with `aria-expanded`; every file is a
 * `<button>` with `aria-current` on the one that is open. The state glyph is
 * text (`M`, `A`, `S`, `U`) beside the name and not colour alone — a tree read
 * with the CSS off still says which files changed. */
import { useState } from "react";

import { TONE_FG } from "../board/CardTile";
import type { FileState } from "../../types";
import { STATE_GLYPH, type FolderNode, type TreeNode } from "./tree";

/** The status pair the gutter already wears (`links.tsx`'s rule): added is
 *  `--ok`, changed is `--warn`, and an untracked file — added, but to nobody's
 *  index yet — is the accent, so it reads as new without claiming git knows. */
export const STATE_INK: Record<FileState, string> = {
  clean: "var(--text-2)",
  modified: TONE_FG.warn,
  added: TONE_FG.ok,
  staged: TONE_FG.ok,
  untracked: TONE_FG.accent,
};

const row: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "6px",
  width: "100%",
  padding: "3px 8px",
  borderRadius: "6px",
  fontSize: "12.5px",
  lineHeight: 1.5,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const glyph: React.CSSProperties = {
  fontSize: "10.5px",
  fontWeight: 600,
  width: "12px",
  textAlign: "center",
  flex: "none",
};

export interface FileTreeProps {
  nodes: readonly TreeNode[];
  /** the file open in the active tab, drawn `aria-current` */
  active: string | null;
  onOpen: (path: string) => void;
  /** a filter is typed: every folder stays open */
  filtering: boolean;
}

export function FileTree({ nodes, active, onOpen, filtering }: FileTreeProps): React.JSX.Element {
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());

  function toggle(path: string): void {
    setClosed((was) => {
      const next = new Set(was);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function draw(node: TreeNode, depth: number): React.JSX.Element {
    const indent = { paddingLeft: `${8 + depth * 14}px` };
    if (node.kind === "file") {
      const on = node.path === active;
      return (
        <button
          key={node.path}
          type="button"
          data-testid="editor-file"
          data-path={node.path}
          data-state={node.file.state}
          aria-current={on ? "true" : undefined}
          onClick={() => onOpen(node.path)}
          title={node.path}
          style={{
            ...row,
            ...indent,
            color: on ? "var(--text)" : STATE_INK[node.file.state],
            background: on ? "var(--pane-3)" : "transparent",
          }}
        >
          <span style={{ ...glyph, color: STATE_INK[node.file.state] }} aria-label={node.file.state}>
            {STATE_GLYPH[node.file.state]}
          </span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{node.name}</span>
        </button>
      );
    }
    return <Folder key={node.path} node={node} depth={depth} open={filtering || !closed.has(node.path)} onToggle={toggle} draw={draw} />;
  }

  return (
    <div data-testid="editor-tree" style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
      {nodes.map((node) => draw(node, 0))}
    </div>
  );
}

function Folder({
  node,
  depth,
  open,
  onToggle,
  draw,
}: {
  node: FolderNode;
  depth: number;
  open: boolean;
  onToggle: (path: string) => void;
  draw: (node: TreeNode, depth: number) => React.JSX.Element;
}): React.JSX.Element {
  return (
    <div>
      <button
        type="button"
        data-testid="editor-folder"
        data-path={node.path}
        data-changed={node.changed}
        aria-expanded={open}
        onClick={() => onToggle(node.path)}
        title={node.changed ? `${node.path} — ${node.changed} changed` : node.path}
        style={{ ...row, paddingLeft: `${8 + depth * 14}px`, color: "var(--text-2)" }}
      >
        <span style={{ ...glyph, color: "var(--text-3)" }}>{open ? "▾" : "▸"}</span>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{node.name}</span>
        {/* Something under it moved: a dot in the warn ink, and the count in
            the title. A closed folder with nothing to say draws nothing. */}
        {node.changed > 0 ? (
          <span
            data-testid="editor-folder-changed"
            aria-label={`${node.changed} changed`}
            style={{ color: TONE_FG.warn, fontSize: "9px", marginLeft: "2px" }}
          >
            ●
          </span>
        ) : null}
      </button>
      {open ? node.children.map((child) => draw(child, depth + 1)) : null}
    </div>
  );
}
