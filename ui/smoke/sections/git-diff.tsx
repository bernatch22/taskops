import { renderToStaticMarkup } from "react-dom/server";

import {
  cascade,
  gitAvailable,
  noteGitRefusal,
  resetGitAvailability,
  type GitTarget
} from "../../src/links";
import { CommitPatch, DiffPane, FileList, FilesChanged  } from "../../src/components/card/Patch";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { REPO } = h;

  const sha = fixture.card.commits[0]?.sha ?? "0".repeat(40);

  /* ── The diff comes from the viewer's own clone ───────────────────────
   *
   * `fixture.git` is the /git DOOR'S OWN answer over a real two-branch repo,
   * and `fixture.git.no_repo` its own refusal on a host that has none
   * (`tests/test_ui.py::a_diff`). Both had to come from the server for the same
   * reason the board payload does — and the refusal doubly so: `noteGitRefusal`
   * matches on the WORDS of `gitdoor.py::NO_REPO`, so a message written by hand
   * here would pass while the real cascade never flipped.
   *
   * WHAT THIS CANNOT REACH, said as plainly as tk-e586f5 said it: `useGitDiff`
   * fetches inside a `useEffect`, and `react-dom/server` fires no effects. So
   * `FilesChanged` and `CommitPatch` can never reach their PATCH step under this
   * harness, and the step they do reach — the honest fallback — is what is
   * asserted on them. The patch renderer itself is reached the way it is
   * designed to be: `cascade()` is pure and `DiffPane` takes a step, so every
   * one of the four is drawn here from a real payload. The gap is the fetch
   * firing, not what it draws. It is covered end to end on the Python side
   * (`tests/test_topology.py`), never in a browser.
   */

  const git = fixture.git;
  const target: GitTarget = { kind: "compare", base: "main", head: "tk-a11111" };

  check("the door answered with a real range", git.compare.head.length === 40);
  check(
    "and with the numstat vocabulary, per file",
    Object.keys(git.compare.stat).sort().join(",") === "pdf.py,tax.py",
    JSON.stringify(git.compare.stat),
  );

  // Step 2 — the patch, drawn from the door's own text.
  const patch = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: git.compare, loading: false })} />,
  );
  check("the patch pane draws the diff", patch.includes('data-testid="patch"'));
  check("a hunk header is drawn as a header", patch.includes("@@"));
  check("an added line keeps its +", patch.includes("+REDUCED = 0.10"));
  check("the file's own header is in the text", patch.includes("diff --git"));
  check("an untruncated patch says nothing about truncation", !patch.includes("patch-truncated"));

  // A CUT patch: the server's own payload with the one key a big range sets.
  const cut = renderToStaticMarkup(
    <DiffPane
      step={cascade(REPO, target, {
        diff: { ...git.compare, truncated: true },
        loading: false,
      })}
    />,
  );
  check("a cut patch says it was cut, with the cap in bytes", cut.includes('data-testid="patch-truncated"'));
  check("and offers the whole of it on the forge", cut.includes('data-testid="patch-truncated-link"'));
  check("the cap is a figure, not an adjective", cut.includes(git.compare.cap.toLocaleString()));

  /* THE FILE LIST the diff PAGE hands its whole range to — drawn from the same
   * door payload, through `FileList`, the pure half of `FilesChanged` (the
   * asking half is a `useEffect` and no effect fires here). The page adds
   * exactly one thing to it, `summary`, so that is what is asserted beside the
   * rows: `N files changed` plus the range's own +/−. */
  const listed = renderToStaticMarkup(
    <FileList
      reader={null}
      repo={REPO}
      target={target}
      step={cascade(REPO, target, { diff: git.compare, loading: false })}
      summary={true}
    />,
  );
  check(
    "the range is a file list, one row per file the door named",
    listed.includes('data-testid="files-changed"') &&
      (listed.match(/data-testid="changed-file"/g) ?? []).length ===
        Object.keys(git.compare.stat).length,
  );
  check(
    "every path the door named is on it",
    Object.keys(git.compare.stat).every((p) => listed.includes(p)),
  );
  check(
    "and the page's own addition, the summary bar, counts those same files",
    listed.includes('data-testid="files-changed-summary"') &&
      listed.includes(`${Object.keys(git.compare.stat).length} files changed`),
  );
  // The drawer's pane never drew a bar, and still must not: `summary` is a prop,
  // not a thing the component decided for itself.
  check(
    "without the prop there is no bar",
    !renderToStaticMarkup(
      <FileList
        reader={null}
        repo={REPO}
        target={target}
        step={cascade(REPO, target, { diff: git.compare, loading: false })}
      />,
    ).includes('data-testid="files-changed-summary"'),
  );

  // Step 1 — loading. Not a spinner forever: it says what it is waiting on.
  const waiting = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: null, loading: true })} />,
  );
  check("waiting draws the loading step", waiting.includes('data-testid="patch-loading"'));

  /* Steps 3 and 4 — the no-repo host, discovered from the door's own words.
   * `noteGitRefusal` is the only way the flag moves, and `why()` changes with
   * it: before the refusal the sentence is "could not read that diff"; after it,
   * "neither a checkout nor a mirror". Asserting BOTH is what would fail if
   * the flag stopped mattering. */
  const beforeRefusal = cascade(null, target, { diff: null, loading: false });
  check(
    "before any refusal the sentence is about this read, not about the host",
    beforeRefusal.step === "none" && beforeRefusal.why.includes("could not read that diff"),
  );
  /* The STALE CLONE — the everyday case once the board is shared. The card is
   * closed and its branch is on origin; this clone has simply never fetched it.
   * That is not an error and must not read as one, and only the door knows
   * WHICH ref was missing, so the cascade quotes it rather than composing a
   * sentence of its own. Asserted before the no-repo flag is flipped, because
   * afterwards every pane would say the host has no clone. */
  const stale = cascade(null, target, {
    diff: null,
    loading: false,
    refusal: git.stale,
  });
  check(
    "a ref this clone lacks is quoted in the door's own words",
    stale.step === "none" && stale.why.includes("not in your clone yet"),
  );
  check(
    "and it names the git fetch that brings it",
    stale.step === "none" && stale.why.includes("git fetch origin tk-b22222"),
  );
  const staleForge = cascade(REPO, target, { diff: null, loading: false, refusal: git.stale });
  check(
    "the same words ride the forge step, which is still offered",
    staleForge.step === "forge" && staleForge.why.includes("git fetch origin"),
  );
  check(
    "a stale ref does NOT flip availability — ask again for the next one",
    (noteGitRefusal(git.stale), gitAvailable()),
  );

  noteGitRefusal(git.no_repo);
  check("the door's own words flip availability", !gitAvailable());
  check(
    "an unknown ref would NOT have flipped it",
    (resetGitAvailability(), noteGitRefusal(git.stale), gitAvailable()),
  );
  noteGitRefusal(git.no_repo);

  const withSlug = renderToStaticMarkup(
    <DiffPane step={cascade(REPO, target, { diff: null, loading: false })} />,
  );
  check("no clone, but a slug: the forge step", withSlug.includes('data-testid="patch-forge"'));
  check("with a real anchor on it", withSlug.includes('data-testid="patch-forge-link"') && !withSlug.includes('href=""'));
  check(
    "and it reads as this host being what it is, not as an error",
    /* The exact sentence moved with the hosted window (§16): the flag's
       learned state now means "neither a checkout nor a mirror", never "this
       host can never read git". The CONTRACT this line pins is unchanged —
       an honest, non-error sentence about what the host is. */
    withSlug.includes("neither a checkout nor a mirror"),
  );

  const bare = renderToStaticMarkup(
    <DiffPane step={cascade(null, target, { diff: null, loading: false })} />,
  );
  check("no clone and no slug: one honest sentence", bare.includes('data-testid="patch-none"'));
  check("with no anchor at all", !bare.includes("<a "));
  check("that says both halves", bare.includes("no remote to link out to"));

  /* The two containers, under the harness's real limitation: no effect fires,
   * so both sit at the cascade's fallback — and that is a REAL state (a phone
   * on a `taskops serve` host), which must still be a readable pane and never a
   * dead anchor. */
  const filesChanged = renderToStaticMarkup(
    <FilesChanged reader={undefined} repo={REPO} base="ms/x" head="tk-a11111" />,
  );
  check(
    "Files changed with no reader falls to the forge, not to nothing",
    filesChanged.includes('data-testid="patch-forge"') && !filesChanged.includes('href=""'),
  );
  const fold = renderToStaticMarkup(
    <CommitPatch reader={undefined} repo={REPO} sha={sha} />,
  );
  check("a commit row offers its fold", fold.includes('data-testid="patch-toggle"'));
  check("and fetches nothing until it is opened", !fold.includes('data-testid="patch-loading"'));
}
