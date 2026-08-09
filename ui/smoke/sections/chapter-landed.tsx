import { renderToStaticMarkup } from "react-dom/server";

import { Monitor } from "../../src/pages/Monitor";
import { Menu as MilestoneMenu } from "../../src/components/chrome/MilestonePicker";
import { PANES, type Check, type Fixture, type Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;

  /* ── A chapter that has LANDED is still a readable chapter ──────────
   *
   * The regression this section exists for: `landed` became a real milestone
   * status and the board payload still filtered `milestones` to `open`, so two
   * finished chapters — 36 cards, their goals, rules and threads — were in the
   * log and on no screen. The payload is the server's own answer to `board
   * milestone=<the landed one>`, which is the read that could not be reached.
   *
   * Three claims, and they are three because they fail separately: the chapter
   * is READABLE (goal, rules, criteria), it is OFFERED by the picker, and it is
   * not drawn as a live board that happens to be quiet. */

  const landedBoard = fixture.board_landed;
  const landedMonitor = renderToStaticMarkup(
    <Monitor board={landedBoard} openCard={() => {}} now={now} />,
  );
  check(
    "a landed chapter still resolves server-side",
    landedBoard.milestone !== null && landedBoard.milestone.status === "landed",
    JSON.stringify(landedBoard.milestone),
  );
  for (const text of fixture.expect_landed) {
    check("the landed chapter shows " + JSON.stringify(text), landedMonitor.includes(text));
  }
  check(
    "every pane still draws over it",
    PANES.every((pane) => landedMonitor.includes(`data-testid="${pane}"`)),
  );
  // The empty state names the state instead of implying a live board that
  // stopped: "0 ready to pick up" is true of a landed chapter and reads as work
  // somebody abandoned.
  check(
    "Live leases says the chapter landed",
    landedMonitor.includes("This chapter has landed"),
  );
  check(
    "and does not offer work to pick up",
    !landedMonitor.includes("ready to pick up") && !landedMonitor.includes("NaN"),
  );

  // The picker's open menu. Rendered directly because the dropdown is state
  // behind a click and no handler fires here — that is what `Menu` is exported
  // for (MilestonePicker.tsx).
  const menu = renderToStaticMarkup(
    <MilestoneMenu
      milestones={[...fixture.board.milestones, ...landedBoard.milestones]}
      landedTotal={landedBoard.landed_total}
      selected=""
      anchor={{ current: null }}
      onClose={() => {}}
      onSelect={() => {}}
    />,
  );
  const landedId = landedBoard.milestone?.id ?? "";
  check("the menu offers the landed chapter at all", menu.includes(landedId));
  check(
    "and offers it as history, told apart from what is in flight",
    menu.includes('data-testid="milestone-landed"') &&
      new RegExp(`data-milestone="${landedId}" data-landed="1"`).test(menu),
    menu,
  );
}
