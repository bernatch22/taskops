import { renderToStaticMarkup } from "react-dom/server";

import {
  cascade,
  gitAvailable,
  noteGitRefusal,
  resetGitAvailability,
  type GitTarget,
} from "../../src/links";
import { DiffPane } from "../../src/components/card/Patch";
import { ReportFrame } from "../../src/components/reports/ReportFrame";
import { whyNoReport } from "../../src/pages/Reports";
import type { Check, Fixture, Harness } from "./section";

/* THE HOSTED WINDOW (ARCHITECTURE.md §16, "The hosted window").
 *
 * A `taskops serve` host used to be the cascade's dead end: /git refused, the
 * pane fell to the forge link, and every diff cost a click out. Now a board
 * with a DECLARED forge answers /git from a read-only mirror on the host, so
 * the same window a phone opens draws the same panes a checkout does — and a
 * board with NO forge still refuses, and the cascade still lands on the forge
 * link or the honest sentence.
 *
 * Nothing here is a new component or a new step: the whole card is that the
 * EXISTING cascade needs no change, because every route it builds is relative
 * to the board's base and every answer is the door's own payload. So what this
 * section pins is exactly that — the three behaviours of one hosted page load,
 * drawn from the fixture's real /git payloads, plus the wording rule: no pane
 * may claim "your clone" on a host that reads a mirror.
 *
 * The harness fires no effects (`react-dom/server`), so as in `git-diff.tsx`
 * the fetch itself is covered on the Python side (`tests/test_topology.py`);
 * here the door's payloads are handed to the pure halves. */

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { REPO } = h;
  const git = fixture.git;
  const target: GitTarget = { kind: "compare", base: "main", head: "tk-a11111" };

  // A section must not inherit the flag another section's refusal flipped.
  resetGitAvailability();

  /* ── a · the diff pane, from a /git answer ──────────────────────────────
   * On the hosted window this answer comes out of the mirror, and the client
   * cannot tell — the payload is the same `GitDiff` a checkout's door sends,
   * which is the whole argument that the cascade needed no change. */
  const patch = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: git.compare, loading: false })} />,
  );
  check("a /git answer draws the patch pane, hosted or not", patch.includes('data-testid="patch"'));
  check("with the door's own diff text in it", patch.includes("diff --git") && patch.includes("@@"));
  check("and no forge fallback beside a patch that arrived", !patch.includes('data-testid="patch-forge"'));

  // The waiting sentence must not claim a clone the hosted reader has none of.
  const waiting = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: null, loading: true })} />,
  );
  check("the loading pane names the host, never the reader's clone", waiting.includes('data-testid="patch-loading"') && !waiting.includes("clone"));

  /* ── b · the report pane, from /git/file bytes ──────────────────────────
   * Same rule: the bytes are the door's `GitFile` payload, mirror or checkout,
   * and the renderer never asks which. */
  const prose = renderToStaticMarkup(<ReportFrame file={git.text_file} title="Field notes" />);
  check("a /git/file answer draws the report pane", prose.includes('data-testid="report-body"'));
  check("with the committed bytes rendered, not the pointer", prose.includes("importer landed"));

  const page = renderToStaticMarkup(<ReportFrame file={git.file} title="Chapter panorama" />);
  check("an html report gets its frame from the same payload", page.includes('data-testid="report-frame"'));

  // And the report page's own "why not", with no bytes: honest about the host.
  const silent = whyNoReport({ file: null, loading: false, refusal: null }, true);
  check("a report the host could not read blames the host, not 'your clone'", !silent.includes("your clone"));

  /* ── c · the forge link survives the refusal ────────────────────────────
   * A hosted board with NO declared forge still refuses /git, in the words
   * `noteGitRefusal` matches — and the cascade's next step is still the forge
   * link, then the sentence. The hosted window ADDS an answer; it removes no
   * fallback. */
  const refused = cascade(REPO, target, { diff: null, loading: false, refusal: git.no_repo });
  check("a /git refusal falls to the forge step", refused.step === "forge");
  check(
    "quoting the door's refusal, not a paraphrase",
    refused.step === "forge" && refused.why === git.no_repo,
  );
  noteGitRefusal(git.no_repo);
  check("and the refusal's words still flip availability for the session", !gitAvailable());

  const drawn = renderToStaticMarkup(<DiffPane step={refused} />);
  check(
    "the forge link is a real anchor on the pane",
    drawn.includes('data-testid="patch-forge-link"') && !drawn.includes('href=""'),
  );

  // Leave the flag as this section found it: later sections start clean too.
  resetGitAvailability();
}
