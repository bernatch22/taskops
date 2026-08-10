import { renderToStaticMarkup } from "react-dom/server";

import { ReportFrame, SANDBOX } from "../../src/components/reports/ReportFrame";
import type { Check, Fixture, Harness } from "./section";

/* A REPORT WRITTEN AS PROSE IS RENDERED AS PROSE.
 *
 * Every report that is not a self-contained HTML page used to land in the same
 * `<pre>` as any unknown type, which meant the reports a human actually reads —
 * the `.md` ones — were served as their own SOURCE: `##`, `|`, `*`, unparsed.
 * The door now says `text/markdown` and this file pins what the reader does
 * with it, in the three parts that could each regress on their own.
 *
 * There is no browser here — `react-dom/server` and nothing else, like every
 * section beside it. */

const REPORT = [
  "# Chapter close",
  "",
  "The **five** criteria, and what each one cost:",
  "",
  "| criterion | met |",
  "| --- | --- |",
  "| the door serves a file at a rev | yes |",
  "",
  "- one",
  "- two",
  "",
  "```sh",
  "uv run pytest -q",
  "```",
].join("\n");

/** The same hostile bytes the sandbox section uses, in a MARKDOWN report — the
 *  branch that does not get a frame has to be safe on its own terms. */
const HOSTILE = "# hi\n\n<script>parent.localStorage.getItem('taskops:x')</script>\n";

function drawn(text: string, kind: "text/markdown" | "text/plain"): string {
  return renderToStaticMarkup(
    <ReportFrame
      file={{ path: ".taskops/reports/x.md", rev: "a".repeat(40), content_type: kind, text, truncated: false, cap: 60000 }}
      title="Chapter close"
    />,
  );
}

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  const html = drawn(REPORT, "text/markdown");

  /* ── 1. it is PARSED, not printed ─────────────────────────────────────── */

  check("a markdown report is drawn by the dashboard's own renderer", html.includes('data-testid="report-markdown"'));
  check("and not dumped into the raw text pane", !html.includes('data-testid="report-text"'));
  /* The ASSERTIONS are about the parse, not about the tags the design happens
     to use: a heading is a styled block and not an `<h1>`, and `<strong>`
     carries inline style — pinning either spelling would pin the design. */
  check("a heading loses its hashes and keeps its words", html.includes(">Chapter close<") && !html.includes("# Chapter close"));
  check("emphasis becomes an element, not two asterisks", /<strong[^>]*>five<\/strong>/.test(html) && !html.includes("**five**"));
  check("a table becomes a table", html.includes("<table") && html.includes("<td"));
  check("a list becomes a list", html.includes("<li>"));
  check("a fenced block keeps its code", html.includes("uv run pytest -q"));
  check("and no source marker survives the parse", !html.includes("# Chapter close") && !html.includes("| --- |"));

  /* ── 2. it needs no frame, and gets none ──────────────────────────────── */

  check("prose is not put in an iframe", !html.includes("<iframe"));
  check("so the sandbox attribute has nothing to appear on", !html.includes(SANDBOX));

  /* ── 3. and the boundary is not bent to do it ─────────────────────────── */

  const hostile = drawn(HOSTILE, "text/markdown");
  check(
    "raw HTML in a markdown report is drawn as characters, never as markup",
    !hostile.includes("<script>") && hostile.includes("&lt;script&gt;"),
  );
  check(
    "so the token line reaches the document as text and nothing else",
    hostile.includes("parent.localStorage.getItem") && !hostile.includes("</script>"),
  );

  /* ── and the OTHER branches are untouched ─────────────────────────────── */

  const plain = drawn("just words\n", "text/plain");
  check("an unknown type still degrades to the raw text pane", plain.includes('data-testid="report-text"'));
  check("and is not quietly parsed as markdown instead", !plain.includes('data-testid="report-markdown"'));
}
