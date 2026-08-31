/* The card's Files-changed pane asks for a range that survives its chapter
 * landing — BOTH ends of it, and pinned where the pane itself chooses it.
 *
 * WHAT WENT WRONG TWICE. First version: base = the chapter's branch, head = the
 * card's branch — and for a landed card both were pruned on the forge before
 * this host became the board's remote, so the compare refused and the pane was
 * empty. Second version made only the HEAD a recorded sha; the base stayed a
 * branch name and the pane stayed empty. Reported live on tk-bffa26 both times.
 *
 * WHY THIS FILE INSISTS ON THE CALL SITE. The previous section pinned the
 * decision as a pure function and said so honestly: `FilesChanged` fetches
 * through a `useEffect`, `react-dom/server` fires none, and a mutation at the
 * dossier's call site was measured to be INVISIBLE here. So the fix that
 * shipped was pinned everywhere except in the one component that was broken.
 * `FilesChanged` now renders the route it asked for as `data-range` on its
 * wrapper, which is a fact about the pane and not a test hook, and every claim
 * below reads it off a rendered `<Body>` — the real component, the real
 * payload. Mutate the call site and this section goes red.
 *
 * The one-commit dossier is the fixture's own card (`tests/test_ui.py`), so the
 * shape asserted is the shape the SERVER sends on `CardPayload.commits`. The
 * multi-commit one is that card with a second commit appended, which is the
 * shape tk-bffa26's live payload has: two bodies, oldest first, both with a
 * `branch` the host no longer carries.
 */
import { renderToStaticMarkup } from "react-dom/server";

import { Body } from "../../src/components/card/Sections";
import { cardRange, gitForge, gitRoute } from "../../src/links";
import type { CardPayload } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

/** The pane's own `data-range`, off a rendered dossier body. */
function asked(dossier: CardPayload, now: number): string {
  const markup = renderToStaticMarkup(<Body dossier={dossier} now={now} repo={null} reader={null} />);
  return /data-range="([^"]*)"/.exec(markup)?.[1] ?? "";
}

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, REPO } = h;
  const one = fixture.card;
  const commits = one.commits;

  check(
    "the dossier payload carries a per-card sha at all",
    commits.length > 0 && typeof commits[0]?.sha === "string",
    JSON.stringify(commits.map((c) => c.sha)),
  );

  /* ── one recorded commit: the commit door, which diffs against parent #1 ── */
  const single: CardPayload = { ...one, commits: [commits[0]!] };
  const first = commits[0]!.sha;
  check(
    "a one-commit card asks the COMMIT door for its own sha",
    asked(single, now) === `git/commit/${encodeURIComponent(first)}`,
    asked(single, now),
  );
  check(
    "and never a branch name on either side",
    !asked(single, now).includes(one.branch) && !asked(single, now).includes("ms/"),
    asked(single, now),
  );

  /* ── several: the whole span, based on the FIRST commit's PARENT ────────── */
  const last = "f".repeat(40);
  const landed: CardPayload = {
    ...one,
    commits: [commits[0]!, { ...commits[0]!, sha: last, subject: "the second half" }],
  };
  const span = asked(landed, now);
  check(
    "a multi-commit card asks compare(<first>^ ... <last>) — the parent, not the first commit",
    span === `git/compare/${encodeURIComponent(`${first}^`)}...${encodeURIComponent(last)}`,
    span,
  );
  check(
    "so the oldest commit's own changes are INSIDE the range, not one off its edge",
    span.includes(encodeURIComponent(`${first}^`)) && !span.includes(`git/compare/${encodeURIComponent(first)}...`),
    span,
  );
  check(
    "and the landed card's pane asks for no branch this host may have pruned",
    !span.includes(one.branch) && !span.includes("ms"),
    span,
  );

  /* ── the fallback, and the forge link beside the pane ───────────────────── */
  check(
    "a commit body with no sha falls to the two branch names",
    JSON.stringify(cardRange([{}], "tk-dfaff7", "ms/x")) ===
      JSON.stringify({ kind: "compare", base: "ms/x", head: "tk-dfaff7" }),
  );
  check(
    "no commit bound at all is no section — the gate the pane always had",
    cardRange([], "tk-dfaff7", "ms/x") === null && cardRange(undefined, "tk-x", "ms/x") === null,
  );
  check(
    "so a dossier with no commits renders no Files-changed pane at all",
    asked({ ...one, commits: [] }, now) === "",
  );
  const forgeOne = gitForge(REPO, cardRange([{ sha: first }], "tk-x", "ms/x")!);
  const forgeMany = gitForge(REPO, cardRange([{ sha: first }, { sha: last }], "tk-x", "ms/x")!);
  check(
    "the forge link beside the pane still points at a real page for one commit",
    forgeOne === `${REPO.url}/commit/${first}`,
    String(forgeOne),
  );
  check(
    "and at the same span for several",
    forgeMany === `${REPO.url}/compare/${first}^...${last}`,
    String(forgeMany),
  );

  /* The route builder is the door's grammar and nothing here re-spells it. */
  check(
    "the pane's data-range IS gitRoute of the target the call site chose",
    asked(single, now) === gitRoute(cardRange(single.commits, single.branch, single.milestone?.branch ?? "")!),
  );
}
