/* The sixth view — the EDITOR: a worktree's real files, read live off the
 * disk this window runs on, drawn the way an editor draws them and never
 * writable.
 *
 * WHAT IT ANSWERS. The Worktrees page says which trees exist and what each
 * one's branch adds as a PATCH; the Board says what state every card is in.
 * Neither says what the code LOOKS LIKE right now — the file a worker is in
 * the middle of, the test it just added, the module it half-renamed. This page
 * does: pick a tree (the checkout first, then every directory under
 * `.taskops/trees/`), and the left pane is its files with their git state, the
 * right pane the file you opened, highlighted, its changed lines marked in the
 * gutter against the branch base, re-read within a second of the disk moving.
 *
 * TWO COMPONENTS, on the rule the Drawer and the Actors page follow: `Editor`
 * owns the hooks (`components/editor/useWorktree.ts` — the reads, the stream,
 * the tabs) and `EditorView` draws what it is handed, so the headless harness
 * renders the whole document from the door's own payloads with no effect ever
 * firing (`ui/smoke/sections/editor-page.tsx`).
 *
 * WHICH TREE is App's state, beside `tab` and `tree`, because two other views
 * send the reader here — a worktree row and the card dossier's Worktree block
 * — and a page that owned its own selection could not be told. Unlike the
 * diff page's `tree`, it is NOT cleared by the tab bar: an editor is a place
 * you come back to, and the tree you left it on is the tree you want.
 *
 * THE BASE for the gutter marks is the row's own chapter branch, resolved from
 * the same `rows()` the Worktrees index uses (`WorktreeRow.milestone.branch`)
 * — never the chapter in focus, for the reason that page argues at length. A
 * chapter tree and the checkout pass no base, and the door answers with the
 * trunk it resolves (`gitwork/trees.py::base_ref`) or HEAD; the line above the
 * code SAYS which base was used, off the door's answer, never guessed here.
 *
 * ON THE DEPLOYED INSTANCE there is no checkout and no worktree, and the door
 * says so in one sentence (`http/editor.py::NO_CHECKOUT`). The page quotes it
 * and draws nothing else — not an empty tree, not a spinner. */
import { useState } from "react";

import { ago } from "../format";
import type { EditorProps } from "../components/monitor/panels";
import { CodeView, type DiffState } from "../components/editor/CodeView";
import { FileTree } from "../components/editor/FileTree";
import { IconSprite } from "../components/editor/Icon";
import { Tabs } from "../components/editor/Tabs";
import { languageOf } from "../components/editor/highlight";
import { filtered, folded, lastChange } from "../components/editor/tree";
import {
  useDiff,
  useListing,
  useOpenFiles,
  useTrees,
  type OpenTab,
} from "../components/editor/useWorktree";
import type { WorktreeRow } from "../components/monitor/panels";
import type { EditorTrees, TreeListing } from "../types";

/** The base a tree's marks are read against: the CARD's own chapter branch
 *  when the tree is a card and the board can name its chapter; nothing
 *  otherwise, and then the door decides (HEAD for the checkout, the trunk for a
 *  chapter tree). Pure and exported for the harness. */
export function baseFor(tree: string | null, named: readonly WorktreeRow[]): string {
  if (!tree) return "";
  return named.find((w) => w.id === tree)?.milestone?.branch ?? "";
}

/** How a tree is named in the picker: the card's title beside its id when
 *  the board knows it — and its standing, and who is in it right now — the
 *  branch otherwise. The standing is the Worktrees index's own pill
 *  (`WorktreeRow.status`), so the two screens cannot disagree about a tree. */
export function labelOf(name: string, branch: string, named: readonly WorktreeRow[]): string {
  const card = named.find((w) => w.id === name);
  if (card) {
    const who = card.worker ?? (card.dev ? card.dev.replace(/^dev:/, "") : null);
    return `${name} — ${card.title} · ${card.status}${who ? ` · ${who}` : ""}`;
  }
  return branch && branch !== name ? `${name} — ${branch}` : name;
}

/** The picker's GROUPS, in the order a reader acts: the checkout, the trees
 *  somebody is working in, the ones waiting, the finished ones — merged apart
 *  from not — the chapter trees, and the trees the board cannot name. Pure,
 *  exported: a native `<optgroup>` is the one styling a `<select>` reliably
 *  carries, and grouping by standing is what says "merged" and "working"
 *  without a colour the option could not wear. */
export function groupsOf(
  trees: readonly { name: string; branch: string }[],
  named: readonly WorktreeRow[],
): { title: string; trees: { name: string; branch: string }[] }[] {
  const by = new Map(named.map((w) => [w.id, w]));
  const groups: { title: string; trees: { name: string; branch: string }[] }[] = [
    { title: "the checkout", trees: [] },
    { title: "working", trees: [] },
    { title: "waiting", trees: [] },
    { title: "done, not merged", trees: [] },
    { title: "merged", trees: [] },
    { title: "chapters", trees: [] },
    { title: "not on the board", trees: [] },
  ];
  for (const t of trees) {
    const row = by.get(t.name);
    const at =
      t.name === "main" ? 0
      : t.name.startsWith("_ms-") ? 5
      : !row ? 6
      : row.status === "merged" ? 4
      : row.status === "done, not merged" ? 3
      : row.status.startsWith("in progress") ? 1
      : 2;
    groups[at]!.trees.push(t);
  }
  return groups.filter((g) => g.trees.length > 0);
}

export function Editor({ reader, tree, onTree, named, now }: EditorProps): React.JSX.Element {
  const { trees, refusal, loading } = useTrees(reader);
  // The checkout is first in every listing, so "nothing chosen yet" opens on it.
  const chosen = tree ?? trees?.trees[0]?.name ?? null;
  const listing = useListing(reader, chosen);
  const base = baseFor(chosen, named);
  const files = useOpenFiles(reader, chosen, listing.listing, base);
  const [query, setQuery] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const activeTab = files.tabs.find((t) => t.path === files.active) ?? null;
  const diff = useDiff(reader, chosen, files.active, base, showDiff, activeTab?.file);
  return (
    <EditorView
      trees={trees}
      refusal={refusal ?? listing.refusal}
      loading={loading}
      tree={chosen}
      onTree={onTree}
      named={named}
      listing={listing.listing}
      live={listing.live}
      query={query}
      onQuery={setQuery}
      tabs={files.tabs}
      active={files.active}
      onOpen={files.open}
      onSelect={files.select}
      onClose={files.close}
      diff={{ on: showDiff, ...diff }}
      onToggleDiff={() => setShowDiff((on) => !on)}
      now={now}
    />
  );
}

export interface EditorViewProps {
  trees: EditorTrees | null;
  /** the door's refusal, quoted — the deployed instance's one sentence */
  refusal: string | null;
  loading: boolean;
  tree: string | null;
  onTree: (name: string) => void;
  named: readonly WorktreeRow[];
  listing: TreeListing | null;
  live: boolean;
  query: string;
  onQuery: (q: string) => void;
  tabs: readonly OpenTab[];
  active: string | null;
  onOpen: (path: string) => void;
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
  diff: DiffState;
  onToggleDiff: () => void;
  now: number;
}

/* ── the geometry ──────────────────────────────────────────────────────────── */

/* THE PAGE FILLS THE VIEWPORT BELOW THE CHROME, by construction and not by
 * measurement. A first version measured the shell's top and set
 * `calc(100vh - top)` from an effect — and the effect ran before the shell
 * existed (it mounts only once the trees are read), so the page sat on its
 * 72vh fallback and left the bottom fifth of a 1150px window blank. Now the
 * chain is a flex column with `min-height: 0` at every link: `App` bounds
 * the shell to `100dvh` on this tab, `<main>` is `minHeight: 0`, this page
 * is `height: 100%`, the panel takes `flex: 1 1 0`, and the tree and the
 * code each scroll inside their own box. The page never scrolls. */
const page: React.CSSProperties = {
  height: "100%",
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  padding: "0 24px 0",  // to the bottom EDGE: every pixel the chrome leaves is code
};

const head: React.CSSProperties = {
  flex: "none",
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: "16px",
  flexWrap: "wrap",
  marginBottom: "12px",
};

const shell: React.CSSProperties = {
  flex: "1 1 0px",
  minHeight: 0,
  display: "grid",
  gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)",
  borderRadius: "16px 16px 0 0",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  borderBottom: "none",
  overflow: "hidden",
};

const aside: React.CSSProperties = {
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  borderRight: "1px solid var(--hair)",
  background: "var(--pane-2)",
};

const filter: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  width: "100%",
  padding: "7px 10px",
  fontSize: "12.5px",
  color: "var(--text)",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  borderRadius: "8px",
};

const picker: React.CSSProperties = {
  fontFamily: '"JetBrains Mono", ui-monospace, monospace',
  fontSize: "12px",
  letterSpacing: "-0.02em",
  padding: "6px 30px 6px 12px",
  borderRadius: "10px",
  color: "var(--text)",
  background: "var(--pane-2)",
  border: "1px solid var(--hair-2)",
  boxShadow: "0 1px 2px rgba(0,0,0,0.08)",
  maxWidth: "44em",
  cursor: "pointer",
};

const meta: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: "10px",
  fontSize: "12px",
  color: "var(--text-3)",
};

const note: React.CSSProperties = {
  fontSize: "13px",
  color: "var(--text-3)",
  padding: "40px 24px",
  lineHeight: 1.7,
  maxWidth: "48em",
};

const toggle = (on: boolean): React.CSSProperties => ({
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "11.5px",
  padding: "4px 12px",
  borderRadius: "9px",
  background: on ? "var(--accent-soft)" : "transparent",
  color: on ? "var(--accent)" : "var(--text-3)",
  whiteSpace: "nowrap",
});

const dot = (
  <span aria-hidden="true" style={{ color: "var(--hair-2)" }}>
    ·
  </span>
);

export function EditorView(p: EditorViewProps): React.JSX.Element {
  const files = p.listing?.files ?? [];
  const shown = filtered(files, p.query);
  const nodes = folded(shown);
  const newest = lastChange(files);
  const activeTab = p.tabs.find((t) => t.path === p.active) ?? null;
  const activeEntry = activeTab ? files.find((f) => f.path === activeTab.path) : undefined;
  return (
    <div style={page} data-testid="editor">
      <IconSprite />
      <div style={head}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "14px", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: "19px", fontWeight: 500, letterSpacing: "-0.035em" }}>
            Editor
          </h2>
          {p.trees ? (
            <select
              data-testid="editor-picker"
              aria-label="worktree"
              value={p.tree ?? ""}
              onChange={(e) => p.onTree(e.target.value)}
              style={picker}
            >
              {groupsOf(p.trees.trees, p.named).map((g) => (
                <optgroup key={g.title} label={g.title} data-testid="editor-picker-group">
                  {g.trees.map((t) => (
                    <option key={t.name} value={t.name} data-testid="editor-picker-tree">
                      {labelOf(t.name, t.branch, p.named)}
                    </option>
                  ))}
                </optgroup>
              ))}
              {/* A tree the reader was SENT to that is not on this disk — a
                  merged card whose directory was tidied. A <select> cannot
                  show a value it has no option for, and falling silently onto
                  `main` while the door's refusal is quoted below read as two
                  screens disagreeing (seen live). So the ask is named, and
                  disabled: it is not a choice, it is what was asked. */}
              {p.tree && !p.trees.trees.some((t) => t.name === p.tree) ? (
                <option value={p.tree} disabled data-testid="editor-picker-missing">
                  {p.tree} — no worktree on this disk
                </option>
              ) : null}
            </select>
          ) : null}
        </div>
        {p.listing ? (
          <div style={meta} data-testid="editor-meta">
            <span className="mono" style={{ color: "var(--accent)" }}>
              {p.listing.branch || p.listing.head.slice(0, 12) || "detached"}
            </span>
            {dot}
            <span>
              {p.listing.files.length} file{p.listing.files.length === 1 ? "" : "s"}
              {/* A capped tree SAYS so, with both numbers: the count is a fact
                  about the listing, `total` the fact about the tree. */}
              {p.listing.capped ? (
                <span data-testid="editor-capped-tree" style={{ color: "var(--warn)" }}>
                  {` of ${p.listing.total.toLocaleString()} — capped at ${p.listing.cap.toLocaleString()}`}
                </span>
              ) : null}
            </span>
            {newest ? (
              <>
                {dot}
                <span data-testid="editor-last-change">
                  last change: <span className="mono">{newest.path}</span> · {ago(p.now - newest.mtime)} ago
                </span>
              </>
            ) : null}
            {dot}
            <span data-testid="editor-live" data-live={p.live} style={{ color: p.live ? "var(--ok)" : "var(--text-3)" }}>
              {p.live ? "● live" : "○ reconnecting"}
            </span>
          </div>
        ) : null}
      </div>

      {p.refusal ? (
        <div data-testid="editor-none" style={{ ...note, flex: "none" }}>
          {p.refusal}
        </div>
      ) : !p.trees ? (
        <div data-testid="editor-loading" style={note}>
          {p.loading ? "reading the worktrees on this disk…" : "no worktrees read yet"}
        </div>
      ) : (
        <div style={shell}>
          <aside style={aside}>
            <div style={{ padding: "10px 10px 8px" }}>
              <input
                data-testid="editor-filter"
                type="search"
                placeholder="filter by path"
                value={p.query}
                onChange={(e) => p.onQuery(e.target.value)}
                style={filter}
              />
            </div>
            <div style={{ minHeight: 0, overflow: "auto", padding: "0 6px 16px" }}>
              {p.listing ? (
                shown.length > 0 ? (
                  <FileTree nodes={nodes} active={p.active} onOpen={p.onOpen} filtering={p.query.trim() !== ""} />
                ) : (
                  <div data-testid="editor-tree-none" style={{ ...note, padding: "18px 10px" }}>
                    {files.length === 0 ? "nothing git can name in this tree" : `nothing matches “${p.query}”`}
                  </div>
                )
              ) : (
                <div style={{ ...note, padding: "18px 10px" }}>reading the tree…</div>
              )}
            </div>
          </aside>
          <section style={{ minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column" }}>
            <Tabs
              tabs={p.tabs.map((t) => ({
                path: t.path,
                state: files.find((f) => f.path === t.path)?.state,
                gone: t.gone,
              }))}
              active={p.active}
              onSelect={p.onSelect}
              onClose={p.onClose}
            />
            {activeTab ? (
              <>
                <div style={{ ...meta, flex: "none", padding: "6px 14px", borderBottom: "1px solid var(--hair)" }}>
                  <span className="mono" data-testid="editor-path" style={{ color: "var(--text-2)" }}>
                    {activeTab.path}
                  </span>
                  {activeEntry ? (
                    <>
                      {dot}
                      <span data-testid="editor-state">{activeEntry.state}</span>
                    </>
                  ) : null}
                  {activeTab.file?.base ? (
                    <>
                      {dot}
                      <span data-testid="editor-base">
                        vs <span className="mono">{activeTab.file.base.ref}</span>
                      </span>
                    </>
                  ) : null}
                  <span style={{ flex: "1 1 auto" }} />
                  <button
                    type="button"
                    data-testid="editor-diff-toggle"
                    aria-pressed={p.diff.on}
                    onClick={p.onToggleDiff}
                    style={toggle(p.diff.on)}
                  >
                    {p.diff.on ? "code" : "diff vs base"}
                  </button>
                </div>
                {activeTab.refusal ? (
                  <div data-testid="editor-file-none" style={note}>
                    {activeTab.refusal}
                  </div>
                ) : activeTab.file ? (
                  <CodeView
                    key={activeTab.path}
                    file={activeTab.file}
                    lang={languageOf(activeTab.path)}
                    flash={activeTab.flash}
                    diff={p.diff}
                  />
                ) : (
                  <div data-testid="editor-file-loading" style={note}>
                    reading {activeTab.path}…
                  </div>
                )}
              </>
            ) : (
              <div data-testid="editor-empty" style={note}>
                Open a file from the tree. What you read is this worktree's own disk, re-read
                the moment it changes — and never written from here.
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

export default Editor;
