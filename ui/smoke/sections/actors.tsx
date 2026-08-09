import { renderToStaticMarkup } from "react-dom/server";

import { Actors, RECENT, actorRows, cardTitles, devRows } from "../../src/pages/Actors";
import { DevDetail, DevPanel, devCards } from "../../src/components/actors/DevPanel";
import { Daysheet, HourRow, RULE, dayLabel, daysheet, span } from "../../src/components/actors/Daysheet";
import { TABS } from "../../src/components/chrome/TabNav";
import type {
  ActorSession,
  BoardPayload,
  ReportPayload,
  ReviewingRow,
  TeamMember
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(_fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, opened } = h;

  /* ── Actors: a page about DEVS, and an agent is a LINE inside one ────
   *
   * The rows are built here for the reason §9 builds its own: this repo's board
   * cannot be made to hold a work lease, a review lease, a lapsed assignment and
   * a fortnight of hours at one instant from a test. The SHAPES are the
   * payload's (`BoardRow`, `TeamMember`, `ReportPayload` — the compiler checks
   * it), and `devRows()` is exported pure precisely so the folding rule can be
   * asserted without rendering.
   *
   * TWO devs, deliberately. A board with several is the case this shape exists
   * for — it is why the top level is a dev and not "the current user" — and this
   * repo's own board has one, so the two-dev case can only be pinned here. */

  const actorRow = (id: string, holder: string | null, assignee = "") =>
    ({
      id,
      title: id + " does a thing",
      priority: 1,
      assignee,
      holder,
      since: now - 100,
      quiet_for: null,
      files: [],
      labels: [],
    }) satisfies BoardPayload["groups"]["doing"][number];

  const hours = (seconds: number, cards: string[], closed?: number, commits?: number) => ({
    seconds,
    human: `${Math.round(seconds / 3600)}h`,
    cards,
    ...(closed === undefined ? {} : { closed }),
    ...(commits === undefined ? {} : { commits }),
  });

  const actorsProps = {
    team: [
      { actor: "dev:berna", seen: now, ago: 4 },
      { actor: "agent:berna/w1", seen: now, ago: 34 },
      { actor: "agent:berna/rv1", seen: now, ago: 60 },
      { actor: "agent:berna/idle", seen: now, ago: 900 },
      { actor: "dev:ana", seen: now, ago: 120 },
      { actor: "agent:ana/a1", seen: now, ago: 15 },
    ] satisfies TeamMember[],
    doing: [actorRow("tk-a11ffa", "agent:berna/w1"), actorRow("tk-d44444", "agent:ana/a1")],
    reviewing: [
      { ...actorRow("tk-b22eee", "agent:berna/rv1"), review_since: now - 30 },
    ] as unknown as ReviewingRow[],
    stalled: [actorRow("tk-c33ddd", null, "agent:berna/w9")],
    report: {
      from: now - 14 * 86400,
      to: now,
      days: [
        { day: "2026-08-07", by_actor: {}, closed: [], commits: 0 },
        {
          day: "2026-08-08",
          by_actor: {
            "agent:berna/w1": hours(7200, ["tk-a11ffa"], 1, 3),
            "dev:berna": hours(3600, ["tk-a11ffa"], 0, 0),
            // Worth zero today: criterion 9 says it gets no row at all.
            "agent:berna/zzz": hours(0, [], 0, 0),
            "agent:ana/a1": hours(3600, ["tk-d44444"], 1, 2),
          },
          closed: ["tk-a11ffa"],
          commits: 3,
        },
      ],
      by_actor: {
        "dev:berna": hours(3600, ["tk-a11ffa"], 2, 5),
        "agent:berna/w1": hours(7200, ["tk-a11ffa"], 1, 3),
        "agent:berna/rv1": hours(1800, [], 0, 0),
        "agent:berna/idle": hours(600, [], 0, 1),
        "agent:berna/w9": hours(0, [], 0, 0),
        "dev:ana": hours(1800, [], 1, 1),
        "agent:ana/a1": hours(3600, ["tk-d44444"], 1, 2),
      },
      total: { seconds: 10800, closed: 1 },
    },
    now,
    onOpen: (id: string) => opened.push(id),
  };

  const devs = devRows(actorsProps);

  /* Criterion 1 and 8: one card per DEV, none per agent, and two devs are two
   * cards each carrying its own agents. Sixty-seven tiles for sixty-six dead
   * sub-agents is what this replaced. */
  check(
    "actors: two devs are two rows, and every agent is inside one of them",
    devs.map((d) => d.dev).join(" ") === "dev:berna dev:ana" &&
      devs[0]?.agents.map((a) => a.actor).join(" ") ===
        "agent:berna/w1 agent:berna/rv1 agent:berna/w9 agent:berna/idle" &&
      devs[1]?.agents.map((a) => a.actor).join(" ") === "agent:ana/a1",
    devs.map((d) => `${d.dev}:${d.agents.length}`).join(" "),
  );
  /* The agents keep `actorRows()`' rank INSIDE their dev: a live work lease,
   * then a live review lease, then a lapsed assignment, then the rest. */
  check(
    "actors: inside a dev, a live lease outranks an agent holding none",
    devs[0]?.agents.map((a) => a.state ?? "none").join(" ") === "doing reviewing lapsed online",
  );
  /* The roles are still derived from the name and the lease — a verifier holds
   * the SECOND mutex and is not a shade of worker. */
  check(
    "actors: the worker and the verifier are told apart",
    devs[0]?.agents[0]?.role === "worker" && devs[0]?.agents[1]?.role === "verifier",
  );

  /* Criterion 7: who is on a card RIGHT NOW is a fact on the card, not behind a
   * click — it is the question somebody opens this tab to answer. */
  check(
    "actors: a live lease is counted and named without opening anything",
    devs[0]?.live === 2 &&
      devs[0]?.onCards.map((c) => `${c.actor}=${c.id}`).join(" ") ===
        "agent:berna/w1=tk-a11ffa agent:berna/rv1=tk-b22eee",
    JSON.stringify(devs[0]?.onCards),
  );

  /* A dev's figures are the SUM of it and its agents — 2+1, 5+3+1, and every
   * member's seconds — and the wording is `core/hours.py`'s. */
  check(
    "actors: a dev's figures are it and its agents, summed",
    devs[0]?.closed === 3 &&
      devs[0]?.commits === 9 &&
      devs[0]?.seconds === 13200 &&
      devs[0]?.worked === "3h 40m" &&
      devs[0]?.partial === false,
    `${devs[0]?.closed}/${devs[0]?.commits}/${devs[0]?.worked}`,
  );

  /* …and when ONE member cannot say a figure, the sum is REFUSED rather than
   * quietly taken over the rest: the dev's own is drawn and the panel says the
   * agents' are counted separately. `agent:berna/old` is a board one version
   * behind — no `closed`, no `commits` (types.ts: both optional). */
  const partialProps = {
    ...actorsProps,
    report: {
      ...actorsProps.report,
      by_actor: {
        ...actorsProps.report.by_actor,
        "agent:berna/old": hours(1800, ["tk-9f0000", "tk-9f0001"]),
      },
    },
  };
  const partial = devRows(partialProps).find((d) => d.dev === "dev:berna");
  check(
    "actors: a figure one member cannot say refuses the sum, it does not skip it",
    partial?.partial === true &&
      partial?.closed === 2 &&
      partial?.commits === 5 &&
      partial?.worked === "1h",
    `${partial?.closed}/${partial?.commits}/${partial?.worked}`,
  );
  /* That member is still HISTORY and not a free slot: it says what it carried. */
  const oldRow = partial?.agents.find((a) => a.actor === "agent:berna/old");
  check(
    "actors: an agent with no card carries its history, not a slot",
    oldRow?.card === null &&
      oldRow?.carried.join(",") === "tk-9f0000,tk-9f0001" &&
      oldRow?.presence === "not seen in 24h" &&
      oldRow?.closed === null,
  );
  /* `actorRows()` is still the fold underneath, and still per actor. */
  check(
    "actors: every actor the board can name reaches exactly one dev",
    actorRows(actorsProps).length ===
      devRows(actorsProps).reduce((n, d) => n + d.agents.length + (d.self ? 1 : 0), 0),
  );

  const actorsMarkup = renderToStaticMarkup(<Actors {...actorsProps} />);
  check("actors: the view renders", actorsMarkup.includes('data-testid="actors"'));
  check(
    "actors: one card per dev is DRAWN, and no card for an agent",
    (actorsMarkup.match(/data-testid="dev-card"/g) ?? []).length === 2 &&
      !actorsMarkup.includes('data-testid="actor-card"'),
  );
  check(
    "actors: NO WORKER SLOTS, under that name or any other",
    !/free|slot|capacity/i.test(actorsMarkup),
  );
  check(
    "actors: the window qualifier is said once, on the view",
    (actorsMarkup.match(/closed and commits are over the last 2 days/g) ?? []).length === 1,
  );
  check(
    "actors: the live lease is on the card, with a door to the card it holds",
    actorsMarkup.includes("2 agents on a card right now") &&
      actorsMarkup.includes('data-testid="dev-live-card" data-card="tk-a11ffa"'),
  );
  /* THE BAR PANEL IS DELETED, not restyled, and deleted from the PAGE: it
   * existed to compare actors against each other, and an ephemeral agent is a
   * label. Nothing replaces it here — the hours moved into the dev's own panel,
   * grouped by the one axis that is a fact about a person, the calendar day. */
  check(
    "actors: the hours bar panel is gone from the page, under any name",
    !actorsMarkup.includes('data-testid="pane-hours-today"') &&
      !actorsMarkup.includes('data-testid="hours-bar"') &&
      !actorsMarkup.includes("Hours worked today") &&
      !actorsMarkup.includes("agent:berna/zzz"),
  );

  /* Criterion 6: MORE AGENTS THAN THE CAP is said, never truncated in silence —
   * on the card (the recent few) and in the detail (the rows). */
  const many = Array.from({ length: 30 }, (_, i) => `agent:berna/n${i}`);
  const capProps = {
    ...actorsProps,
    team: many.map((actor, i) => ({ actor, seen: now, ago: i })) satisfies TeamMember[],
    doing: [],
    reviewing: [] as unknown as ReviewingRow[],
    stalled: [],
    report: {
      ...actorsProps.report,
      by_actor: Object.fromEntries(many.map((a) => [a, hours(600, [], 0, 0)])),
    },
  };
  const capped = devRows(capProps)[0]!;
  const capMarkup = renderToStaticMarkup(<Actors {...capProps} />);
  check(
    "actors: a dev with thirty agents draws a few names and counts the rest",
    capped.agents.length === 30 &&
      capMarkup.includes(`+${30 - RECENT} more`) &&
      (capMarkup.match(/agent:berna\/n\d+/g) ?? []).length === 0,
    capMarkup.split('data-testid="dev-recent"')[1]?.slice(0, 120),
  );
  /* Criterion 5: a board nobody has touched is ONE sentence, not an empty grid. */
  const actorsEmpty = renderToStaticMarkup(
    <Actors team={[]} doing={[]} reviewing={[]} stalled={[]} report={null} now={now} onOpen={() => {}} />,
  );
  check(
    "actors: nobody seen is one sentence",
    actorsEmpty.includes('data-testid="actors-none"') &&
      !actorsEmpty.includes('data-testid="dev-card"'),
  );

  /* The fourth tab exists AND has a page. A tab that falls through to the Board
   * is a dead tab that still looks alive; `App`'s page map is a
   * `Record<TabId, …>`, so this list and that map cannot disagree. */
  check(
    "actors: the tab bar is Nova's four, in Nova's order",
    TABS.map((t) => t.id).join(" ") === "monitor board actors worktrees",
  );

  /* ── The detail: an overlay, and a pane per DATE with an hour inside ──
   *
   * This section pinned a DRAWING — lanes per agent on a shared axis — and a
   * panel of bars beside it. Both are deleted, and this is the redesign that
   * replaced them: the window grouped by calendar day, newest FIRST and only the
   * newest open, each day's hours a row, each row folding open to its sessions.
   * A sub-agent adds nothing here; it is at most the name on a session.
   *
   * The folds are clicks and no handler fires under `react-dom/server`, so the
   * same two seams the rest of this dashboard uses carry the assertions:
   * `daysheet()` is exported PURE (everything that decides what the click lands
   * on), and `HourRow` takes `open` as a PROP, so an hour folded open is a tree
   * this harness can render — exactly as `Dossier` is exported beside `Drawer`.
   *
   * The fixture is built from a LOCAL midnight, not a fixed epoch: an hour is
   * the reader's own hour (`Date#getHours`), and a UTC constant would bucket
   * differently in every timezone this suite runs in.
   */

  const DAYSHEET_DAY = "2026-08-08";
  const midnight = new Date(2026, 7, 8).getTime() / 1000;
  const at = (h: number, m: number) => midnight + h * 3600 + m * 60;
  const run = (
    fromH: number,
    fromM: number,
    toH: number,
    toM: number,
    task: string,
  ): ActorSession => ({
    start: at(fromH, fromM),
    end: at(toH, toM),
    task,
    seconds: at(toH, toM) - at(fromH, fromM),
  });
  const sheetHours = (blocks: ActorSession[], total = blocks.length) => ({
    seconds: blocks.reduce((n, b) => n + b.seconds, 0),
    human: "ignored — a merged day's total is this screen's own sum",
    cards: [...new Set(blocks.map((b) => b.task))],
    sessions: blocks,
    sessions_total: total,
  });

  /* 10:38–11:12 is the session that CROSSES an hour boundary; 11:00 is then an
   * hour inside the day's span with nothing counted, and 12:20 belongs to an
   * AGENT — both are merged onto one list with no row of their own. */
  const sheetReport = {
    from: midnight - 86400,
    to: midnight + 86400,
    days: [
      {
        day: "2026-08-06",
        by_actor: { "dev:berna": { seconds: 60, human: "1m", cards: [] } },
        closed: [],
        commits: 0,
      },
      {
        day: "2026-08-07",
        by_actor: {
          "dev:berna": sheetHours([
            { ...run(15, 0, 15, 30, "tk-a11ffa"), start: at(15, 0) - 86400, end: at(15, 30) - 86400 },
          ]),
        },
        closed: [],
        commits: 0,
      },
      {
        day: DAYSHEET_DAY,
        by_actor: {
          "dev:berna": sheetHours([
            run(9, 0, 9, 58, "tk-e5a340"),
            run(10, 4, 10, 31, "tk-c4445b"),
            run(10, 38, 11, 12, "tk-c4445b"),
          ]),
          "agent:berna/w1": sheetHours([run(12, 20, 12, 40, "tk-d34294")], 4),
        },
        closed: [],
        commits: 0,
      },
    ],
    by_actor: {},
    total: { seconds: 0, closed: 0 },
  } satisfies ReportPayload;

  const sheetTitles = { "tk-c4445b": "the index: two columns" };
  const sheet = daysheet(
    sheetReport,
    ["dev:berna", "agent:berna/w1", "agent:berna/never"],
    sheetTitles,
  );

  /* Criterion 1: one pane per calendar day, NEWEST FIRST — the panel this
   * replaced drew the 7th above the 8th — and a day with no counted session at
   * all (the 6th sends no `sessions` key) is not a pane. */
  check(
    "daysheet: one pane per date, newest first, and no pane for a day with nothing",
    sheet.map((d) => d.day).join(" ") === "2026-08-08 2026-08-07",
    JSON.stringify(sheet.map((d) => d.day)),
  );
  check(
    "daysheet: a pane is headed by its weekday and date, not by an ISO string",
    sheet[0]?.label === "Saturday 8 August" && dayLabel("2026-08-07") === "Friday 7 August",
    `${sheet[0]?.label}`,
  );

  /* Criterion 2: the hours the day SPANS — first session's hour to the last's —
   * so the shape of the day is visible, and never 00–23. */
  const dayOne = sheet[0]!;
  check(
    "daysheet: the rows are the hours the day spans, not a full clock",
    dayOne.hours.map((h) => h.label).join(" ") === "09:00 10:00 11:00 12:00",
    JSON.stringify(dayOne.hours.map((h) => h.label)),
  );
  /* …and the hour with nothing in it is PRESENT. It is where the dropped gap
   * is, and the reason the day's total is smaller than last minus first. */
  check(
    "daysheet: an hour inside the span with nothing counted is a row, not a hole",
    dayOne.hours[2]?.label === "11:00" && dayOne.hours[2]?.sessions.length === 0,
  );

  /* Criterion 4: 10:38–11:12 belongs to the hour of its START and is ONE
   * session. Split, it would put 22m in 10:00 and 12m in 11:00 — two intervals
   * `core/hours.py` never produced, and 11:00 would stop being empty. */
  check(
    "daysheet: a session across an hour boundary stays whole, in the hour it started",
    dayOne.hours[1]?.sessions.length === 2 &&
      dayOne.hours[1]?.sessions[1]?.seconds === 34 * 60 &&
      dayOne.hours[1]?.seconds === 61 * 60 &&
      dayOne.hours[2]?.seconds === 0,
    JSON.stringify(dayOne.hours.map((h) => h.seconds / 60)),
  );
  check(
    "daysheet: the day's total is the sum of its hours, and the gaps are measured",
    dayOne.seconds === 139 * 60 &&
      dayOne.seconds === dayOne.hours.reduce((n, h) => n + h.seconds, 0) &&
      dayOne.gaps === 3 &&
      span(dayOne.dropped) === "1h 21m",
    `${dayOne.seconds / 60} ${dayOne.gaps} ${span(dayOne.dropped)}`,
  );
  /* The dev's sessions and its agents' are ONE list. The agent is not a lane,
   * not a row and not a heading — it is the name on a session. */
  check(
    "daysheet: the dev and its agents merge onto one list of sessions",
    dayOne.hours[3]?.sessions[0]?.actor === "agent:berna/w1" &&
      dayOne.hours[0]?.sessions[0]?.actor === "dev:berna",
  );
  check(
    "daysheet: a truncated answer says so rather than shrinking the day",
    dayOne.capped === true && sheet[1]?.capped === false,
  );
  /* A board one version behind sends no `sessions` at all — degraded, never
   * crashed (types.ts: both keys optional). */
  check(
    "daysheet: a payload without sessions degrades to no pane at all",
    daysheet(sheetReport, ["agent:berna/never"]).length === 0 &&
      daysheet(null, ["dev:berna"]).length === 0,
  );

  const opened2: string[] = [];
  const sheetMarkup = renderToStaticMarkup(
    <Daysheet days={sheet} onOpen={(id) => opened2.push(id)} />,
  );
  /* Criterion 1, drawn: the NEWEST pane is the open one and the rest are shut —
   * real buttons carrying `aria-expanded`, never a bare arrow glyph. */
  check(
    "daysheet: the newest pane is open and the older one is closed",
    (sheetMarkup.match(/data-testid="day-fold" aria-expanded="(true|false)"/g) ?? []).join(" ") ===
      'data-testid="day-fold" aria-expanded="true" data-testid="day-fold" aria-expanded="false"' &&
      sheetMarkup.includes(">Saturday 8 August<"),
    sheetMarkup.match(/aria-expanded="(true|false)"/g)?.join(" "),
  );
  /* Criterion 2, drawn: the empty hour SAYS so, and carries no fold — there is
   * nothing behind it, and an arrow that opens nothing is not a control. */
  check(
    "daysheet: the empty hour says nothing counted and is not a fold",
    sheetMarkup.includes('data-testid="hour-row" data-hour="11:00" data-empty="yes"') &&
      sheetMarkup.includes(">nothing counted<") &&
      (sheetMarkup.match(/data-testid="hour-fold"/g) ?? []).length === 3,
    sheetMarkup.match(/data-hour="[^"]+" data-empty="[^"]+"/g)?.join(" "),
  );
  check(
    "daysheet: an hour row carries its counted time and the cards touched",
    sheetMarkup.includes(">tk-c4445b<") && sheetMarkup.includes(">1h 1m<") &&
      sheetMarkup.includes(">58m<"),
  );
  /* An hour of the CLOSED pane is not drawn at all. */
  check(
    "daysheet: a closed date pane draws none of its hours",
    (sheetMarkup.match(/data-testid="hour-row"/g) ?? []).length === 4,
  );
  /* Criterion 3: folded open, the hour lists its sessions — start, end,
   * duration, card and title. `HourRow` takes `open` as a prop precisely so this
   * is reachable with no click. */
  const hourMarkup = renderToStaticMarkup(
    <HourRow hour={dayOne.hours[1]!} open onFold={() => {}} onOpen={(id) => opened2.push(id)} />,
  );
  check(
    "daysheet: an open hour lists its sessions with start, end, duration and card",
    (hourMarkup.match(/data-testid="session-row"/g) ?? []).length === 2 &&
      hourMarkup.includes("10:04 – 10:31") &&
      hourMarkup.includes(">27m<") &&
      hourMarkup.includes(">tk-c4445b</span>") &&
      hourMarkup.includes("the index: two columns"),
    hourMarkup.slice(0, 240),
  );
  /* Criterion 6: a session is a door to its CARD's dossier — the same `openCard`
   * every other view uses — and it is a real button. */
  check(
    "daysheet: a session opens the dossier of the card it was credited to",
    /<button[^>]*data-testid="session-row" data-card="tk-c4445b"/.test(hourMarkup),
  );
  /* A card the board cannot name right now is drawn as its ID ALONE, never with
   * a title nothing sent. */
  check(
    "daysheet: a session on a card nobody holds is its id and no invented title",
    renderToStaticMarkup(
      <HourRow hour={dayOne.hours[0]!} open onFold={() => {}} onOpen={() => {}} />,
    ).includes(">tk-e5a340</span></span>"),
  );
  /* The gaps are said as a figure, and the rule is on screen in
   * `core/hours.py`'s own words. */
  check(
    "daysheet: the dropped time is a figure and the arithmetic is beside it",
    sheetMarkup.includes("3 gaps · 1h 21m not counted") &&
      sheetMarkup.includes('data-testid="daysheet-rule"') &&
      sheetMarkup.includes("credited to the card that CLOSES it") &&
      RULE.includes("dropped whole, never capped"),
  );
  /* Nothing counted in the window is a SENTENCE, never an empty pane. */
  check(
    "daysheet: an actor with no counted time says so instead of drawing a pane",
    renderToStaticMarkup(<Daysheet days={[]} onOpen={() => {}} />).includes(
      'data-testid="daysheet-none"',
    ),
  );
  /* THE DELETED DESIGN, absent from the tree it was drawn in: no lane, no axis,
   * no per-agent row anywhere in this panel. */
  check(
    "daysheet: the lane-per-agent drawing is gone, not hidden",
    !sheetMarkup.includes("timesheet") && !sheetMarkup.includes("lane"),
  );

  /* Criterion 5 of the previous card, kept: the detail is a FULL OVERLAY reusing
   * the existing machinery. `DevPanel` is `shared/Overlay` — a portal — so it
   * renders nothing at all here, exactly as `Drawer` does; `DevDetail` beside it
   * is the document, and it is what the harness reads. */
  const sheetDev = devRows({ ...actorsProps, report: sheetReport })[0]!;
  check(
    "actors: the dev detail is the shared portal overlay, not a second one",
    renderToStaticMarkup(
      <DevPanel row={sheetDev} report={sheetReport} onOpen={() => {}} onClose={() => {}} />,
    ) === "" && !actorsMarkup.includes('data-testid="dev-figures"'),
  );
  const detailMarkup = renderToStaticMarkup(
    <DevDetail
      row={sheetDev}
      report={sheetReport}
      titles={sheetTitles}
      onOpen={() => {}}
      onClose={() => {}}
    />,
  );
  check(
    "actors: the detail is the figures and the date panes, and NOTHING per agent",
    detailMarkup.includes('data-testid="dev-figures"') &&
      detailMarkup.includes('data-testid="day-pane" data-day="2026-08-08"') &&
      !detailMarkup.includes('data-testid="dev-agent"') &&
      !detailMarkup.includes('data-testid="dev-card"') &&
      !detailMarkup.includes("timesheet"),
  );
  /* `cards` is a UNION and not a sum, so it survives a member that cannot say
   * its `closed`/`commits` — which is the case that refuses every other total. */
  check(
    "actors: the rail counts the distinct cards carried, and says who is running now",
    devCards(devs[0]!) === 1 &&
      detailMarkup.includes("2 running now") &&
      cardTitles(actorsProps)["tk-a11ffa"] === "tk-a11ffa does a thing",
    `${devCards(devs[0]!)}`,
  );
  const partialDetail = renderToStaticMarkup(
    <DevDetail row={partial!} report={actorsProps.report} onOpen={() => {}} onClose={() => {}} />,
  );
  check(
    "actors: a refused sum is said in words, and a real sum says it is one",
    partialDetail.includes('data-testid="dev-partial"') &&
      renderToStaticMarkup(
        <DevDetail row={devs[0]!} report={actorsProps.report} onOpen={() => {}} onClose={() => {}} />,
      ).includes('data-testid="dev-sum"'),
  );
}
