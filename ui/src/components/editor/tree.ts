/* The Editor's pure rules — no React, no clock, no fetch — so every decision
 * the page makes about a listing can be pinned under `react-dom/server`
 * (`ui/smoke/sections/editor-page.tsx`) without a DOM:
 *
 *   · `folded()`     a flat listing → a tree of folders, folders first
 *   · `filtered()`   the path filter box
 *   · `lastChange()` the newest mtime — "the project is moving" in one line
 *   · `changedSpan()` which lines a re-read moved, for the flash
 *   · `markMap()`    the gutter marks, by line
 *
 * `folded` carries a `changed` count per folder — how many files under it are
 * not clean — because a folded folder must still say something happened
 * inside it; that is the whole reason a reader would open it. */

import type { FileState, LineMark, MarkKind, TreeFile } from "../../types";

export interface FolderNode {
  kind: "folder";
  name: string;
  path: string;
  children: TreeNode[];
  /** files under it, at any depth, whose state is not `clean` */
  changed: number;
}

export interface FileNode {
  kind: "file";
  name: string;
  path: string;
  file: TreeFile;
}

export type TreeNode = FolderNode | FileNode;

/** The glyph a file's state wears in the tree. `clean` wears none: a mark on
 *  every row is no mark at all. */
export const STATE_GLYPH: Record<FileState, string> = {
  clean: "",
  modified: "M",
  added: "A",
  staged: "S",
  untracked: "U",
};

export function folded(files: readonly TreeFile[]): TreeNode[] {
  const root: FolderNode = { kind: "folder", name: "", path: "", children: [], changed: 0 };
  const folders = new Map<string, FolderNode>([["", root]]);

  function folder(path: string): FolderNode {
    const found = folders.get(path);
    if (found) return found;
    const cut = path.lastIndexOf("/");
    const parent = folder(cut < 0 ? "" : path.slice(0, cut));
    const made: FolderNode = {
      kind: "folder",
      name: cut < 0 ? path : path.slice(cut + 1),
      path,
      children: [],
      changed: 0,
    };
    parent.children.push(made);
    folders.set(path, made);
    return made;
  }

  for (const file of files) {
    const cut = file.path.lastIndexOf("/");
    const parent = folder(cut < 0 ? "" : file.path.slice(0, cut));
    parent.children.push({
      kind: "file",
      name: cut < 0 ? file.path : file.path.slice(cut + 1),
      path: file.path,
      file,
    });
    if (file.state !== "clean") {
      // every ancestor, up to and excluding the root
      let up = parent;
      while (up.path !== "") {
        up.changed += 1;
        const at = up.path.lastIndexOf("/");
        up = folder(at < 0 ? "" : up.path.slice(0, at));
      }
    }
  }

  function sort(node: FolderNode): void {
    node.children.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "folder" ? -1 : 1;
      return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
    });
    node.children.forEach((child) => {
      if (child.kind === "folder") sort(child);
    });
  }
  sort(root);
  return root.children;
}

/** Case-insensitive substring over the whole path. Empty is everything. */
export function filtered(files: readonly TreeFile[], query: string): TreeFile[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...files];
  return files.filter((f) => f.path.toLowerCase().includes(needle));
}

/** The file the disk touched most recently, or null for an empty tree. */
export function lastChange(files: readonly TreeFile[]): TreeFile | null {
  let newest: TreeFile | null = null;
  for (const file of files) if (newest === null || file.mtime > newest.mtime) newest = file;
  return newest;
}

/** Which lines of `after` a re-read moved, 1-based inclusive, or null when
 *  nothing did. Common prefix and common suffix, the way an editor lights a
 *  save: an insertion lights the inserted lines and nothing below them, a
 *  deletion lights the seam it closed. */
export function changedSpan(before: readonly string[], after: readonly string[]): [number, number] | null {
  let head = 0;
  while (head < before.length && head < after.length && before[head] === after[head]) head += 1;
  let tail = 0;
  while (
    tail < before.length - head &&
    tail < after.length - head &&
    before[before.length - 1 - tail] === after[after.length - 1 - tail]
  ) {
    tail += 1;
  }
  if (head === before.length && head === after.length) return null;
  const from = head + 1;
  const to = after.length - tail;
  return to >= from ? [from, to] : [Math.max(1, Math.min(from, after.length)), Math.max(1, Math.min(from, after.length))];
}

/** Line → mark, for the gutter. Later marks win on overlap, which cannot
 *  happen with what `gitwork/reading.py` emits and costs nothing to allow. */
export function markMap(marks: readonly LineMark[]): Map<number, MarkKind> {
  const map = new Map<number, MarkKind>();
  for (const [from, to, kind] of marks) for (let n = from; n <= to; n += 1) map.set(n, kind);
  return map;
}

/** The lines of a text, for `changedSpan` and the line count — a file ending
 *  in a newline has no empty last line, exactly as git counts it. */
export function linesOf(text: string): string[] {
  const lines = text.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}
