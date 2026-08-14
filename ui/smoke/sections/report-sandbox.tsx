import { renderToStaticMarkup } from "react-dom/server";

import { onTab } from "../../src/App";
import { TABS } from "../../src/components/chrome/TabNav";
import { FORBIDDEN, ReportFrame, SANDBOX } from "../../src/components/reports/ReportFrame";
import { fileRoute } from "../../src/links";
import { Reports, whyNoReport } from "../../src/pages/Reports";
import type { Check, Fixture, Harness } from "./section";

/* THE SECURITY BOUNDARY OF THE REPORTS VIEW, pinned headlessly.
 *
 * The milestone's fourth acceptance criterion is one sentence — *a report with a
 * `<script>` tag cannot read the dashboard's token* — and this file is what
 * makes it a claim instead of an intention. There is no browser here (no jsdom,
 * no puppeteer, `react-dom/server` and nothing else), so the claim is proved the
 * way a headless harness can prove it, in three parts that together leave no gap
 * a script could fit through:
 *
 *   1. WHAT THE PARENT DOCUMENT CONTAINS. The report's own bytes — the hostile
 *      ones, `parent.localStorage.getItem(...)` and all, committed for real by
 *      `tests/test_ui.py::A_HOSTILE_REPORT` — reach this markup ESCAPED, inside
 *      an attribute. The dashboard's document therefore carries no `<script`
 *      element of the report's at all, which is asserted literally. Nothing was
 *      sanitised and nothing was stripped: React escaped it because it is an
 *      attribute value, and there is no `dangerouslySetInnerHTML` anywhere in
 *      this dashboard for it to have been routed through instead.
 *   2. WHAT THE FRAME IS ALLOWED TO DO. `sandbox="allow-scripts"`, exactly, and
 *      `allow-same-origin` nowhere near it. That pair is not two permissions but
 *      the absence of the sandbox (`ReportFrame.tsx` carries the argument), so
 *      it is asserted twice — on the rendered attribute, and on the exported
 *      constant, which is the only value a caller can ever get.
 *   3. WHERE THE BYTES CAME FROM. The row's `path` + `sha` compose the /git file
 *      route and nothing else; the fixture's report row and the door's own
 *      answer name the same file at the same commit. The door answers
 *      `application/json` whatever the file is, so the origin holding the token
 *      is never asked to serve HTML in the first place.
 *
 * WHAT IS OUT OF REACH HERE, said as plainly as `git-diff.tsx` says it:
 * `useGitFile` fetches inside a `useEffect` and no effect fires under
 * `react-dom/server`, so the READER page can never reach its bytes under this
 * harness — the step it does reach, the honest sentence, is what is asserted on
 * it. The frame itself is reached the way it is designed to be: `ReportFrame`
 * takes the door's answer as a prop, so it is drawn here from the real payload.
 * The gap is the fetch firing, not what it draws.
 */
export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const reports = fixture.board.reports ?? [];
  const first = reports[0];

  /* ── the list rides the board payload ───────────────────────────────────── */

  check("the board payload carries the chapter's reports", reports.length > 0);
  check(
    "and the honest total beside them",
    (fixture.board.reports_total ?? 0) >= reports.length,
    JSON.stringify(fixture.board.reports_total),
  );
  check(
    "newest first, as the fold hands them over",
    reports.every((r, i) => i === 0 || (reports[i - 1]?.ts ?? 0) >= r.ts),
  );
  check(
    "every row is a POINTER — a path under .taskops/reports/ and a sha, never prose",
    reports.every((r) => r.path.startsWith(".taskops/reports/") && r.sha.length > 0),
  );

  if (!first) return; // every claim below is about a report that exists

  const index = renderToStaticMarkup(
    <Reports
      reports={reports}
      total={fixture.board.reports_total ?? 0}
      chapter={fixture.board.milestone?.title ?? ""}
      reader={null}
      open={null}
      onOpen={(id) => h.opened.push(id ?? "")}
      now={h.now}
    />,
  );
  check("the index draws one row per report", index.includes('data-testid="reports"') &&
    (index.match(/data-testid="report-row"/g) ?? []).length === reports.length);
  check("with the title the filer gave it", index.includes(first.title));
  check("and the file it points at", index.includes(first.path));
  check(
    "a chapter with no report says what one IS, not nothing",
    renderToStaticMarkup(
      <Reports
        reports={[]}
        total={0}
        chapter=""
        reader={null}
        open={null}
        onOpen={() => {}}
        now={h.now}
      />,
    ).includes("committed under .taskops/reports/"),
  );

  /* ── 3 · the bytes come through the /git door ───────────────────────────── */

  const door = fixture.git.file;
  check(
    "the row and the door's answer name the same file at the same commit",
    first.path === door.path && first.sha === door.rev,
    `${first.path}@${first.sha} vs ${door.path}@${door.rev}`,
  );
  const route = fileRoute(first.sha, first.path);
  check("the content route is the /git file door", route.startsWith("git/file/"));
  check("carrying the rev and the path, both encoded", route === `git/file/${first.sha}?path=${encodeURIComponent(first.path)}`, route);
  check(
    "the door types the content itself — a FIELD, never this origin's header",
    door.content_type === "text/html" && fixture.git.text_file.content_type === "text/markdown",
  );
  /* The fixture's non-HTML report is a `.md`, and it used to come back
     `text/plain` because the door knew no markdown. It does now, and the claim
     that matters is unchanged and asserted here in the form that carries it:
     the type this origin must never be handed for a report it did not sandbox
     is `text/html`, and prose is not it. */
  check(
    "and prose is emphatically not typed as HTML",
    fixture.git.text_file.content_type !== "text/html",
  );

  /* ── 2 · the sandbox, on the constant and on the attribute ──────────────── */

  check("the sandbox this dashboard gives a report is exactly one token", SANDBOX === "allow-scripts");
  check(
    "and it can never be the pair that defeats it",
    !SANDBOX.includes(FORBIDDEN) && FORBIDDEN === "allow-same-origin",
  );

  const framed = renderToStaticMarkup(<ReportFrame file={door} title={first.title} />);
  /* React 18's server renderer prints `srcDoc` and `referrerPolicy` with their
   * JSX casing rather than the HTML spelling. HTML attribute NAMES are
   * case-insensitive, so what a browser parses is `srcdoc` and
   * `referrerpolicy` — the claims below are about which attributes are on the
   * frame, not about React's casing, so they read a lowercased copy. The
   * sandbox is asserted on `framed` itself: its VALUE is case-sensitive and is
   * the one string that must never change. */
  const attrs = framed.toLowerCase();
  check("an html report is drawn in an iframe", framed.includes('data-testid="report-frame"'));
  check("with sandbox=allow-scripts", framed.includes('sandbox="allow-scripts"'));
  check(
    "and NEVER allow-same-origin — the pair that would reach the parent",
    !framed.includes("allow-same-origin"),
  );
  check("nothing else is handed back either", !framed.includes("allow-forms") &&
    !framed.includes("allow-popups") && !framed.includes("allow-top-navigation") &&
    !framed.includes("allow-downloads") && !framed.includes("allow-modals"));
  check("the bytes travel in srcdoc, not in a src on this origin", attrs.includes("srcdoc="));
  check("and the frame leaks no referrer", attrs.includes('referrerpolicy="no-referrer"'));

  /* ── 1 · the hostile script never becomes markup in THIS document ───────── */

  check(
    "the fixture's report really is hostile — it reaches for the token",
    door.text.includes("<script") && door.text.includes("localStorage"),
  );
  check(
    "yet the dashboard's own document contains no script element of its",
    !framed.includes("<script"),
  );
  check(
    "it is delivered escaped, inside the sandboxed frame's attribute",
    framed.includes("&lt;script&gt;"),
  );
  check(
    "so the token key it hunts for is nowhere executable in this origin",
    !framed.includes("<script") && framed.includes("taskops:"),
  );

  /* ── NOTHING but HTML is framed, and neither branch can execute ──────────
   *
   * This block used to draw the fixture's `.md` and assert one thing: that a
   * non-HTML report lands in the raw text pane. Markdown has a renderer now
   * (`sections/report-markdown.tsx` pins the parse), so the claim is stated in
   * the form that survives it and covers BOTH: whatever is not `text/html`
   * gets no frame, and its markup reaches the document as characters. Two
   * renderers, one boundary — asserted on each. */

  const prose = renderToStaticMarkup(<ReportFrame file={fixture.git.text_file} title="notes" />);
  check("a markdown report is drawn by this dashboard's renderer", prose.includes('data-testid="report-markdown"'));
  const plain = renderToStaticMarkup(
    <ReportFrame file={{ ...fixture.git.text_file, content_type: "text/plain" }} title="notes" />,
  );
  check("an unknown type still lands in the raw text pane", plain.includes('data-testid="report-text"'));
  check("in no iframe at all, either way", !plain.includes("<iframe") && !prose.includes("<iframe"));
  check(
    "its markup drawn as the characters it is, either way",
    plain.includes("&lt;script&gt;") &&
      !plain.includes("<script") &&
      prose.includes("&lt;script&gt;") &&
      !prose.includes("<script"),
  );

  const cut = renderToStaticMarkup(
    <ReportFrame file={{ ...door, truncated: true }} title={first.title} />,
  );
  check("a cut report says it was cut, with the cap in bytes", cut.includes('data-testid="report-truncated"') &&
    cut.includes(door.cap.toLocaleString()));

  /* ── the reader page's honest fallback, and the door's own words ────────── */

  const reading = renderToStaticMarkup(
    <Reports
      reports={reports}
      total={fixture.board.reports_total ?? 0}
      chapter=""
      reader={null}
      open={first.id}
      onOpen={() => {}}
      now={h.now}
    />,
  );
  check("opening a row replaces the index with the report, full width", reading.includes('data-testid="report-page"') &&
    !reading.includes('data-testid="reports"'));
  check("and it names its source: the path, the sha and who filed it", reading.includes('data-testid="report-source"') &&
    reading.includes(first.sha.slice(0, 12)));
  check(
    "with no bytes to draw it says so, and draws no frame",
    reading.includes('data-testid="report-none"') && !reading.includes("<iframe"),
  );
  check(
    "a selection whose row is gone falls back to the index",
    renderToStaticMarkup(
      <Reports reports={reports} total={0} chapter="" reader={null} open="ev-gone" onOpen={() => {}} now={h.now} />,
    ).includes('data-testid="reports"'),
  );
  check(
    "a refusal is quoted in the door's own words, never paraphrased",
    whyNoReport({ file: null, loading: false, refusal: fixture.git.not_a_report }, true) ===
      fixture.git.not_a_report,
  );
  check(
    "and the door said the thing only it can say — this is not a file server",
    fixture.git.not_a_report.includes("not a report") &&
      fixture.git.not_a_report.includes(".taskops/reports/"),
  );

  /* ── the tab bar clears the open report, exactly as it clears a tree ────── */

  check("selecting the tab you are on returns to the report index", onTab("reports").report === null);
  check("and so does leaving for another one", onTab("board").report === null);
  /* The whole list, which `sections/actors.tsx` used to own: Reports is the
   * FIFTH tab and the last one, and `App`'s page map is a `Record<TabId, …>`,
   * so a tab here with no page is a compile error rather than a dead pill. */
  check(
    "Reports is the fifth tab, after Nova's four",
    TABS.map((t) => t.id).join(" ") === "monitor board actors worktrees reports",
  );
}
