/* The fifth view — a chapter's REPORTS, listed and then read full width.
 *
 * The narration a chapter produced is the one artefact a machine cannot
 * regenerate, and until this chapter it died in a chat transcript. It is now a
 * committed file the board holds a POINTER to (`core/reports.py`), which decides
 * the whole shape of this page:
 *
 *   · the LIST costs nothing and is already here. `verbs/pulse.py::run` folds
 *     the `report` events into `board.reports` on every read, scoped to the
 *     chapter in focus, newest first, capped with `reports_total` beside it. So
 *     this page fetches NOTHING to draw its index — there is one owner of "what
 *     the board says right now" (`useBoard.ts`) and this is a slice of its
 *     answer, not a second fetcher with its own clock.
 *   · the CONTENT is not on the board and never will be: `events.jsonl` stores
 *     references and measures, never bytes. It comes from the reader's own clone
 *     through the `/git` file door, per OPEN, exactly as a patch does
 *     (`links.tsx::useGitFile`, `useGitDiff`'s sibling).
 *
 * THE SHAPE IS `Worktrees`'s, on purpose and not by accident: an index whose row
 * opens a full-width surface that REPLACES it — no modal, no drawer, no history
 * entry. That was decided once already, for the diff page, and the reason is the
 * same here and stronger: a report is a document, and a document read through a
 * 900px letterbox is the bug that page exists to remove. The selection lives in
 * `App.tsx` next to the tab for the reason `tree` does — the thing that must
 * clear it is the tab bar.
 *
 * WHAT THIS PAGE DOES NOT OWN: where a report is allowed to run. That is
 * `components/reports/ReportFrame.tsx`, one file, one constant, and this page
 * cannot ask it for anything laxer because there is no argument to pass.
 */
import { ReportFrame } from "../components/reports/ReportFrame";
import { ago, shortActor } from "../format";
import { useGitFile } from "../links";
import type { FiledReport, GitFile } from "../types";

/** What this page needs of a client — structural, like `GitReader`, so the page
 *  is testable with a two-line fake and the harness can pass `null`. */
export interface FileReader {
  git<T>(route: string): Promise<T>;
}

export interface ReportsProps {
  /** `board.reports`, already scoped to the chapter in focus by the server. */
  reports: FiledReport[];
  /** `board.reports_total` — how many there really are behind the cap. */
  total: number;
  /** The chapter in focus, for the subtitle. `null` under "All milestones". */
  chapter: string;
  /** The wire. Optional and nullable: the smoke harness renders with none, and
   *  a page that demanded a client could not be tested headlessly. */
  reader?: FileReader | null;
  /** WHICH report is open, and how to change it — controlled by `App`, like
   *  `Worktrees`'s tree, because the tab bar is what has to clear it. */
  open: string | null;
  onOpen: (id: string | null) => void;
  now: number;
}

const page: React.CSSProperties = {
  height: "100%",
  overflowY: "auto",
  padding: "0 24px 26px",
};

const head: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  gap: "14px",
  padding: "2px 0 16px",
};

const nothing: React.CSSProperties = {
  borderRadius: "16px",
  border: "1px dashed var(--hair)",
  padding: "44px 24px",
  textAlign: "center",
  fontSize: "12.5px",
  color: "var(--text-3)",
  lineHeight: 1.7,
};

const row: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "block",
  width: "100%",
  borderRadius: "13px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  padding: "14px 18px",
};

const meta: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "10px",
  marginTop: "6px",
  fontSize: "11.5px",
  color: "var(--text-3)",
};

const back: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "12.5px",
  color: "var(--accent)",
};

const NOTHING =
  "No report has been filed for this chapter yet. A report is a file committed " +
  "under .taskops/reports/ and registered with one call — filed path=… title=… " +
  "sha=… — and the board keeps the pointer, never the prose.";

const dot = (
  <span aria-hidden="true" style={{ color: "var(--hair)" }}>
    ·
  </span>
);

/** What the reader gets when there are no bytes to draw — the cascade's last
 *  step, said for a report instead of for a patch.
 *
 *  A refusal the door actually sent WINS, verbatim, for the reason `links.tsx`
 *  gives: only the door knows whether its repo is missing that commit
 *  (`git fetch origin …` brings it), whether the host has neither a checkout
 *  nor a mirror to read from, or
 *  whether that path is not a report — and each one is actionable in words this
 *  side could only paraphrase. Pure and exported, so the sentence is pinned
 *  without a fetch (`App.tsx::onTab`'s reasoning). */
export function whyNoReport(
  state: { file: GitFile | null; loading: boolean; refusal: string | null },
  hasReader: boolean,
): string {
  if (state.loading) return "reading it from this host…";
  if (state.refusal) return state.refusal;
  if (!hasReader) return "this window has no door onto a repository, so there are no bytes to read";
  return "this host could not read that report";
}

function Reader({
  report,
  reader,
  onBack,
}: {
  report: FiledReport;
  reader: FileReader | null;
  onBack: () => void;
}): React.JSX.Element {
  const state = useGitFile(reader, { sha: report.sha, path: report.path });
  return (
    <div style={page} data-testid="report-page" data-report={report.id}>
      <div style={head}>
        <button type="button" data-testid="report-back" onClick={onBack} style={back}>
          ← Reports
        </button>
        <span style={{ fontSize: "15px", fontWeight: 450, letterSpacing: "-0.03em" }}>
          {report.title}
        </span>
      </div>
      <div className="mono" data-testid="report-source" style={{ ...meta, marginBottom: "12px" }}>
        <span>{report.path}</span>
        {dot}
        <span>{report.sha.slice(0, 12)}</span>
        {dot}
        <span>{shortActor(report.by)}</span>
      </div>
      {state.file ? (
        <ReportFrame file={state.file} title={report.title} />
      ) : (
        <div style={nothing} data-testid="report-none">
          {whyNoReport(state, Boolean(reader))}
        </div>
      )}
    </div>
  );
}

export function Reports({
  reports,
  total,
  chapter,
  reader = null,
  open,
  onOpen,
  now,
}: ReportsProps): React.JSX.Element {
  /* The early return, `Worktrees`'s rule: a selection whose row is gone — the
   * board moved, or the chapter in focus changed under it — falls through to the
   * index rather than drawing a page about nothing. */
  const selected = open ? (reports.find((r) => r.id === open) ?? null) : null;
  if (selected) {
    return <Reader report={selected} reader={reader} onBack={() => onOpen(null)} />;
  }

  return (
    <div style={page} data-testid="reports">
      <div style={head}>
        <h2 style={{ margin: 0, fontSize: "19px", fontWeight: 500, letterSpacing: "-0.035em" }}>
          Reports
        </h2>
        <span style={{ fontSize: "12.5px", color: "var(--text-3)" }}>
          {chapter ? chapter : "every chapter"}
          {/* The honest total beside the capped list — `done_total`'s idiom.
              Drawn only when the cap actually bit, because "20 of 20" is a fact
              about the cap and not about the board. */}
          {total > reports.length ? ` · ${reports.length} of ${total}` : ""}
        </span>
      </div>

      {reports.length === 0 ? (
        <div style={nothing} data-testid="reports-none">
          {NOTHING}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {reports.map((r) => (
            <button
              key={r.id}
              type="button"
              data-testid="report-row"
              data-report={r.id}
              onClick={() => onOpen(r.id)}
              style={row}
            >
              <span
                style={{
                  display: "block",
                  fontSize: "13.5px",
                  fontWeight: 450,
                  letterSpacing: "-0.02em",
                }}
              >
                {r.title}
              </span>
              <span style={meta}>
                <span className="mono">{r.path}</span>
                {dot}
                <span>{shortActor(r.by)}</span>
                {dot}
                <span>{ago(now - r.ts)} ago</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default Reports;
