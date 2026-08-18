import { renderToStaticMarkup } from "react-dom/server";

import { scopeOf } from "../../src/App";
import {
  ALL_CHAPTERS,
  Menu as MilestoneMenu,
  MilestonePicker,
} from "../../src/components/chrome/MilestonePicker";
import type { Check, Fixture, Harness } from "./section";

export async function run(
  fixture: Fixture,
  check: Check,
  _h: Harness,
): Promise<void> {
  /* ── "all chapters" is a scope, and it is asked for by name ─────────
   *
   * The defect (2026-08-18, a board with one open chapter and eight landed
   * ones): the option sent NO `milestone=`, which the server reads as "resolve
   * it yourself" and resolves to the single open chapter. So the page was
   * narrowed to that chapter, the menu drew its ✓ on "all chapters" the whole
   * time, and clicking it changed no argument — a filter with no way out of it
   * except naming every chapter in turn.
   *
   * Both halves, as this harness always pins them: the RULE that decides what
   * the pill is told, and the markup that shows it. */

  const open = fixture.board.milestones.filter((m) => m.status === "open")[0];
  const openId = open?.id ?? "";

  check(
    "nothing picked: the ✓ falls on the chapter the SERVER resolved",
    scopeOf("", openId) === openId,
    scopeOf("", openId),
  );
  check(
    "nothing picked and no chapter resolved: the whole board",
    scopeOf("", undefined) === ALL_CHAPTERS,
  );
  check(
    "and what the reader picked always wins over the resolution",
    scopeOf(ALL_CHAPTERS, openId) === ALL_CHAPTERS &&
      scopeOf(openId, undefined) === openId,
  );

  // The menu, rendered directly — the dropdown is state behind a click and no
  // handler fires here (that is what `Menu` is exported for).
  function menuAt(selected: string): string {
    return renderToStaticMarkup(
      <MilestoneMenu
        milestones={fixture.board.milestones}
        landedTotal={fixture.board.landed_total}
        selected={selected}
        anchor={{ current: null }}
        onClose={() => {}}
        onSelect={() => {}}
      />,
    );
  }
  const focused = menuAt(openId);
  const whole = menuAt(ALL_CHAPTERS);
  check(
    "the all-chapters row sends `*`, never the absence of an argument",
    focused.includes(`data-milestone="${ALL_CHAPTERS}"`),
    focused,
  );
  check(
    "focused on a chapter, all-chapters is NOT the one marked",
    !focused.includes(`aria-selected="true" data-milestone="${ALL_CHAPTERS}"`),
    focused,
  );
  check(
    "and marked exactly when the whole board is what is asked for",
    whole.includes(`aria-selected="true" data-milestone="${ALL_CHAPTERS}"`),
    whole,
  );

  // The pill itself: board-wide over a board with one open chapter used to read
  // "no open milestone", which is the opposite of what the page was showing.
  const pill = renderToStaticMarkup(
    <MilestonePicker
      milestone=""
      milestones={fixture.board.milestones}
      landedTotal={fixture.board.landed_total}
      selected={ALL_CHAPTERS}
      onSelect={() => {}}
    />,
  );
  check(
    "the pill says which scope it is at",
    pill.includes("all chapters"),
    pill,
  );
  check(
    "and never 'no open milestone' over a board showing every chapter",
    !pill.includes("no open milestone"),
    pill,
  );
}
