/* THE TREE AS A PULL REQUEST — the second surface of the Worktrees view.
 *
 * One worktree, full width: the branch it carries, who is in it, where it is on
 * disk, and the whole compare range `<milestone branch>...tk-<id>` as a file
 * list with each file's patch on expand.
 *
 * WHY A PAGE AND NOT THE DRAWER. That was the bug this chapter exists for:
 * clicking a tree opened the CARD dossier, a 900px drawer, with Files changed
 * crammed into a pane inside it. A patch line is arbitrarily long — a fixed
 * column cannot hold one, so the pane scrolled on its own X axis and the reader
 * read a pull request through a letterbox. The engine was right and the screen
 * was wrong. So this is a page: the Worktrees view early-returns it INSTEAD of
 * its table, there is no modal, no overlay and no history entry, and `onBack`
 * clears the one `useState` that selected the row. The card Dossier keeps its
 * own Files changed pane, untouched; this is a second surface, not a
 * replacement.
 *
 * WHAT THIS FILE OWNS: the chrome above the file list — the back link, the
 * branch line, the identity line, and the summary bar's placement.
 *
 * WHAT IT DOES NOT OWN, and may not grow: the cascade (numstat → patch → forge
 * → one sentence) is `links.tsx::cascade`, the wire is `client.ts::git`, the
 * wording of why-not is the cascade's, and the file list with its per-file
 * patches is `components/card/Patch.tsx::FilesChanged` — REUSED, not copied.
 * Nothing here fetches. A host that mounts no /git door (`taskops serve` sits
 * in a directory of boards) is not an error state: the cascade already returns
 * its `forge` or `none` step and `FilesChanged` draws the honest sentence, so
 * there is no spinner, no error box and no retry in this file.
 */
import { useState } from "react";

import { FilesChanged, type PatchMode, type PatchView } from "../components/card/Patch";
import { CommentBox } from "../components/card/CommentBox";
import { Thread } from "../components/card/Thread";
/* THE CARD'S OWN THREAD. `ThreadProps` is declared in the SEAM
 * (`components/monitor/panels.ts`) beside `WorktreeDiffProps`, and re-exported
 * here because this is the module that renders it. It spent one wave declared
 * in this file — panels.ts was held by another card and a concept two workers
 * touch in one file is the conflict `docs/fan-out.md` is about — and came back
 * at the chapter close, exactly as this comment promised it would. The seam
 * never changed. */
import {
  TREE_DIR,
  type ThreadProps,
  type WorktreeDiffProps,
} from "../components/monitor/panels";
import { Ext, compareUrl } from "../links";

export type { ThreadProps };

const page: React.CSSProperties = {
  height: "100%",
  overflowY: "auto",
  padding: "0 24px 26px",
};

const back: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "12.5px",
  color: "var(--accent)",
};

const mono: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--text-2)",
  marginTop: "10px",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const identity: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  marginTop: "6px",
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "10px",
};

const dot = (
  <span aria-hidden="true" style={{ color: "var(--hair)" }}>
    ·
  </span>
);

/** WHO is in the tree, in the table's own words. `dev` alone when the actor is
 *  a dev already (there is no process to name), and the table's own sentence
 *  when the row has neither a holder nor an assignee — an ownership line that
 *  renders blank reads as a payload that failed, not as "free". */
function carrier(row: WorktreeDiffProps["row"]): string {
  if (!row.dev) return "nobody — free to take";
  return row.worker ? `${row.dev} · ${row.worker}` : row.dev;
}

/* The two ways to read a patch, as a control. It remembers NOTHING — no
 * localStorage, no key on the board — because a stored preference is a write
 * whose only job is to contradict the default, and the default is the reason
 * this page exists. Split leads. */
const MODES: readonly { id: PatchMode; name: string }[] = [
  { id: "split", name: "split" },
  { id: "unified", name: "unified" },
];

/** What this page asks `FilesChanged` for. A function, exported, because it is
 *  the one place the PAGE's measurements are chosen — and no handler fires under
 *  `react-dom/server`, so left inline it would be a decision with no test
 *  (`ui/smoke/sections/diff-page.tsx`, and `submit()`'s reasoning in CLAUDE.md). `size` is
 *  fixed: this surface is the page, always. Only the mode is the reader's. */
export function pageView(mode: PatchMode): PatchView {
  return { size: "page", mode };
}

const modeButton = (on: boolean): React.CSSProperties => ({
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "11.5px",
  padding: "4px 12px",
  borderRadius: "9px",
  background: on ? "var(--accent-soft)" : "transparent",
  color: on ? "var(--accent)" : "var(--text-3)",
});

const sectionLabel: React.CSSProperties = {
  fontSize: "11px",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--text-3)",
  marginBottom: "10px",
};

export function WorktreeDiff({
  row,
  base,
  repo,
  reader,
  onBack,
  dossier,
  team = [],
  now = Date.now() / 1000,
  onComment,
  readOnly,
}: WorktreeDiffProps & ThreadProps): React.JSX.Element {
  /* The one piece of state this page owns. `split` by default — side by side is
   * the reason the page is not the drawer's pane. It is passed DOWN into
   * `FilesChanged`, never read from context, and a patch `split()` cannot parse
   * falls back to unified per file (`components/card/split.ts`). */
  const [mode, setMode] = useState<PatchMode>("split");
  const view = pageView(mode);
  // The head is the row's id — a branch name IS the card id, no slug
  // (ARCHITECTURE.md §11), which is why there is nothing to construct here.
  const head = row.id;
  // Step three of the cascade as a page-level anchor. `null` when the board
  // carries no slug, and then no anchor is drawn at all — no disabled link, no
  // `href=""` (`links.tsx`, the chapter's "NO SLUG → NO LINKS" rule).
  const forge = compareUrl(repo, head, base);
  return (
    <div style={page} data-testid="worktree-diff" data-branch={head}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "16px",
          padding: "2px 0 14px",
        }}
      >
        <button type="button" data-testid="worktree-diff-back" onClick={onBack} style={back}>
          ← Worktrees
        </button>
        <span className="mono" style={{ fontSize: "12px", color: "var(--accent)" }}>
          {head}
        </span>
        <span
          style={{
            fontSize: "14px",
            fontWeight: 450,
            letterSpacing: "-0.025em",
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {row.title}
        </span>
      </div>

      <div
        style={{
          borderRadius: "16px",
          background: "var(--pane)",
          border: "1px solid var(--hair)",
          padding: "16px 20px 18px",
        }}
      >
        {/* The range, in the direction the diff reads: base ← head. With no
            chapter in focus there is no base to print, and the UI may not guess
            one — `gitwork/trees.py::base_ref` resolves the trunk from the repo
            and no verb sends it (`links.tsx`, "the trunk the UI does not
            know"). So the line SAYS that instead of showing an empty base. */}
        <div className="mono" data-testid="worktree-diff-range" style={mono}>
          {base ? (
            <>
              {base} <span style={{ color: "var(--text-3)" }}>←</span> {head}
            </>
          ) : (
            <>
              <span style={{ color: "var(--text-3)" }}>
                the trunk this board does not name
              </span>{" "}
              <span style={{ color: "var(--text-3)" }}>←</span> {head}
            </>
          )}
        </div>
        <div style={identity}>
          <span className="mono" data-testid="worktree-diff-owner">
            {carrier(row)}
          </span>
          {dot}
          {/* Construction, not a fetch: `.taskops/trees/<id>`, pinned for life
              by `gitwork/trees.py`. The row already carries it; TREE_DIR is
              imported so the constant has one home even here. */}
          <span className="mono" data-testid="worktree-diff-dir">
            {row.dir || TREE_DIR + head}
          </span>
          {forge ? (
            <>
              {dot}
              <Ext
                href={forge}
                title={`${base || "the trunk"}...${head}`}
                style={{ color: "var(--accent)" }}
              >
                <span data-testid="worktree-diff-forge">
                  open on {repo?.host ?? "the forge"} ↗
                </span>
              </Ext>
            </>
          ) : null}
        </div>
      </div>

      {/* The file list, the +/− per file, the summary bar and all four steps of
          the cascade — one component, already written, asked for this range.
          `summary` and `view` are the only things this page adds to it. */}
      <div style={{ marginTop: "18px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "12px",
            marginBottom: "10px",
          }}
        >
          <span style={sectionLabel}>Files changed</span>
          <span data-testid="worktree-diff-mode" style={{ display: "flex", gap: "2px" }}>
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                data-mode={m.id}
                aria-pressed={mode === m.id}
                onClick={() => setMode(m.id)}
                style={modeButton(mode === m.id)}
              >
                {m.name}
              </button>
            ))}
          </span>
        </div>
        <FilesChanged
          reader={reader}
          repo={repo}
          base={base}
          head={head}
          summary={true}
          view={view}
        />
      </div>

      {/* THE CARD'S OWN THREAD — the same component, the same box, the same
          write. See the note at the top of this file for why there is no
          worktree comment and never will be. */}
      <div style={{ marginTop: "26px" }} data-testid="worktree-diff-thread">
        <div style={sectionLabel}>
          {dossier ? `Thread · ${dossier.history.length}` : "Thread"}
        </div>
        <div
          style={{
            borderRadius: "16px",
            background: "var(--pane)",
            border: "1px solid var(--hair)",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "18px 20px" }}>
            {dossier ? (
              <Thread history={dossier.history} now={now} repo={repo} reader={reader} />
            ) : (
              <div style={{ fontSize: "12.5px", color: "var(--text-3)" }}>
                reading {head}&apos;s card…
              </div>
            )}
          </div>
          {/* No box without a door to send through: the write is `App`'s
              `comment`, and a caller that did not hand one over gets the thread
              read-only rather than a button that fails. */}
          {onComment ? <CommentBox team={team} onSend={onComment} readOnly={readOnly} /> : null}
        </div>
      </div>
    </div>
  );
}

export default WorktreeDiff;
