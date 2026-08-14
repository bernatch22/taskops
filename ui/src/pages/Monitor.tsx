/* Nova's Monitor — the first and central section, transcribed from
 * Taskops Nova.dc.html lines 168-417.
 *
 * This page is a LAYOUT and a set of slices, and deliberately nothing else. It
 * holds no derivation: each panel turns rows into its own view model, because a
 * page that derived for eight panels would be the file five workers all had to
 * edit, and criterion 4 of this card is that a panel lands without touching
 * Monitor.tsx. What travels between the two is `components/monitor/panels.ts`,
 * where every one of these prop objects is a declared interface.
 *
 * The grid is the design's, ratio for ratio:
 *
 *     minmax(0, 1.4fr)                        minmax(380px, 1fr)   sticky
 *     ┌──────────────────────────────────┐    ┌────────────────┐
 *     │ Live leases                      │    │ Chapter        │
 *     ├───────────────┬──────────────────┤    ├────────────────┤
 *     │ Throughput    │ Lease health     │    │ Addressed…     │
 *     │   1.25fr      │   1fr            │    ├────────────────┤
 *     ├───────────────┼──────────────────┤    │ Event stream   │
 *     │ Dependency    │ Edit surface     │    └────────────────┘
 *     │   1.1fr       │   1fr            │
 *     └───────────────┴──────────────────┘
 *
 * Eight sections in six layout slots — the three left blocks and the three right
 * panes the card counts. Nothing was merged and nothing dropped: Nova draws eight
 * `<section>`s here and eight are rendered.
 *
 * `align-items: start` on the outer grid is what lets the right column be
 * `position: sticky`. A stretched grid item is already as tall as the row and
 * sticky does nothing to it — that pairing is the design's, and losing either
 * half silently loses the behaviour. */
import { Chapter } from "../components/monitor/Chapter";
import { DependencyChain } from "../components/monitor/DependencyChain";
import { EditSurface } from "../components/monitor/EditSurface";
import { EventStreamPane } from "../components/monitor/EventStream";
import { LeaseHealth } from "../components/monitor/LeaseHealth";
import { LiveLeases } from "../components/monitor/LiveLeases";
import { Mentions } from "../components/monitor/Mentions";
import { Swarm } from "../components/monitor/Swarm";
import { Throughput } from "../components/monitor/Throughput";
import type { BoardPayload } from "../types";
import { EMPTY_FEED } from "../useEvents";
import type { EventFeed } from "../useEvents";

export interface MonitorProps {
  board: BoardPayload;
  openCard: (id: string) => void;
  /** epoch seconds. Passed in so every pane shares one clock (panels.ts). */
  now: number;
  /** The log, already read. ONLY the Event stream uses it, and only because the
   *  log is not part of the board snapshot (see the pane below). App owns the
   *  one `useEvents` call and hands the feed down — this page holds no fetch,
   *  exactly as it holds no board fetch. Optional on purpose: the smoke harness
   *  renders this page with no wire at all, so it falls back to `EMPTY_FEED`
   *  and the pane says nothing asked for the log. */
  feed?: EventFeed;
  /** The header picker's own `onSelect`, handed straight through to the Chapter
   *  pane so its `focus` action and the picker are ONE state (`App.tsx`). This
   *  page still holds nothing: it passes a prop it was given, exactly as it
   *  passes `openCard`. Optional for the harness, which renders this page with
   *  no wire at all. */
  onFocusChapter?: ((id: string) => void) | undefined;
}

const scroll: React.CSSProperties = {
  height: "100%",
  overflowY: "auto",
  padding: "0 24px 26px",
};

const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1.4fr) minmax(380px, 1fr)",
  gap: "16px",
  alignItems: "start",
};

const left: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "16px",
  minWidth: 0,
};

const right: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "16px",
  minWidth: 0,
  position: "sticky",
  top: 0,
};

const pair = (ratio: string): React.CSSProperties => ({
  display: "grid",
  gridTemplateColumns: `minmax(0, ${ratio}) minmax(0, 1fr)`,
  gap: "16px",
});

export function Monitor({
  board,
  openCard,
  now,
  feed,
  onFocusChapter,
}: MonitorProps): React.JSX.Element {
  const g = board.groups;
  /** Every open row that can name a file, for the Edit surface. */
  const rows = [...g.take, ...g.doing, ...g.stalled, ...g.blocked];
  /* The chapter in focus is HISTORY, not a quiet live board. `!== "open"` and
   * not `=== "landed"`: a status this bundle has never heard of is safer read
   * as not-in-flight than drawn as work somebody could pick up. */
  const finished = board.milestone !== null && board.milestone.status !== "open";
  /* Open chapters only — `board.milestones` carries the landed ones too since
   * they stopped being invisible (types.ts), and these are what the Chapter pane
   * LISTS when the server could not focus one (several open, `_facts.in_scope`
   * refusing to guess). A landed chapter is history and is not in that list. */
  const open = board.milestones.filter((m) => m.status === "open");
  /* Every OPEN card row, for the Chapter pane's per-chapter counts. One more
   * slice, not a derivation: the fold by chapter is the panel's own (panels.ts).
   * `mentions` is not a card row and `done` is a capped tail, so neither is in
   * it — the count this feeds is "open cards", which is the only one that can
   * be true. */
  const openRows = [
    ...g.take,
    ...g.doing,
    ...g.stalled,
    ...g.blocked,
    ...g.reviewing,
    ...g.review,
    ...g.changes,
    ...g.merge,
  ];

  return (
    <div style={scroll} data-testid="monitor">
      <div style={grid}>
        <div style={left}>
          <LiveLeases
            doing={g.doing}
            reviewing={g.reviewing}
            stalled={g.stalled}
            now={now}
            onOpen={openCard}
            standing={{
              ready: g.take.length,
              blocked: g.blocked.length,
              // The count behind the cap, not the tail `groups.done` carries.
              // `?? 0` for a board older than a1d1005, which sends neither
              // (types.ts) — the standing reads 0 closed rather than crashing.
              closed: board.done_total ?? 0,
            }}
            finished={finished}
          />

          <div style={pair("1.25fr")}>
            <Throughput report={board.hours} />
            <LeaseHealth doing={g.doing} reviewing={g.reviewing} stalled={g.stalled} now={now} />
          </div>

          <div style={pair("1.1fr")}>
            <DependencyChain
              blocked={g.blocked}
              others={[...g.take, ...g.doing, ...g.stalled]}
              onOpen={openCard}
            />
            <EditSurface rows={rows} />
          </div>

          {/* The foot of the LEFT column, which is where "to the left of the
              Event stream" lands: the stream is the last pane of the sticky
              right column, and the two read together — what is attached to what
              beside what just happened. It is full-width in this column because
              a radial diagram in a half-column is a diagram nobody can read. */}
          <Swarm
            team={board.team}
            doing={g.doing}
            reviewing={g.reviewing}
            stalled={g.stalled}
          />
        </div>

        <div style={right}>
          <Chapter
            milestone={board.milestone}
            open={open}
            rows={openRows}
            repo={board.repo}
            onFocus={onFocusChapter}
          />
          <Mentions mentions={g.mentions} now={now} onOpen={openCard} />
          {/* The one pane that reads the LOG and not the board snapshot, so it
              is the one pane handed the feed. App calls `useEvents` once
              (useEvents.ts) — it resets to page one whenever `board` changes
              identity and opens no socket — and this page passes the answer
              through. `feed` is optional and `EMPTY_FEED` draws the empty state:
              the headless harness renders this page with no wire. */}
          <EventStreamPane feed={feed ?? EMPTY_FEED} now={now} />
        </div>
      </div>
    </div>
  );
}

export default Monitor;
