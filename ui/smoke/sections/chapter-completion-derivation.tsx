/* Pins `completed.ts::chapterComplete` — the client-side derivation the whole
 * story view stands on. No markup here: the function is PURE, so the section is
 * five payloads and five verdicts. The payloads are built by hand ON PURPOSE —
 * the fixture's boards are live chapters, and this section needs the exact
 * boundary cases (landed, all-done, one card in take, no focus, version drift)
 * under its own control. */
import { chapterComplete } from "../../src/completed";
import type { BoardGroups, BoardPayload, BoardRow, Milestone, Pulse } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

const NOW = 1_755_000_000;

function stone(status: string): Milestone {
  return {
    id: "ms-story",
    title: "A finished chapter",
    goal: "reads as a story",
    rules: [],
    branch: "ms/story",
    status,
    created: NOW,
  };
}

function row(id: string): BoardRow {
  return {
    id,
    title: id,
    priority: 1,
    assignee: "",
    holder: null,
    since: NOW,
    quiet_for: null,
    files: [],
    labels: [],
  };
}

const EMPTY_GROUPS: BoardGroups = {
  merge: [],
  mentions: [],
  review: [],
  changes: [],
  stalled: [],
  take: [],
  doing: [],
  reviewing: [],
  blocked: [],
  done: [],
};

const PULSE: Pulse = {
  milestone: "A finished chapter",
  goal: "reads as a story",
  counts: { doing: 0, ready: 0, blocked: 0, stalled: 0, done: 3 },
  mentions: 0,
};

function board(over: Partial<BoardPayload>): BoardPayload {
  return {
    milestone: stone("open"),
    milestones: [],
    groups: { ...EMPTY_GROUPS, done: [row("tk-done1")] },
    team: [],
    hours: null,
    done_total: 3,
    seq: 1,
    pulse: PULSE,
    ...over,
  };
}

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  check("a landed chapter in focus derives complete", chapterComplete(board({ milestone: stone("landed") })));
  check(
    "landed wins even with work still in a group",
    chapterComplete(
      board({
        milestone: stone("landed"),
        groups: { ...EMPTY_GROUPS, take: [row("tk-late")] },
      }),
    ),
  );
  check("an open chapter with everything done derives complete", chapterComplete(board({})));
  check(
    "one card still in take means not complete",
    !chapterComplete(board({ groups: { ...EMPTY_GROUPS, take: [row("tk-open1")] } })),
  );
  check(
    "an unanswered board-wide mention does not hold the chapter open",
    chapterComplete(
      board({
        groups: {
          ...EMPTY_GROUPS,
          mentions: [{ id: "tk-x", title: "", by: "dev:berna", text: "?", ts: NOW }],
        },
      }),
    ),
  );
  check("no milestone in focus is never complete", !chapterComplete(board({ milestone: null })));
  check(
    "a freshly planned chapter with nothing closed is not a triumph",
    !chapterComplete(board({ done_total: 0, groups: EMPTY_GROUPS })),
  );

  // The drift case, verbatim from types.ts's header: a board one version behind
  // sends no `done` group and no `done_total` — and the a1d1005-era payload the
  // header describes. Derive false, never throw.
  const behind = board({});
  delete behind.done_total;
  delete behind.groups.done;
  let threw = false;
  let verdict = true;
  try {
    verdict = chapterComplete(behind);
  } catch {
    threw = true;
  }
  check("a board missing done/done_total derives false without throwing", !threw && !verdict);
}
