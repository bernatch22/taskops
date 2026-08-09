import { renderToStaticMarkup } from "react-dom/server";

import { Monitor } from "../../src/pages/Monitor";
import type {
  BoardPayload,
  Milestone
  
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;

  /* ── SEVERAL chapters open is a list, not an apology (tk-13d115) ─────
   *
   * `_facts.in_scope` returns None for several open chapters — it refuses to
   * guess — and the Chapter pane used to read that refusal as a fault: a
   * paragraph telling the reader to "land or drop the finished ones" and nothing
   * at all about either chapter. Two open chapters is a working board.
   *
   * The payload is the server's own, with the landed chapter re-opened and the
   * focus cleared: exactly the shape a board with two chapters in flight sends,
   * and every field on both chapters is a real one the board wrote. */

  const several = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const second = JSON.parse(
    JSON.stringify(fixture.board_landed.milestone),
  ) as Milestone | null;
  const first = several.milestone;
  check(
    "the two-chapter fixture has two real chapters",
    first !== null && second !== null,
  );
  if (first && second) {
    second.status = "open";
    several.milestone = null; // what the server sends when it cannot focus one
    // The re-opened one FIRST, so the row that expands by default is the chapter
    // that has rules AND criteria — criterion 2 is about the whole body, and a
    // chapter with neither would prove only that the goal is drawn.
    // …and a THIRD that has LANDED, in the same list, because that is exactly
    // how the payload sends it (`_facts.chapters`: open first, landed after).
    // A landed chapter is history and must not be listed as in flight.
    const ghost: Milestone = {
      ...first,
      id: "ms-hasalreadylanded",
      title: "a landed chapter",
      status: "landed",
    };
    several.milestones = [second, first, ghost];
    // One card moved to the second chapter, so the counts have something to
    // disagree about if they are ever invented rather than folded.
    const moved = several.groups.take[0];
    if (moved) moved.milestone = second.id;

    const many = renderToStaticMarkup(
      <Monitor
        board={several}
        openCard={() => {}}
        now={now}
        onFocusChapter={() => {}}
      />,
    );
    check(
      "with two chapters open the pane apologises for nothing",
      !many.includes("Land or drop the finished ones"),
      many,
    );
    check(
      "it lists BOTH chapters as foldable rows",
      many.includes(first.title) &&
        many.includes(second.title) &&
        (many.match(/data-testid="chapter-fold"/g) ?? []).length === 2,
      many,
    );
    // A real button with `aria-expanded`, not an arrow glyph: the first row open,
    // the rest closed.
    check(
      "the first row is expanded and the second is not",
      (many.match(/aria-expanded="true"/g) ?? []).length === 1 &&
        (many.match(/aria-expanded="false"/g) ?? []).length === 1,
      many,
    );
    // Criterion 2: the expanded body is what the single-chapter pane draws —
    // goal, rules, criteria (drawn on no other screen) and the branch footer.
    check(
      "the expanded body is the whole chapter, criteria included",
      many.includes(second.goal) &&
        // …through the SAME `Goal` the focused pane draws (tk-382948): the
        // accordion was the second of the two sites printing it raw, and a fix
        // applied to one of two call sites is the drift this pane already has a
        // post-mortem about.
        many.includes('data-testid="chapter-goal"') &&
        many.includes('data-testid="chapter-rules"') &&
        many.includes('data-testid="chapter-criteria"') &&
        many.includes("Integration branch") &&
        many.includes(second.branch),
      many,
    );
    check(
      "the collapsed one shows its title and NOT its goal",
      // A RENDERED fragment, not the raw string: since the goal became markdown
      // the source text appears nowhere at all, so `!includes(first.goal)` is
      // true even for a pane that draws the whole thing. A heading the renderer
      // emits verbatim is what can still tell the two apart.
      many.includes(first.title) &&
        !many.includes(first.goal) &&
        !many.includes("Dónde está el frente hoy"),
      many,
    );
    check(
      "the chapter that landed is not listed — this pane is what is in flight",
      !many.includes(ghost.title) && !many.includes(ghost.id),
      many,
    );
    // And the common case is untouched: one chapter in focus is the pane that
    // was always there — no rows, no fold arrow, no accordion chrome.
    const focusedOne = renderToStaticMarkup(
      <Monitor
        board={fixture.board}
        openCard={() => {}}
        now={now}
        onFocusChapter={() => {}}
      />,
    );
    check(
      "with a chapter in focus the pane renders as it always did",
      !focusedOne.includes('data-testid="chapter-fold"') &&
        !focusedOne.includes('data-testid="chapter-focus"') &&
        focusedOne.includes("Chapter in focus"),
      focusedOne,
    );
    // The counts are FOLDED from the rows, never invented — and a payload whose
    // rows name no chapter draws no count at all rather than `0 open` on each.
    check(
      "each row says how many open cards it carries",
      (many.match(/data-testid="chapter-open-count"/g) ?? []).length === 2,
      many,
    );
    const blind = JSON.parse(JSON.stringify(several)) as BoardPayload;
    for (const rows of Object.values(blind.groups)) {
      for (const row of rows as { milestone?: string }[]) delete row.milestone;
    }
    const blindMarkup = renderToStaticMarkup(
      <Monitor board={blind} openCard={() => {}} now={now} />,
    );
    check(
      "with no row naming a chapter, no count is drawn rather than a wrong one",
      !blindMarkup.includes('data-testid="chapter-open-count"') &&
        blindMarkup.includes('data-testid="chapter-fold"'),
      blindMarkup,
    );
    // The `focus` action is the header picker's own setter arriving as a prop —
    // no handler fires here, so what is pinned is that the control exists only
    // when there is somewhere for it to go. `App.tsx` passes `setMilestone`.
    const noFocus = renderToStaticMarkup(
      <Monitor board={several} openCard={() => {}} now={now} />,
    );
    check(
      "focus is offered when a setter is passed and not otherwise",
      (many.match(/data-testid="chapter-focus"/g) ?? []).length === 2 &&
        !noFocus.includes('data-testid="chapter-focus"'),
      noFocus,
    );
  }
}
