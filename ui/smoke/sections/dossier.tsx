import { renderToStaticMarkup } from "react-dom/server";

import { Dossier } from "../../src/components/card/Drawer";
import { Markdown } from "../../src/components/shared/Markdown";
import type {
  CardPayload
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, slice } = h;

  /* ── The dossier — including the criteria v1 never drew ─────────────── */

  const dossier = renderToStaticMarkup(
    <Dossier
      dossier={fixture.card}
      openId={fixture.card.card.id}
      team={fixture.board.team}
      now={now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  for (const text of fixture.expect) {
    check("dossier shows " + JSON.stringify(text), dossier.includes(text));
  }
  check("criteria are on screen", dossier.includes('data-testid="criteria"'));
  check(
    "every criterion is drawn, numbered",
    // Split on the backticks: a criterion is drawn through the ONE renderer now
    // (tk-382948), so a code span reaches the page as `<code>…</code>` and the
    // criterion is no longer one raw substring. Every piece of it is still
    // there, which is the claim — "drawn" was never "drawn as plain text".
    fixture.card.card.criteria.every((text) =>
      text.split("`").every((piece) => piece === "" || dossier.includes(piece)),
    ),
  );
  check("the comment box is the foot", dossier.includes('data-testid="comment-box"'));

  /* …and drawn through the ONE renderer, inline. The check above splits on the
   * backticks, so it passes for a criterion printed raw — mutating this site
   * came back green until this was added. What cannot be green raw: a `<code>`
   * element per code span, one inline render per criterion, and no `<p>` (the
   * block wrapper) anywhere in the section. */
  const crit = slice(dossier, 'data-testid="criteria"', "Commits ·");
  check(
    "a criterion reads its markdown and keeps its number",
    crit !== "" &&
      crit.includes("<code") &&
      crit.includes("npm run typecheck") &&
      !crit.includes("`") &&
      !crit.includes("<p") &&
      (crit.match(/data-testid="markdown-inline"/g) ?? []).length ===
        fixture.card.card.criteria.length,
    crit,
  );

  /* CRITERION 3 of tk-382948: the spec and the thread render EXACTLY as they
   * did. The proof is byte-level and it is the strongest one available here —
   * the dossier must CONTAIN, verbatim, what `<Markdown>` produces for the very
   * same string on its own. Had the inline mode leaked into the default path
   * (or had the spec been switched to it), the substring would not be there. */
  const spec = fixture.card.card.spec;
  check(
    "the spec is still the block renderer's own output, byte for byte",
    spec !== "" && dossier.includes(renderToStaticMarkup(<Markdown text={spec} />)),
  );
  const said = fixture.card.history.find((e) => e.kind === "comment");
  const saidText = typeof said?.body["text"] === "string" ? said.body["text"] : "";
  check(
    "a comment is too — the thread is untouched",
    saidText !== "" && dossier.includes(renderToStaticMarkup(<Markdown text={saidText} />)),
  );
  /* The released note and the reviewer's verdict were the other raw draws in
   * this document. Both are prose and both now read their markdown. */
  /* SCOPED to the section, not to the whole document: `<code>` appears in the
   * criteria too, so the unscoped form of this check passed with the resume note
   * printed raw. */
  const resume = slice(dossier, "Resume note · previous worker", "Worktree");
  check(
    "the previous worker's released note reads its markdown",
    resume.includes("<code") &&
      resume.includes("src/tax.py::half_up") &&
      !resume.includes("`"),
    resume,
  );

  /* The reviewer's verdict is the last raw draw in this document, and no fixture
   * board can reach it: `standing.verdict === "changes"` needs a card that was
   * handed in and bounced, which would move the card this dossier is about out
   * of the group every other assertion here reads. So it is the same exception
   * `2b` documents — the server's own payload, with the ONE key under test set
   * on top of it, in the shape `core/review.py::Standing` sends. */
  const bounced = JSON.parse(JSON.stringify(fixture.card)) as CardPayload;
  bounced.standing = {
    submitted_at: now - 600,
    submitted_by: "agent:berna/w2",
    verdict: "changes",
    note: "the rounding is still `float` in one branch",
    reviewed_by: "dev:berna",
    reviewed_at: now - 60,
  };
  const changes = renderToStaticMarkup(
    <Dossier
      dossier={bounced}
      openId={bounced.card.id}
      team={fixture.board.team}
      now={now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  const verdict = slice(changes, 'data-testid="verdict"', "</div></div>");
  check(
    "the reviewer's words read their markdown too",
    verdict.includes("<code") && verdict.includes("float") && !verdict.includes("`"),
    verdict,
  );
}
