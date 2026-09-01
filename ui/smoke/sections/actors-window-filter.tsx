import { renderToStaticMarkup } from "react-dom/server";

import { Actors, windowSaid } from "../../src/pages/Actors";
import { DevDetail } from "../../src/components/actors/DevPanel";
import { devRows } from "../../src/pages/Actors";
import {
  DEFAULT_HOURS_CHOICE,
  HOURS_CHOICES,
  LEGACY_DEFAULT_HOURS_CHOICE,
  choicesFor,
  lastMonth,
  snapped,
  windowFor,
} from "../../src/hoursWindow";
import type { HoursChoice } from "../../src/hoursWindow";
import type { BoardPayload, ReportPayload, ReviewingRow, TeamMember } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(_fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;

  /* ── The window is a CHOICE on screen and a spelling on the wire ──────
   *
   * The page opens on the last 30 days — the sliding figure that only shrinks
   * when work ages out — with the calendar one tap away. What is pinned here is
   * the seam between the two
   * halves: the pure mapping choice→`window=` (no handler fires under
   * `react-dom/server`, so a rule inside a click closure would have no test),
   * and the fact that every word the screen says about the SPAN is the
   * payload's own, never re-derived from `from`/`to`. */

  check(
    "actors window: the filter offers 7 days, 30 days, this month, last month and total",
    HOURS_CHOICES.map((c) => c.id).join(" ") === "7d 30d month last total" &&
      HOURS_CHOICES.map((c) => c.name).join(" · ") ===
        "7 days · 30 days · This month · Last month · Total",
    HOURS_CHOICES.map((c) => c.name).join(" · "),
  );
  /* The default slid off the calendar on purpose: on the 1st "this month" is
   * hours old, and a dev with 29 hours on screen the night before woke up to
   * 2h 50m. `hoursWindow.ts::DEFAULT_HOURS_CHOICE` argues it in full. */
  check(
    "actors window: the page opens on the last 30 days, not the calendar month",
    DEFAULT_HOURS_CHOICE === "30d" && windowFor(DEFAULT_HOURS_CHOICE) === "30d",
  );

  /* All but one are already the server's own spellings and are passed
   * through untouched (`verbs/_windows.py::parse`). */
  const mapped = (["7d", "30d", "month", "total"] as HoursChoice[]).map((c) =>
    windowFor(c, new Date(2026, 7, 14)),
  );
  check(
    "actors window: 7d, 30d, month and total travel as the board's own spellings",
    mapped.join(" ") === "7d 30d month total",
    mapped.join(" "),
  );

  /* THE ONE SPELLING COMPUTED HERE, and the reason it is: "the month before the
   * one the READER is in" is only knowable in the browser. In January that is
   * December of the PREVIOUS year — a naive `month - 1` writes `2026-00`, which
   * the server refuses, and a naive `year` writes `2027-12`, which it accepts
   * and answers with nothing. */
  check(
    "actors window: last month is the previous YYYY-MM, closed on both edges",
    windowFor("last", new Date(2026, 7, 14)) === "2026-07" &&
      windowFor("last", new Date(2026, 2, 1)) === "2026-02",
    windowFor("last", new Date(2026, 7, 14)),
  );
  check(
    "actors window: in JANUARY last month is December of the previous year",
    lastMonth(new Date(2026, 0, 1)) === "2025-12" &&
      lastMonth(new Date(2026, 0, 31)) === "2025-12" &&
      windowFor("last", new Date(2027, 0, 9)) === "2026-12",
    lastMonth(new Date(2026, 0, 1)),
  );

  /* ── What the screen SAYS it measured is what came back ───────────── */

  const actorRow = (id: string, holder: string | null) =>
    ({
      id,
      title: id + " does a thing",
      priority: 1,
      assignee: "",
      holder,
      since: now - 100,
      quiet_for: null,
      files: [],
      labels: [],
    }) satisfies BoardPayload["groups"]["doing"][number];

  const hours = (seconds: number, cards: string[], closed: number, commits: number) => ({
    seconds,
    human: `${Math.round(seconds / 3600)}h`,
    cards,
    closed,
    commits,
  });

  const report = {
    from: now - 13 * 86400,
    to: now,
    window: {
      window: "month",
      kind: "month",
      label: "August 2026",
      start: now - 13 * 86400,
      end: now,
    },
    days: [{ day: "2026-08-08", by_actor: {}, closed: [], commits: 0 }],
    days_total: 14,
    by_actor: {
      "dev:berna": hours(3600, ["tk-a11ffa"], 2, 5),
      "agent:berna/w1": hours(7200, ["tk-a11ffa"], 1, 3),
    },
    total: { seconds: 10800, closed: 3 },
  } satisfies ReportPayload;

  const props = {
    team: [{ actor: "dev:berna", seen: now, ago: 4 }] satisfies TeamMember[],
    doing: [actorRow("tk-a11ffa", "agent:berna/w1")],
    reviewing: [] as unknown as ReviewingRow[],
    stalled: [],
    report,
    now,
    onOpen: () => {},
  };

  const markup = renderToStaticMarkup(<Actors {...props} />);
  check(
    "actors window: every option is drawn, as the board's own segmented control",
    markup.includes('data-testid="actors-window-filter"') &&
      HOURS_CHOICES.every((c) => markup.includes(`data-window="${c.id}"`)),
    markup.match(/data-window="[^"]+"/g)?.join(" "),
  );
  /* The default is the pressed one, and it is 30 days — with no `choice` prop
   * at all, which is the state the page renders in on its own. */
  check(
    "actors window: with nothing told it, 30 days is the option pressed",
    /data-window="30d" aria-pressed="true"/.test(markup) &&
      (markup.match(/aria-pressed="true"/g) ?? []).length === 1,
    markup.match(/data-window="[^"]+" aria-pressed="[^"]+"/g)?.join(" "),
  );
  /* …and a page TOLD which one is on says that one instead. */
  check(
    "actors window: the pressed option is the caller's choice",
    /data-window="last" aria-pressed="true"/.test(
      renderToStaticMarkup(<Actors {...props} choice="last" onChoice={() => {}} />),
    ),
  );

  /* THE LABEL IS THE PAYLOAD'S. "August 2026" is `verbs/_windows.py::label`'s
   * word, arriving on `report.window.label`; nothing here derives a month from
   * `from`/`to`, which in a different zone is a different month. */
  check(
    "actors window: the qualifier prints the payload's own label, not a re-derivation",
    markup.includes("closed and commits are over August 2026") &&
      windowSaid(report, 2) === "2 devs · an agent is a line inside its dev · closed and commits are over August 2026",
    windowSaid(report, 2),
  );
  /* A board one version behind sends no `window` key: the older sentence, over
   * the buckets it DID send, is still true and is still what is drawn. */
  const { window: _dropped, ...older } = report;
  check(
    "actors window: a payload with no window degrades to counting the day buckets",
    windowSaid(older as ReportPayload, 1) ===
      "1 dev · an agent is a line inside its dev · closed and commits are over the last 1 day" &&
      windowSaid(null, 1) === "1 dev · the answer carried no hours, so no figure is drawn",
    windowSaid(older as ReportPayload, 1),
  );

  /* ── The per-dev overlay carries the same window ──────────────────── */

  const dev = devRows(props)[0]!;
  const detail = renderToStaticMarkup(
    <DevDetail row={dev} report={report} window="August 2026" onOpen={() => {}} onClose={() => {}} />,
  );
  check(
    "actors window: the opened dev shows worked, closed and commits for that window, and names it",
    detail.includes(">3h<") &&
      detail.includes(">closed<") &&
      detail.includes(">3<") &&
      detail.includes(">8<") &&
      detail.includes("over August 2026"),
    detail.match(/class="num"[^>]*>[^<]*</g)?.join(" "),
  );
  /* Told no window, it keeps the vaguer sentence rather than naming a span
   * nothing sent. */
  check(
    "actors window: an overlay told no window names none",
    renderToStaticMarkup(
      <DevDetail row={dev} report={report} onOpen={() => {}} onClose={() => {}} />,
    ).includes("over the report’s window"),
  );

  /* ── A PRE-CALENDAR HOST: the payload's shape is the feature detection ──
   *
   * A 0.3.1 host's `days()` reads `Nd` and nothing else, and answers an unknown
   * spelling with a SILENT 7d — so shipping "month" there shrank a reader's
   * window from the old always-14d without a word. The absence of `window` on
   * the payload is what says so; nothing here reads a version. */

  const legacy = older as ReportPayload;

  check(
    "actors window: a payload with NO window offers the Nd set only, defaulting to 14d",
    choicesFor(legacy).map((c) => c.id).join(" ") === "7d 14d 30d 90d" &&
      LEGACY_DEFAULT_HOURS_CHOICE === "14d" &&
      windowFor(LEGACY_DEFAULT_HOURS_CHOICE) === "14d",
    choicesFor(legacy).map((c) => c.id).join(" "),
  );
  /* The label is the CLIENT's here, and honest about what it is — the one case
   * it may speak, because an old host says nothing about the span it read. */
  check(
    "actors window: the degraded options say last N days, in the client's own words",
    choicesFor(legacy).map((c) => c.name).join(" · ") ===
      "last 7 days · last 14 days · last 30 days · last 90 days",
    choicesFor(legacy).map((c) => c.name).join(" · "),
  );
  /* …and a payload WITH window restores the calendar set exactly as shipped. */
  check(
    "actors window: a payload WITH window answers the calendar set, unchanged",
    choicesFor(report) === HOURS_CHOICES &&
      choicesFor(report).map((c) => c.id).join(" ") === "7d 30d month last total",
    choicesFor(report).map((c) => c.id).join(" "),
  );
  /* FIRST PAINT is deterministic: nothing has come back, so the set that holds
   * the current selection is drawn — the pressed option is never absent from
   * its own control — and with nothing selected, the calendar set the page is
   * born in. */
  check(
    "actors window: on first paint the set follows the selection, calendar when none",
    choicesFor(null).map((c) => c.id).join(" ") === "7d 30d month last total" &&
      choicesFor(null, "month").map((c) => c.id).join(" ") === "7d 30d month last total" &&
      choicesFor(null, "14d").map((c) => c.id).join(" ") === "7d 14d 30d 90d" &&
      choicesFor(undefined, "7d").map((c) => c.id).join(" ") === "7d 30d month last total",
    choicesFor(null, "14d").map((c) => c.id).join(" "),
  );
  /* THE SNAP, ONCE. A calendar choice meets a legacy answer and moves to 14d;
   * everything already in the answered set stays exactly where it is, which is
   * what stops the refetch from asking for a third window. */
  check(
    "actors window: month snaps to 14d on a legacy answer, and nothing else moves",
    snapped(legacy, "month") === "14d" &&
      snapped(legacy, "last") === "14d" &&
      snapped(legacy, "14d") === "14d" &&
      snapped(legacy, "7d") === "7d" &&
      snapped(report, "month") === "month" &&
      snapped(report, "30d") === "30d" &&
      snapped(null, "month") === "month" &&
      snapped(null, "30d") === "30d",
    [snapped(legacy, "month"), snapped(legacy, "7d"), snapped(report, "30d")].join(" "),
  );
  /* And on screen: the degraded control draws the four Nd options and presses
   * the one the snap settled on, with no calendar spelling anywhere in it. */
  const degraded = renderToStaticMarkup(
    <Actors {...props} report={legacy} choice="month" onChoice={() => {}} />,
  );
  check(
    "actors window: against a legacy payload the control draws 7d·14d·30d·90d, 14d pressed",
    (["7d", "14d", "30d", "90d"] as HoursChoice[]).every((id) =>
      degraded.includes(`data-window="${id}"`),
    ) &&
      !degraded.includes('data-window="month"') &&
      !degraded.includes('data-window="total"') &&
      /data-window="14d" aria-pressed="true"/.test(degraded) &&
      degraded.includes("last 14 days"),
    degraded.match(/data-window="[^"]+"/g)?.join(" "),
  );
}
