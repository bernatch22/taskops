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
import { useState } from "react";
import type { Counts } from "../../links";

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

const pane: React.CSSProperties = {
  borderRadius: "11px",
  background: "var(--pane-3)",
  padding: "10px 12px",
  fontSize: "11.5px",
  lineHeight: 1.55,
  maxHeight: "360px",
  overflow: "auto",
  whiteSpace: "pre",
};

const note: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--text-3)",
  padding: "10px 12px",
  lineHeight: 1.55,
};

/** The patch itself. Empty text is its own sentence: git answered, and the
 *  answer was "nothing here" — which is not the same as not having asked. */
export function PatchText({ text }: { text: string }): React.JSX.Element {
  if (!text.trim()) {
    return (
      <div data-testid="patch-empty" style={note}>
        no textual change in this range — a binary, a mode, or a merge that took no side
      </div>
    );
  }
  return (
    <div className="mono" data-testid="patch" style={pane}>
      {text.split("\n").map((line, n) => (
        <div key={n} style={{ color: tone(line) }}>
          {line || " "}
        </div>
      ))}
    </div>
  );
}

/** One step of the cascade, drawn. The only component that knows what a step
 *  LOOKS like, and it renders all four — including the two that are not a
 *  patch, because "no spinner forever, no silent nothing" is a rule about those
 *  two and not about the happy one. */
export function DiffPane({ step }: { step: DiffStep }): React.JSX.Element {
  if (step.step === "loading") {
    return (
      <div data-testid="patch-loading" style={note}>
        reading the diff from this host's clone…
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
      <PatchText text={step.diff.patch} />
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
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  target: GitTarget;
  on: boolean;
  path?: string;
}): React.JSX.Element {
  const state = useGitDiff(reader, target, on, path);
  return <DiffPane step={cascade(repo, target, state)} />;
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

const row: React.CSSProperties = {
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
}: {
  reader: GitReader | null | undefined;
  repo: Repo | null | undefined;
  target: GitTarget;
  path: string;
  counts: Counts;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="changed-file" style={{ minWidth: 0 }}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} style={row}>
        <span
          className="mono"
          style={{ fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          <span style={{ color: "var(--text-3)", marginRight: "8px" }}>{open ? "▾" : "▸"}</span>
          {path}
        </span>
        <Numstat counts={counts} />
      </button>
      {open ? (
        <div style={{ padding: "8px 14px 12px" }}>
          <Asked reader={reader} repo={repo} target={target} on={true} path={path} />
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
}): React.JSX.Element {
  const target: GitTarget = { kind: "compare", base, head };
  const state = useGitDiff(reader, target, true);
  const step = cascade(repo, target, state);

  if (step.step !== "patch") return <DiffPane step={step} />;

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
        />
      ))}
    </div>
  );
}
