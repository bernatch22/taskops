/* The diff on screen: a unified patch, a file list, and the four states of the
 * cascade — drawn, never decided.
 *
 * WHAT THIS FILE DOES NOT OWN. The order of the fallbacks is `links.tsx`
 * (`cascade()`), the wire is `client.ts::git`, the wording of "why not" is
 * `cascade()`'s too. Everything here takes a `DiffStep` and paints it. That
 * split is the chapter's fifth rule made structural: if the fallback order ever
 * has to change, there is exactly one function to open, and no renderer can
 * quietly grow a fifth step of its own.
 *
 * NO DEPENDENCY, DELIBERATELY. A unified diff is lines prefixed `+`, `-`, ` `
 * and `@@`, and that is the whole grammar this needs. Syntax highlighting is a
 * parser per language, a theme per mode and ~200 kB in a bundle that ships React
 * and nothing else — for a pane whose job is "what changed", which the prefix
 * already answers. The design system's restraint wins, and `+`/`−` carry the
 * meaning with the CSS off exactly as `<Numstat>` does.
 *
 * COLOUR. `--ok` and `--danger`, the same status pair `<Numstat>` wears, on the
 * same reasoning (`links.tsx`): added and deleted are a status pair, not two
 * categorical series, and inventing a hue here would be a sixth palette entry.
 * Hunk headers and file headers are `--text-3` — structure, not content.
 *
 * WIDTH. A patch line is arbitrarily long and a drawer is a fixed column, so the
 * pane scrolls on its own X axis (`overflow: auto` over `white-space: pre`) and
 * every grid cell above it is `minmax(0, …)`. Nothing here may widen the drawer:
 * a horizontal scrollbar on the page is the one failure mode this pane has. */
import { Ext, Numstat, cascade, useGitDiff, type DiffStep, type GitReader, type GitTarget, type Repo } from "../../links";
import { Fragment, useState } from "react";
import type { Counts } from "../../links";
import { split, type Hunk, type Side } from "./split";

/* ── HOW BIG, AND IN HOW MANY COLUMNS ─────────────────────────────────────────
 *
 * The same patch is read in two places that are nothing alike: a 900px dossier
 * column, where it is one pane among ten and 360px of it is generous, and a
 * full-width diff PAGE, where those measurements draw a ribbon in the middle of
 * nothing. Both are correct for their surface, so neither may be inherited from
 * context: the choice is a PROP with two named values, defaulted to the one that
 * was already there, so no existing caller moves and no component has to guess
 * which screen it is on.
 *
 * `mode` rides in the same object for the same reason. Unified is what the
 * drawer draws and what every fallback lands on; split is the page's default,
 * because side by side is the reason the page exists. */
export type PatchSize = "drawer" | "page";
export type PatchMode = "unified" | "split";

export interface PatchView {
  size: PatchSize;
  mode: PatchMode;
}

/** The drawer's view, character for character what this file drew before the
 *  page existed. Every prop below defaults to it. */
export const DRAWER_VIEW: PatchView = { size: "drawer", mode: "unified" };

/** A patch line's ink, by its first character — the whole grammar. `+++`/`---`
 *  are file headers and are tested BEFORE `+`/`-`, or every header would read as
 *  a one-line addition. */
export function tone(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) return "var(--text-3)";
  if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("new file") || line.startsWith("deleted file")) {
    return "var(--text-3)";
  }
  if (line.startsWith("+")) return "var(--ok)";
  if (line.startsWith("-")) return "var(--danger)";
  return "var(--text-2)";
}

/** The pane's measurements, by surface.
 *
 *  `drawer` is the original object, untouched — criterion 3 of this card is that
 *  the dossier's pane keeps today's numbers, so they are written here once and
 *  the page's are a SECOND entry rather than an override of the first.
 *
 *  `page` is a page's typography: ~13px mono instead of 11.5, a looser line, and
 *  a cap that is a fraction of the VIEWPORT rather than 360 fixed pixels — a
 *  number chosen for a drawer means "a third of the screen" on a laptop and "a
 *  seventh" on a monitor, and the pane's job on the page is to be the page.
 *  `overflow: auto` and `white-space: pre` are the same on both: a patch line is
 *  arbitrarily long, and this pane scrolling on its own X axis is what keeps the
 *  page from scrolling on its. */
const PANE: Record<PatchSize, React.CSSProperties> = {
  drawer: {
    borderRadius: "11px",
    background: "var(--pane-3)",
    padding: "10px 12px",
    fontSize: "11.5px",
    lineHeight: 1.55,
    maxHeight: "360px",
    overflow: "auto",
    whiteSpace: "pre",
  },
  page: {
    borderRadius: "11px",
    background: "var(--pane-3)",
    padding: "14px 16px",
    fontSize: "13px",
    lineHeight: 1.65,
    maxHeight: "72vh",
    overflow: "auto",
    whiteSpace: "pre",
  },
};

const note: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--text-3)",
  padding: "10px 12px",
  lineHeight: 1.55,
};

/* ── the two columns ──────────────────────────────────────────────────────── */

const num: React.CSSProperties = {
  color: "var(--text-3)",
  textAlign: "right",
  padding: "0 10px 0 0",
  userSelect: "none",
  whiteSpace: "pre",
  verticalAlign: "top",
};

/** One side of a row. `null` is a real cell and not an absent one — it is the
 *  gap opposite a pure addition or deletion, and it must be drawn (tinted, with
 *  no number) or the two columns stop being aligned by construction. */
function Cell({ side, ink }: { side: Side | null; ink: string }): React.JSX.Element {
  return (
    <>
      <td style={num}>{side ? side.n : ""}</td>
      <td
        style={{
          color: side ? ink : "var(--text-3)",
          background: side ? undefined : "var(--pane-2)",
          padding: "0 12px 0 0",
          whiteSpace: "pre",
          verticalAlign: "top",
        }}
      >
        {side ? side.text || " " : " "}
      </td>
    </>
  );
}

/** The patch, side by side.
 *
 *  ONE table, so the two halves cannot scroll apart: both sides live in the same
 *  rows of the same grid, and the single `overflow: auto` above them is one X
 *  axis for both. Two panes side by side would be two scrollbars a reader has to
 *  keep in sync by hand, and a long line on one side would silently offset the
 *  other.
 *
 *  It draws nothing it was not handed: `split()` decides what pairs with what,
 *  and an unparseable patch never reaches here at all — see `PatchText`. */
export function SplitText({ hunks }: { hunks: Hunk[] }): React.JSX.Element {
  return (
    <table
      data-testid="patch-split"
      /* No fixed layout and no per-column width: a patch line is arbitrarily
         long, so the table is allowed to grow past the pane and the pane's own
         `overflow: auto` scrolls BOTH columns together. Capping the columns
         would clip the code instead, which is the failure this pane exists to
         avoid. */
      style={{ borderCollapse: "collapse", minWidth: "100%" }}
    >
      <tbody>
        {hunks.map((hunk, h) => (
          <Fragment key={h}>
            <tr>
              <td colSpan={4} style={{ color: "var(--text-3)", whiteSpace: "pre", padding: "6px 0 2px" }}>
                {hunk.header}
              </td>
            </tr>
            {hunk.rows.map((r, i) => (
              <tr key={i} data-testid="patch-split-row">
                <Cell side={r.left} ink="var(--danger)" />
                <Cell side={r.right} ink="var(--ok)" />
              </tr>
            ))}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}

/** The patch itself. Empty text is its own sentence: git answered, and the
 *  answer was "nothing here" — which is not the same as not having asked.
 *
 *  THE FALLBACK IS HERE, at the one place both views are in scope: split mode is
 *  a REQUEST, not a promise. `split()` returns `[]` for anything it could not
 *  read, and then this draws the unified view it has always drawn — never an
 *  empty two-column table, which reads as "no changes" and means "I did not
 *  understand". */
export function PatchText({
  text,
  view = DRAWER_VIEW,
}: {
  text: string;
  view?: PatchView;
}): React.JSX.Element {
  if (!text.trim()) {
    return (
      <div data-testid="patch-empty" style={note}>
        no textual change in this range — a binary, a mode, or a merge that took no side
      </div>
    );
  }
  const hunks = view.mode === "split" ? split(text) : [];
  return (
    <div className="mono" data-testid="patch" style={PANE[view.size]}>
      {hunks.length > 0 ? (
        <SplitText hunks={hunks} />
      ) : (
        text.split("\n").map((line, n) => (
          <div key={n} style={{ color: tone(line) }}>
            {line || " "}
          </div>
        ))
      )}
    </div>
  );
}

/** One step of the cascade, drawn. The only component that knows what a step
 *  LOOKS like, and it renders all four — including the two that are not a
 *  patch, because "no spinner forever, no silent nothing" is a rule about those
 *  two and not about the happy one. */
export function DiffPane({
  step,
  view = DRAWER_VIEW,
}: {
  step: DiffStep;
  view?: PatchView;
}): React.JSX.Element {
  if (step.step === "loading") {
    return (
      <div data-testid="patch-loading" style={note}>
        reading the diff from this host…
      </div>
    );
  }
  if (step.step === "forge") {
    return (
      <div data-testid="patch-forge" style={note}>
        {step.why} —{" "}
        <Ext href={step.href} style={{ color: "var(--accent)" }}>
          <span data-testid="patch-forge-link">read it on the forge ↗</span>
        </Ext>
      </div>
    );
  }
  if (step.step === "none") {
    return (
      <div data-testid="patch-none" style={note}>
        {step.why}.
      </div>
    );
  }
  return (
    <div>
      {/* A cut patch SAYS it was cut, with the cap in bytes so the number is a
          fact and not an adjective, and with the forge beside it when there is
          one — the place the rest of it actually lives. */}
      {step.diff.truncated ? (
        <div data-testid="patch-truncated" style={{ ...note, color: "var(--warn)" }}>
          truncated at {step.diff.cap.toLocaleString()} bytes — this is the head of the diff, not all of it
          {step.forge ? (
            <>
              {" · "}
              <Ext href={step.forge} style={{ color: "var(--accent)" }}>
                <span data-testid="patch-truncated-link">the whole diff ↗</span>
              </Ext>
            </>
          ) : null}
        </div>
      ) : null}
      <PatchText text={step.diff.patch} view={view} />
    </div>
  );
}

/** The pane a caller gets for one target: ask, then draw whichever step came
 *  back. Two lines, and they are the two that must never be written separately —
 *  a component that fetched without going through `cascade()` would be a second
 *  fallback order by omission. */
function Asked({
  reader,
  repo,
  target,
  on,
  path,
  view = DRAWER_VIEW,
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  target: GitTarget;
  on: boolean;
  path?: string;
  view?: PatchView;
}): React.JSX.Element {
  const state = useGitDiff(reader, target, on, path);
  return <DiffPane step={cascade(repo, target, state)} view={view} />;
}

const toggle: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "11px",
  padding: "2px 8px",
  borderRadius: "8px",
  background: "var(--pane-3)",
  color: "var(--text-3)",
};

/** A commit's patch, folded. Used by the dossier's commit list AND by the
 *  thread, so the two rows that show the same sha expand into the same pane
 *  rather than into two that drifted. */
export function CommitPatch({
  reader,
  repo,
  sha,
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  sha: string;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ minWidth: 0 }}>
      <button
        type="button"
        data-testid="patch-toggle"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={toggle}
      >
        {open ? "hide diff" : "diff"}
      </button>
      {/* Not rendered until it is open: the hook is the fetch, so an unmounted
          pane is an unmade request — laziness by structure, not by a flag. */}
      {open ? (
        <div style={{ marginTop: "8px" }}>
          <Asked reader={reader} repo={repo} target={{ kind: "commit", ref: sha }} on={true} />
        </div>
      ) : null}
    </div>
  );
}

/** A file row, by surface. In the drawer it is a LIST ITEM — nine pixels of
 *  padding, 12px mono, one of many things in a column. On the page it is the
 *  HEADER of the file below it: more room, a heavier line, and a hairline that
 *  reads as a section break rather than as a separator between two entries. */
const ROW: Record<PatchSize, React.CSSProperties> = {
  drawer: {
    all: "unset",
    boxSizing: "border-box",
    cursor: "pointer",
    display: "grid",
    gridTemplateColumns: "minmax(0,1fr) auto",
    gap: "14px",
    alignItems: "center",
    padding: "9px 14px",
    width: "100%",
    borderBottom: "1px solid var(--hair)",
  },
  page: {
    all: "unset",
    boxSizing: "border-box",
    cursor: "pointer",
    display: "grid",
    gridTemplateColumns: "minmax(0,1fr) auto",
    gap: "18px",
    alignItems: "center",
    padding: "14px 20px",
    width: "100%",
    borderBottom: "1px solid var(--hair)",
  },
};

/** One file of the compare: its path, its +/−, and its own patch on demand.
 *
 *  Per FILE and not one big fetch: the range's patch is capped, and the file a
 *  reader actually opened is the one that must arrive whole. `?path=` is the
 *  door's own parameter, so this costs nothing but a query string. */
function FileRow({
  reader,
  repo,
  target,
  path,
  counts,
  view = DRAWER_VIEW,
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  target: GitTarget;
  path: string;
  counts: Counts;
  view?: PatchView;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="changed-file" style={{ minWidth: 0 }}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} style={ROW[view.size]}>
        <span
          className="mono"
          style={{
            fontSize: view.size === "page" ? "13px" : "12px",
            fontWeight: view.size === "page" ? 500 : undefined,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          <span style={{ color: "var(--text-3)", marginRight: "8px" }}>{open ? "▾" : "▸"}</span>
          {path}
        </span>
        <Numstat counts={counts} />
      </button>
      {open ? (
        <div style={{ padding: view.size === "page" ? "10px 20px 18px" : "8px 14px 12px" }}>
          <Asked reader={reader} repo={repo} target={target} on={true} path={path} view={view} />
        </div>
      ) : null}
    </div>
  );
}

/** The optional summary band — the design's `7 files changed   +412 −38`. */
const summaryBar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "14px",
  padding: "11px 14px",
  fontSize: "12.5px",
  color: "var(--text-2)",
  borderBottom: "1px solid var(--hair)",
};

/** Files changed — the card AS A PULL REQUEST.
 *
 *  The target is `<milestone branch>...<card branch>`, both already on the
 *  dossier payload, so nothing is constructed and nothing is guessed — the same
 *  two facts the forge `compare` link is built from, asked of the local clone
 *  instead of of the network.
 *
 *  The list is the FIRST step of the cascade in its own right: `stat` is the
 *  numstat vocabulary, so a reader who never expands a file still gets +/− per
 *  file. Only the expansion is a second request. */
export function FilesChanged({
  reader,
  repo,
  base,
  head,
  summary = false,
  view = DRAWER_VIEW,
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  base: string;
  head: string;
  /** Draw the `N files changed  +a −d` bar above the list.
   *
   *  A PROP here rather than a computation at the call site, because the count
   *  it states is `step.diff.stat` — which only exists once the cascade has
   *  answered, inside this component. A page that wanted the bar for itself
   *  would have to ask the door a second time for the range this one already
   *  holds, and that second fetch is exactly the duplication the chapter's
   *  third rule forbids. Off by default: the drawer's pane never drew one.
   *  `<Numstat>` paints the +/−, so the status pair is not spelled twice. */
  summary?: boolean;
  /** The surface this list is drawn on, and in how many columns. Defaults to
   *  the drawer's, so the dossier pane is byte-for-byte what it was. */
  view?: PatchView;
}): React.JSX.Element {
  const target: GitTarget = { kind: "compare", base, head };
  const state = useGitDiff(reader, target, true);
  return (
    <FileList
      reader={reader}
      repo={repo}
      target={target}
      step={cascade(repo, target, state)}
      summary={summary}
      view={view}
    />
  );
}

/** The list itself, given a step — `DiffPane`'s seam, for the file list.
 *
 *  Split out for exactly the reason `Dossier` is exported beside `Drawer`
 *  (CLAUDE.md): `FilesChanged` asks through `useGitDiff`, an EFFECT, and
 *  `react-dom/server` fires no effects — so under the headless harness that
 *  component can only ever reach the cascade's fallback and the drawn list
 *  would have no test at all. This half is pure: hand it the step `cascade()`
 *  returned from the door's own payload and it draws what a reader sees.
 *  It decides nothing — the fallback order is still `cascade()`'s alone and the
 *  only fetch is still the hook above. */
export function FileList({
  reader,
  repo,
  target,
  step,
  summary = false,
  view = DRAWER_VIEW,
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  target: GitTarget;
  step: DiffStep;
  summary?: boolean;
  view?: PatchView;
}): React.JSX.Element {
  const { base, head } = target.kind === "compare" ? target : { base: "", head: target.ref };
  if (step.step !== "patch") return <DiffPane step={step} view={view} />;

  const stat: Counts = step.diff.stat;
  const paths = Object.keys(stat).sort();
  if (paths.length === 0) {
    return (
      <div data-testid="changed-none" style={note}>
        no files differ between {base} and {head}
      </div>
    );
  }
  return (
    <div data-testid="files-changed" style={{ borderRadius: "13px", background: "var(--pane-2)", overflow: "hidden" }}>
      {summary ? (
        <div data-testid="files-changed-summary" style={summaryBar}>
          <span>
            {paths.length} file{paths.length === 1 ? "" : "s"} changed
          </span>
          <Numstat counts={stat} />
        </div>
      ) : null}
      {paths.map((path) => (
        <FileRow
          key={path}
          reader={reader}
          repo={repo}
          target={target}
          path={path}
          counts={{ [path]: stat[path] ?? null }}
          view={view}
        />
      ))}
    </div>
  );
}
