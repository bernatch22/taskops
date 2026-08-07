/* Edit surface — Taskops Nova.dc.html lines 321-337.
 *
 * A warning, never a lock: that is the subtitle, and it is also the whole
 * semantics. Each open card DECLARES its `files`; when two declarations meet on
 * one path the row tints and the pill says how many hold it. Nothing here
 * refuses anything — the worktrees already make it impossible for two workers
 * to overwrite each other, so the only thing a lock would add is a false sense
 * that the board knows more than it does.
 *
 * The rows are `<div>`s, not buttons, exactly as the design draws them, and
 * `EditSurfaceProps` therefore carries no `onOpen`. This pane states a fact; it
 * does not navigate. Adding a click would be inventing an interaction Nova does
 * not have.
 *
 * ── WHAT THIS PANE CANNOT SEE (criterion 4) ───────────────────────────────
 *
 * It is the client-side twin of `src/taskops/verbs/_context.py::collisions`,
 * and it inherits that function's blindness, deliberately. Four things it does
 * not know, and will not pretend to:
 *
 *  1. **Only what a card DECLARED.** `files` is typed into `taskops_plan` by a
 *     human. A worker that edits a file nobody listed is invisible here — the
 *     board never reads a diff and taskops never parses source
 *     (`docs/fan-out.md` §10 declines to widen this on purpose).
 *  2. **Exact path equality only.** `ui/src/format.ts` and `src/format.ts` are
 *     two different rows. So are the same file spelled relative and absolute.
 *  3. **The same CONCEPT in different files is not a collision at all.** This
 *     is the defect `docs/fan-out.md` is the post-mortem of: four workers wrote
 *     four `ago()`/`initials()` in four different paths, and this warning was
 *     CORRECTLY silent for every one of them. Zero collisions reported, and the
 *     merged tree was still wrong. A pane that implied it would have caught
 *     that would be worse than one that says it cannot.
 *  4. **Unowned cards are counted here, unlike on the server.** `collisions()`
 *     skips a card with no holder and no assignee — inside a `take` that would
 *     be noise, because you cannot collide with a plan. This is a PANORAMA, not
 *     a take: a path two planned cards both name is exactly the thing a human
 *     wants to see before dispatching them in parallel. The detail line says
 *     which of the two it is, per card, so the difference is on screen and not
 *     hidden in a filter.
 */
import { Pane, PaneEmpty, PaneTile } from "./Pane";
import { TONE_BG, TONE_FG } from "../board/CardTile";
import { shortActor } from "../../format";
import type { BoardRow } from "../../types";
import type { EditSurfaceProps, FileClaim } from "./panels";

/** Who a row counts as, in words. `holder` is the LIVE lease; `assignee` is who
 *  it was handed to and has not started; neither means it is unowned. */
function who(row: BoardRow): string {
  if (row.holder) return shortActor(row.holder);
  if (row.assignee) return `${shortActor(row.assignee)}, not started`;
  return "unclaimed";
}

/** One row per declared path, contended first, then alphabetical — the order a
 *  warning wants: the thing to look at is at the top. */
export function claims(rows: readonly BoardRow[]): FileClaim[] {
  const byPath = new Map<string, BoardRow[]>();
  for (const row of rows) {
    for (const path of row.files) {
      const holders = byPath.get(path) ?? [];
      holders.push(row);
      byPath.set(path, holders);
    }
  }
  const out: FileClaim[] = [];
  for (const [path, holders] of byPath) {
    out.push({
      path,
      detail: holders.map((row) => `${row.id} · ${who(row)}`).join("   ·   "),
      claims: holders.length,
      contended: holders.length > 1,
    });
  }
  out.sort((a, b) => b.claims - a.claims || a.path.localeCompare(b.path));
  return out;
}

const row: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  gap: "12px",
  alignItems: "center",
};

const ellipsis: React.CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const pathStyle: React.CSSProperties = { ...ellipsis, fontSize: "12px", color: "var(--text)" };

const detailStyle: React.CSSProperties = {
  ...ellipsis,
  fontSize: "11px",
  color: "var(--text-3)",
  marginTop: "3px",
};

const pill: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "3px 10px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
};

export function EditSurface({ rows }: EditSurfaceProps): React.JSX.Element {
  const files = claims(rows);
  return (
    <Pane
      testId="pane-files"
      title="Edit surface"
      subtitle="A warning, never a lock."
      headPad="18px 20px 10px"
    >
      {files.length === 0 ? (
        <PaneEmpty>
          No open card declares a file. This pane only ever sees what a card
          declared — never what a worker actually edited.
        </PaneEmpty>
      ) : (
        <div style={{ padding: "4px 10px 12px" }}>
          {files.map((file) => (
            <PaneTile
              key={file.path}
              pad="11px 10px"
              style={{
                ...row,
                ...(file.contended ? { background: TONE_BG.warn } : {}),
              }}
            >
              <div style={{ minWidth: 0 }} data-testid="file-claim" data-path={file.path}>
                <div className="mono" style={pathStyle}>
                  {file.path}
                </div>
                <div style={detailStyle}>{file.detail}</div>
              </div>
              <span
                style={{
                  ...pill,
                  // On a contended row the pill sits ON the warn tint, so it
                  // takes the pane's own ground back rather than a second wash
                  // of the same colour, which would erase its edge.
                  background: file.contended ? "var(--pane)" : TONE_BG.neutral,
                  color: file.contended ? TONE_FG.warn : TONE_FG.neutral,
                }}
              >
                {file.claims === 1 ? "1 claim" : `${file.claims} claims`}
              </span>
            </PaneTile>
          ))}
        </div>
      )}
    </Pane>
  );
}
