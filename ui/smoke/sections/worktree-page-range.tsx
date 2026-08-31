/* The WORKTREES PAGE's range — the page Berna actually opens, and the one that
 * kept asking for two branch names while three chapters fixed the drawer.
 *
 * Reported live on 2026-08-31 for tk-bffa26 and tk-dfaff7: the page asked
 * `compare/ms%2F<chapter>...tk-<id>`, and a landed card's two branches were
 * pruned before this host became the board's remote, so the host answered
 * `not_found` and the page drew the refusal over work sitting in the trunk.
 * `WorktreeDiff` now takes its target from `links.tsx::cardRange` — the SAME
 * rule the drawer uses, never a second one — and keeps the branch compare only
 * when nothing is recorded, which is a live tree whose work has not been
 * committed yet and where the branch really is the only handle.
 *
 * Read off the RENDERED PAGE, never from the pure function: the previous
 * chapter's section pinned the decision one layer below the call site, a
 * call-site mutation was measured GREEN, and the page stayed broken in
 * production for hours. Mutate the call site and this section goes red.
 */
import { renderToStaticMarkup } from "react-dom/server";

import { WorktreeDiff } from "../../src/pages/WorktreeDiff";
import type { CardPayload } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

const CHAPTER = "ms/a-chapter";
const ROW = { id: "tk-range", branch: "tk-range", path: ".taskops/trees/tk-range", holder: "" };

/** The page's own `data-range`, off a rendered page. */
function asked(dossier: CardPayload | undefined, now: number): string {
  const markup = renderToStaticMarkup(
    <WorktreeDiff
      row={ROW as never}
      base={CHAPTER}
      repo={null}
      reader={null}
      dossier={dossier}
      now={now}
      onBack={() => {}}
    />,
  );
  return /data-range="([^"]*)"/.exec(markup)?.[1] ?? "";
}

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;
  const card = fixture.card;
  const first = card.commits[0]!.sha;
  const single = asked({ ...card, commits: [card.commits[0]!] }, now);

  check(
    "a one-commit card asks the COMMIT door, not two branches",
    single === `git/commit/${encodeURIComponent(first)}`,
    single,
  );

  const newest = "f".repeat(40);
  const span = asked(
    { ...card, commits: [card.commits[0]!, { ...card.commits[0]!, sha: newest }] },
    now,
  );
  check(
    "a multi-commit card asks the span from the OLDEST commit's PARENT",
    span === `git/compare/${encodeURIComponent(`${first}^`)}...${encodeURIComponent(newest)}`,
    span,
  );
  check("and never a chapter branch on either side", !span.includes("ms%2F"), span);

  const bare = asked({ ...card, commits: [] }, now);
  check(
    "a tree with NOTHING recorded keeps the two branch tips — the only handle it has",
    bare === `git/compare/${encodeURIComponent(CHAPTER)}...tk-range`,
    bare,
  );
}
