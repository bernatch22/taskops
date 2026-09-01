/* The day pane whose FIRST session opened before its own midnight.
 *
 * `core/hours.py`'s edge rule credits an interval to the window its CLOSING
 * stamp is in — so a session that opens at 23:5x and closes past midnight is
 * filed under the NEXT day. Found live on /convo/ (2026-08-31, Europe/Madrid):
 * the pane said 17h 13m, held 286 sessions, and drew exactly ONE hour row —
 * `daysheet()` walked hour NUMBERS from the first session's 23 to the last's
 * 23, and the day after it walked 23..10, which is no rows at all. Only a day
 * nobody worked across its opening midnight survived.
 *
 * What this section pins is the repaired walk: slots by TIMESTAMP, so the
 * spill hours of the previous local day are drawn first, labelled with their
 * own wall clock, every session lands in a row, and the pane's total is still
 * the sum of its rows. The fixture is built from a LOCAL midnight for the same
 * reason `sections/actors.tsx`'s is: an hour is the reader's own hour, and a
 * UTC constant buckets differently in every zone this suite runs in. */
import { daysheet } from "../../src/components/actors/Daysheet";
import type { ActorSession, ReportPayload } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  const DAY = "2026-08-31";
  const midnight = new Date(2026, 7, 31).getTime() / 1000;
  const at = (h: number, m: number) => midnight + h * 3600 + m * 60;
  const run = (fromH: number, fromM: number, toH: number, toM: number, task: string): ActorSession => ({
    start: at(fromH, fromM),
    end: at(toH, toM),
    task,
    seconds: at(toH, toM) - at(fromH, fromM),
  });
  const sessions = (blocks: ActorSession[]) => ({
    seconds: blocks.reduce((n, b) => n + b.seconds, 0),
    human: "ignored — a merged day's total is this screen's own sum",
    cards: [...new Set(blocks.map((b) => b.task))],
    sessions: blocks,
    sessions_total: blocks.length,
  });

  /* 23:50 → 00:10 crosses the midnight and closes inside the 31st, so the
   * server filed it HERE; 00:15 and 02:05 are real small-hours work; then a
   * long silence until 12:00. The silence is 03:00–11:00 drawn empty — the
   * empty hour is the information — and the spill hour is one more row ABOVE
   * the day's own 00:00, not a wall the walk trips over. */
  const report = {
    from: midnight - 86400,
    to: midnight + 86400,
    days: [
      {
        day: DAY,
        by_actor: {
          "dev:berna": sessions([
            { start: at(23, 50) - 86400, end: at(0, 10), task: "tk-e5a340", seconds: 20 * 60 },
            run(0, 15, 0, 45, "tk-e5a340"),
            run(2, 5, 2, 25, "tk-c4445b"),
            run(12, 0, 12, 30, "tk-c4445b"),
          ]),
          "agent:berna/fable": sessions([run(13, 10, 13, 40, "tk-d34294")]),
        },
        closed: [],
        commits: 0,
      },
    ],
    by_actor: {},
    total: { seconds: 0, closed: 0 },
  } satisfies ReportPayload;

  const sheet = daysheet(report, ["dev:berna", "agent:berna/fable"]);
  const pane = sheet[0]!;
  const labels = pane.hours.map((h) => h.label);

  /* The walk: 23:00 of the eve first, then 00:00 through 13:00 — fifteen rows,
   * not one, and not none. The old numeric walk answered `[23:00]` here. */
  check(
    "daysheet spill: the pane opens on the eve's 23:00 and walks through to 13:00",
    labels.join(" ") ===
      "23:00 00:00 01:00 02:00 03:00 04:00 05:00 06:00 07:00 08:00 09:00 10:00 11:00 12:00 13:00",
    JSON.stringify(labels),
  );
  /* Two rows may share a wall label on such a pane (a 23:00 of the eve beside
   * a day reaching its own 23:00) — the fold's identity is the SLOT, so every
   * key is distinct whatever the labels do. */
  check(
    "daysheet spill: every hour row folds under its own key",
    new Set(pane.hours.map((h) => h.key)).size === pane.hours.length,
  );
  /* No session fell between the rows: the five counted intervals all landed,
   * each in the hour its start falls in, and the pane's total is still the sum
   * of its rows — the arithmetic the walk broke was exactly this one. */
  check(
    "daysheet spill: every session lands in a row, and the total is the sum of the rows",
    pane.hours.reduce((n, h) => n + h.sessions.length, 0) === 5 &&
      pane.hours[0]?.sessions[0]?.task === "tk-e5a340" &&
      pane.seconds === pane.hours.reduce((n, h) => n + h.seconds, 0) &&
      pane.seconds === 130 * 60,
    `${pane.hours.reduce((n, h) => n + h.sessions.length, 0)} sessions, ${pane.seconds / 60}m`,
  );
  /* The silence is drawn, not skipped: 03:00 through 11:00 are empty rows. */
  check(
    "daysheet spill: the small-hours silence is empty rows, not a hole",
    pane.hours.filter((h) => h.sessions.length === 0).length === 10,
    JSON.stringify(pane.hours.filter((h) => h.sessions.length === 0).map((h) => h.label)),
  );
}
