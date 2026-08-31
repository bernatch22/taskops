/* The card's diff asks for something that survives its chapter landing.
 *
 * `links.tsx::cardHead` is the whole decision: the newest RECORDED sha when the
 * card has one, the branch when it does not. It is pinned here because both of
 * its answers are real states of a live board — a card with commits, and one
 * closed with `no_code=true` that has none — and because the state it exists
 * for is neither: a card worked BEFORE the host became the board's remote,
 * whose `tk-*` branch was pruned on the forge when its chapter landed and never
 * reached this host. Its commits are in the trunk that was pushed, so the sha
 * resolves and the branch is a 404 forever — no later push grows it back.
 *
 * WHAT THIS CANNOT REACH, in `git-diff.tsx`'s own words: the dossier's
 * `FilesChanged` asks through a `useEffect` and `react-dom/server` fires no
 * effects, so REPLACING `cardHead(...)` with `dossier.branch` at that call site
 * is invisible here — mutation-checked and confirmed invisible, not assumed.
 * What is pinned is the decision itself, pure, plus the fact that the payload
 * carries a sha to decide with; the call site is one expression with no second
 * candidate, and the end-to-end proof that a sha resolves where a pruned branch
 * does not is on the Python side (`tests/test_topology.py`).
 *
 * The fixture's card is the source of the sha (`tests/test_ui.py`), so what is
 * asserted is the shape the SERVER actually sends on `CardPayload.commits`, not
 * a shape written by hand here: no event was added for this card, and if the
 * dossier ever stopped carrying commit bodies this section is what says so.
 */
import { renderToStaticMarkup } from "react-dom/server";

import { cardHead } from "../../src/links";
import { FileList } from "../../src/components/card/Patch";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { REPO } = h;
  const commits = fixture.card.commits;

  check(
    "the dossier payload carries a per-card sha at all",
    commits.length > 0 && typeof commits[commits.length - 1]?.sha === "string",
    JSON.stringify(commits.map((one) => one.sha)),
  );

  const newest = commits[commits.length - 1]?.sha ?? "";
  check(
    "the head is the recorded sha, never the branch, when the card has one",
    cardHead(commits, "tk-dfaff7") === newest && newest !== "",
    `${cardHead(commits, "tk-dfaff7")} vs ${newest}`,
  );
  /* WHICH sha, pinned on its own: the fixture card may carry exactly one
   * commit, and then "the newest" and "the first" are the same string — a
   * claim the fixture cannot fail. The board writes them oldest-first
   * (`verbs/_context.py::dossier` folds the event stream in order), so the
   * ORDER is pinned against a list that has two. */
  const ordered = [...commits, { sha: "f".repeat(40), subject: "the latest work" }];
  check(
    "with several commits it is the NEWEST — the last the board wrote, not the first",
    cardHead(ordered, "tk-dfaff7") === "f".repeat(40),
    cardHead(ordered, "tk-dfaff7"),
  );
  check(
    "a card with no commits recorded falls back to its branch",
    cardHead([], "tk-dfaff7") === "tk-dfaff7",
  );
  check(
    "so does a payload with no commits key at all",
    cardHead(undefined, "tk-dfaff7") === "tk-dfaff7",
  );
  check(
    "and a commit body missing its sha is not a handle",
    cardHead([{}], "tk-dfaff7") === "tk-dfaff7",
  );

  /* Downstream nothing branches on the shape of the handle: the target is the
   * cascade's vocabulary, so the same list is drawn whichever one it got. */
  const markup = renderToStaticMarkup(
    <FileList
      reader={null}
      repo={REPO}
      target={{ kind: "compare", base: "ms/x", head: newest }}
      step={{ step: "patch", diff: fixture.git.compare, forge: null }}
    />,
  );
  check("the file list draws the range asked for by sha", markup.includes('data-testid="changed-file"'));
  check("and says nothing about a branch it was not given", !markup.includes("tk-dfaff7"));
}
