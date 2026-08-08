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
import { Throughput } from "../components/monitor/Throughput";
import type { BoardPayload } from "../types";
import type { Client } from "../client";

export interface MonitorProps {
  board: BoardPayload;
  openCard: (id: string) => void;
  /** epoch seconds. Passed in so every pane shares one clock (panels.ts). */
  now: number;
  /** ONLY the Event stream uses it, and only because the log is not part of the
   *  board snapshot (see the pane below). Optional on purpose: the smoke
   *  harness renders this page with no wire at all, and a page that demanded a
   *  client would be a page that cannot be tested headlessly. */
  client?: Client | null;
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

export function Monitor({ board, openCard, now, client }: MonitorProps): React.JSX.Element {
  const g = board.groups;
  /** Every open row that can name a file, for the Edit surface. */
  const rows = [...g.take, ...g.doing, ...g.stalled, ...g.blocked];
  /* The chapter in focus is HISTORY, not a quiet live board. `!== "open"` and
   * not `=== "landed"`: a status this bundle has never heard of is safer read
   * as not-in-flight than drawn as work somebody could pick up. */
  const finished = board.milestone !== null && board.milestone.status !== "open";
  /* Open chapters only — `board.milestones` carries the landed ones too since
   * they stopped being invisible (types.ts), and this count is what the Chapter
   * pane says is in flight when the server could not focus one. */
  const open = board.milestones.filter((m) => m.status === "open").length;

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
        </div>

        <div style={right}>
          <Chapter milestone={board.milestone} chapters={open} repo={board.repo} />
          <Mentions mentions={g.mentions} now={now} onOpen={openCard} />
          {/* The one pane that reads the LOG and not the board snapshot, so it
              is the one pane handed the client: it pages `events` itself
              (useEvents.ts), resets to page one whenever `board` changes
              identity, and opens no socket of its own. `client` is optional and
              `null` draws the empty state — the headless harness renders this
              page with no wire. */}
          <EventStreamPane client={client ?? null} signal={board} now={now} />
        </div>
      </div>
    </div>
  );
}

export default Monitor;
