import { renderToStaticMarkup } from "react-dom/server";

import { Dossier } from "../../src/components/card/Drawer";
import { Monitor } from "../../src/pages/Monitor";
import { Worktrees, rows } from "../../src/pages/Worktrees";
import type {
  BoardPayload,
  CardPayload
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, REPO } = h;

  /* ── The board points at the code — and only when it can ───────────────
   *
   * `BoardPayload.repo` is the whole switch (`links.tsx`). The fixture is a
   * REAL board with no `origin` recorded, so the no-slug case is the payload
   * above, unmodified — the case that must change NOTHING. The with-slug case
   * is built here for the same reason as 2b and 2c: this board cannot produce
   * one, and the copy is the server's own answer with the key set on top.
   *
   * The gitlab pass is not a duplicate. It is the assertion that a non-GitHub
   * host is a VALUE and not a second code path: same components, same props,
   * a different row of `BY_HOST`, and `/-/commit/` instead of `/commit/`.
   * Delete that row and this is the check that goes red. */

  const drawAll = (payload: BoardPayload, dossierCard: CardPayload): string =>
    renderToStaticMarkup(
      <>
        <Monitor board={payload} openCard={() => {}} now={now} />
        <Worktrees
          groups={payload.groups}
          milestones={payload.milestones}
          repo={payload.repo}
        />
        <Dossier
          dossier={dossierCard}
          openId={dossierCard.card.id}
          team={payload.team}
          now={now}
          onClose={() => {}}
          onComment={async () => {}}
          repo={payload.repo}
          /* The Worktree block draws its control only when there is somewhere to
             send the reader (`Sections.tsx::Body`), so the harness has to be
             that somewhere — the same shape App passes. Without it the absence
             of the row would look like the feature working. */
          onOpenTree={() => {}}
        />
      </>,
    );

  const linkable = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  linkable.repo = REPO;
  const onGitlab = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  onGitlab.repo = { host: "gitlab.com", slug: "g/sub/p", url: "https://gitlab.com/g/sub/p" };

  // A commit with counts, on the dossier's commit list AND on its thread — the
  // two places a sha is drawn, and the two `numstat` readers (a typed field and
  // `readNumstat` over an open event body) that must agree.
  const counted = JSON.parse(JSON.stringify(fixture.card)) as CardPayload;
  const sha = counted.commits[0]?.sha ?? "0".repeat(40);
  const numstat = { "src/a.py": [12, 3], "ui/logo.png": null };
  counted.commits[0] = { sha, subject: "a commit with counts", numstat: { "src/a.py": [12, 3], "ui/logo.png": null } };
  counted.history = [
    ...counted.history,
    {
      id: "smoke-commit",
      ts: now - 60,
      actor: "agent:berna/e3",
      kind: "commit",
      scope: "task",
      subject: counted.card.id,
      body: { sha, subject: "a commit with counts", numstat },
    } as unknown as (typeof counted.history)[number],
  ];

  const noSlug = drawAll(fixture.board, counted);
  const slug = drawAll(linkable, counted);
  const gitlab = drawAll(onGitlab, counted);

  // NO SLUG → NO LINKS, and no layout shift. Not "no href" — no ANCHOR: a
  // disabled-looking link is the dead anchor the chapter's rule forbids.
  check("no slug: not one anchor is rendered", !noSlug.includes("<a "));
  check(
    "no slug: no compare offered anywhere",
    !noSlug.includes("chapter-compare") && !noSlug.includes("worktree-compare"),
  );
  // The layout does not depend on the slug either. This used to assert the
  // five-column grid string, which pinned a table that no longer exists; what it
  // was really about survives, so that is what it says now: with no anchor to
  // draw, the index still draws every column that has rows and every row in
  // them. The count is the fixture's own — one column, because nothing on this
  // board is integrated — and it is derived rather than written, so it follows
  // the payload instead of pinning a number.
  check(
    "no slug: the worktrees index is whole anyway",
    (noSlug.match(/data-testid="worktree-column"/g) ?? []).length === 1 &&
      (noSlug.match(/data-testid="worktree-row"/g) ?? []).length ===
        rows(fixture.board.groups).length,
  );

  check("a sha links to the commit page", slug.includes(`https://github.com/owner/repo/commit/${sha}`));
  check("the thread's sha is a link too", slug.includes('data-testid="thread-commit-link"'));
  /* The card modal's Worktree block used to offer a forge compare here, and
     this check asserted its URL shape. It offers the WORKTREE now — the view in
     this dashboard, reading this clone — so the claim worth pinning inverted:
     not "the link is built right" but "there is no such link to build", with or
     without a slug. The card's diff did not go anywhere; it is the Files
     changed section, read from the clone (`OWN_CLONE` in tests/test_ui.py). */
  check(
    "the card sends the reader to its worktree, in this dashboard",
    slug.includes('data-testid="card-open-tree"'),
  );
  check(
    "and offers no forge compare of its own, slug or no slug",
    !slug.includes('data-testid="card-compare"') && !noSlug.includes('data-testid="card-compare"'),
  );
  // …with NO base in the URL: the trunk is not on the board, so the forge's own
  // default branch answers. A `main` appearing here is the UI guessing.
  check(
    "the chapter compares against the trunk, whose name the UI does not know",
    slug.includes('data-testid="chapter-compare"') &&
      /href="https:\/\/github\.com\/owner\/repo\/compare\/ms[^".]*"/.test(slug),
  );
  check("a worktree row compares too", slug.includes('data-testid="worktree-compare"'));
  // …and it is the row button's SIBLING, never its child. That is the invariant
  // the old reserved sixth column existed to buy: an `<a>` inside a `<button>`
  // is invalid HTML and unreachable by keyboard. The column is gone; the rule it
  // was protecting is asserted directly instead.
  check(
    "the compare anchor sits beside the row button, not inside it",
    /data-testid="worktree-row"[\s\S]*?<\/button><a /.test(slug),
  );
  check(
    "every outward anchor is a new tab with rel=noopener",
    (slug.match(/<a /g) ?? []).length === (slug.match(/rel="noopener noreferrer"/g) ?? []).length,
  );
  check("no anchor has an empty href", !slug.includes('href=""'));

  check("the numstat draws +12", slug.includes(">+12<"));
  check("and −3, with a minus sign", slug.includes(">−3<"));
  // The honest half: git prints `-` for a binary and the payload stores null.
  // A "0" here would be the UI claiming a measurement nobody made.
  check("a binary is counted as binary, never as a zero", slug.includes("1 binary"));
  check(
    "both numstat readers agree — the commit list and the thread",
    (slug.match(/data-testid="numstat"/g) ?? []).length >= 2,
  );

  check(
    "a non-github host is a VALUE: /-/commit and /-/compare",
    gitlab.includes(`https://gitlab.com/g/sub/p/-/commit/${sha}`) && gitlab.includes("/-/compare/"),
  );
  check("nothing rendered NaN or an undefined path", !slug.includes("NaN") && !slug.includes("/undefined"));
}
