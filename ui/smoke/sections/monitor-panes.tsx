import { renderToStaticMarkup } from "react-dom/server";

import { Monitor } from "../../src/pages/Monitor";
import { PANES, type Check, type Fixture, type Harness } from "./section";



export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, opened, slice } = h;

  /* ── Monitor draws its eight panes ─────────────────────────────────── */

  const monitor = renderToStaticMarkup(
    <Monitor board={fixture.board} openCard={(id) => opened.push(id)} now={now} />,
  );
  check("monitor renders", monitor.includes('data-testid="monitor"'));
  for (const pane of PANES) {
    check("pane " + pane, monitor.includes(`data-testid="${pane}"`));
  }

  /* ── Prose is rendered as prose (tk-382948) ────────────────────────
   *
   * The bug, on the freshly migrated axion board: a chapter goal of 4.252
   * characters of real markdown printed as one raw paragraph with the asterisks
   * and the backticks visible. Three claims, and they fail separately:
   *
   *   · the GOAL renders as elements — bold, heading, code, list — and none of
   *     the source markers survives as a character;
   *   · nothing is CUT. A tall goal gets its own scroll, so the last sentence of
   *     the fixture goal must be in the markup;
   *   · a RULE keeps its numbering. This is the one that needed a new mode:
   *     block-rendered, the fixture's second rule (`1. …`) becomes an `<ol>`
   *     inside a tile that already numbers itself.
   *
   * All three read the SAME `monitor` markup rendered above, from the server's
   * own payload — the goal, the rules and the criteria on it are what
   * `tests/test_ui.py::a_board` put on a real board. */

  const goal = slice(monitor, 'data-testid="chapter-goal"', 'data-testid="chapter-rules"');
  check("the chapter goal has its own box", goal !== "");
  check(
    "the goal renders as markdown, not as characters",
    goal.includes("<strong") &&
      goal.includes("<code") &&
      goal.includes("<ul") &&
      goal.includes("Dónde está el frente hoy"),
    goal,
  );
  check(
    "no source marker survives as text",
    !goal.includes("**") && !goal.includes("###") && !goal.includes("`"),
    goal,
  );
  check(
    "a long goal scrolls and is never cut",
    goal.includes("max-height") &&
      goal.includes("overflow-y:auto") &&
      // The last words of the fixture goal. A clamp or an ellipsis loses them.
      goal.includes("la restricción que ata es el"),
    goal,
  );

  /* The mentions pane draws a COMMENT — the same string the thread draws — and
   * it was the third screen printing prose raw. Inline, because the row is one
   * line between an author and a card line. */
  const mention = slice(monitor, 'data-testid="pane-mentions"', 'data-testid="pane-events"');
  check(
    "the mention row reads the comment's markdown",
    mention.includes("<code") && mention.includes("round()") && !mention.includes("`"),
    mention,
  );

  const rules = slice(monitor, 'data-testid="chapter-rules"', 'data-testid="chapter-criteria"');
  check(
    "a rule reads its inline markdown",
    rules.includes("<code") && rules.includes("node build.mjs"),
    rules,
  );
  check(
    "…and keeps the tile's numbering: no second list, no block wrapper",
    !rules.includes("<ol") && !rules.includes("<p") && rules.includes("1. The feed socket"),
    rules,
  );
  check(
    "the chapter's criteria go through the same one renderer",
    slice(monitor, 'data-testid="chapter-criteria"', "Integration branch").includes("<code"),
  );
}
