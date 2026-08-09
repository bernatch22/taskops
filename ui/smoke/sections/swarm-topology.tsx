import { renderToStaticMarkup } from "react-dom/server";

import { Swarm, topology } from "../../src/components/monitor/Swarm";
import type {
  BoardPayload,
  ReviewingRow,
  TeamMember
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(_fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;

  /* ── Swarm topology: who is attached to what ──────────────────────────
   *
   * The pane's whole claim is that it invents nothing — it folds four slices
   * the board already sends into nodes and edges. `topology()` is that fold,
   * exported as a pure function precisely so it can be asserted here WITHOUT
   * rendering, which is also why the layout is arithmetic and not a force
   * simulation: a simulation settles over frames and this harness has none.
   *
   * The rows are built here rather than taken from the fixture for the reason
   * §2b builds its own: this repo's board cannot be made to hold a live work
   * lease AND a live review lease on one card AND two cards declaring one path,
   * all at the same instant, from a test. The SHAPES are the payload's own
   * (`BoardRow`, `ReviewingRow`, `TeamMember` — the compiler checks that), and
   * the pane against the real fixture is asserted in §1 with the other panes. */

  const swarmRow = (id: string, holder: string | null, files: string[]) =>
    ({
      id,
      title: id + " does a thing",
      priority: 1,
      assignee: holder ?? "agent:berna/x",
      holder,
      since: now - 100,
      quiet_for: null,
      files,
      labels: [],
    }) satisfies BoardPayload["groups"]["doing"][number];

  const swarmTeam: TeamMember[] = [
    { actor: "dev:berna", seen: now, ago: 0 },
    { actor: "agent:berna/s1", seen: now, ago: 0 },
  ];
  const swarmDoing = [
    swarmRow("tk-aaa111", "agent:berna/s1", ["ui/src/shared.ts"]),
    swarmRow("tk-bbb222", "agent:berna/s2", ["ui/src/shared.ts", "ui/src/other.ts"]),
  ];
  const swarmReviewing = [
    { ...swarmRow("tk-aaa111", "agent:berna/rv1", ["ui/src/shared.ts"]), review_since: now - 30 },
  ] as unknown as ReviewingRow[];
  const swarmLapsed = [swarmRow("tk-ccc333", null, [])];

  const swarmGraph = topology({ team: swarmTeam, doing: swarmDoing, reviewing: swarmReviewing, stalled: swarmLapsed });
  const swarmEdge = (from: string, to: string, kind: string) =>
    swarmGraph.edges.some((e) => e.from === from && e.to === to && e.kind === kind);

  const swarmCards = new Set(swarmGraph.nodes.filter((n) => n.kind === "card").map((n) => n.id));

  /* The orchestrator's edges go to its AGENTS and to no card — the registry
   * refuses `take` to a `dev:`, so a dev→card edge is a claim the server makes
   * impossible. It is NOT "no edges at all": that was the bug, drawing
   * `s14 — dev:berna — tk-13d115` by letting the lease line cross the centre. */
  check(
    "swarm: the orchestrator is the centre and touches no card",
    swarmGraph.nodes[0]?.id === "dev:berna" &&
      swarmGraph.nodes[0]?.kind === "orchestrator" &&
      !swarmGraph.edges.some((e) => e.from === "dev:berna" && swarmCards.has(e.to)) &&
      !swarmGraph.edges.some((e) => e.to === "dev:berna" && swarmCards.has(e.from)),
  );
  check(
    "swarm: every card edge starts at the agent that holds it, never at a dev",
    swarmGraph.edges
      .filter((e) => e.kind === "lease" || e.kind === "lapsed")
      .every((e) => e.from.startsWith("agent:") && swarmCards.has(e.to)),
  );
  check(
    "swarm: every drawn agent hangs off its dev by an ownership edge",
    swarmGraph.nodes
      .filter((n) => n.kind !== "card" && n.kind !== "orchestrator")
      .every((n) => swarmEdge("dev:berna", n.id, "owns")),
  );
  /* Ownership is a standing fact about a name and not work, so it is drawn
   * apart (`--hair-2`, thinner) and left out of the header count. */
  check(
    "swarm: an ownership edge is not counted as a lease",
    swarmGraph.leases === swarmGraph.edges.filter((e) => e.kind === "lease").length &&
      swarmGraph.edges.some((e) => e.kind === "owns"),
  );
  /* An agent whose dev is not on `team` still draws; the far end is simply not
   * there. An orchestrator is never invented for an absent dev. */
  const swarmOrphan = topology({
    team: [{ actor: "dev:other", seen: now, ago: 0 }],
    doing: [swarmRow("tk-ddd444", "agent:berna/s9", [])],
    reviewing: [],
    stalled: [],
  });
  check(
    "swarm: an agent whose dev is absent draws itself and no ownership edge",
    swarmOrphan.nodes.some((n) => n.id === "agent:berna/s9") &&
      !swarmOrphan.nodes.some((n) => n.id === "dev:berna") &&
      !swarmOrphan.edges.some((e) => e.kind === "owns"),
  );
  check("swarm: a live lease is an edge from its worker", swarmEdge("agent:berna/s1", "tk-aaa111", "lease"));
  check(
    "swarm: a card under review has TWO edges, and the verifier is its own kind",
    swarmEdge("agent:berna/rv1", "tk-aaa111", "lease") &&
      swarmGraph.edges.filter((e) => e.to === "tk-aaa111" && e.kind === "lease").length === 2 &&
      swarmGraph.nodes.find((n) => n.id === "agent:berna/rv1")?.kind === "verifier" &&
      swarmGraph.nodes.find((n) => n.id === "agent:berna/s1")?.kind === "worker" &&
      /* three true edges around one card: two leases, and each agent's own
       * ownership edge back to the dev */
      swarmEdge("dev:berna", "agent:berna/s1", "owns") &&
      swarmEdge("dev:berna", "agent:berna/rv1", "owns"),
  );
  check(
    "swarm: a stalled card draws its lapsed owner",
    swarmGraph.nodes.find((n) => n.id === "agent:berna/x")?.kind === "lapsed" &&
      swarmEdge("agent:berna/x", "tk-ccc333", "lapsed"),
  );
  check(
    "swarm: two cards on one declared path are one dashed edge, counted once",
    swarmGraph.contested === 1 && swarmEdge("tk-aaa111", "tk-bbb222", "contested"),
  );
  check("swarm: a card nobody declared a shared file with has no dashed edge",
    !swarmGraph.edges.some((e) => e.kind === "contested" && (e.from === "tk-ccc333" || e.to === "tk-ccc333")));

  /* Criterion 5, and the reason `Math.random()` is banned in that file: the same
   * payload twice is the same markup, byte for byte. */
  const drawSwarm = () =>
    renderToStaticMarkup(
      <Swarm team={swarmTeam} doing={swarmDoing} reviewing={swarmReviewing} stalled={swarmLapsed} />,
    );
  const swarmFirst = drawSwarm();
  check("swarm: the same payload renders identically twice", swarmFirst === drawSwarm());
  check(
    "swarm: the header counts nodes, live leases and contested edges",
    swarmFirst.includes(`${swarmGraph.nodes.length} nodes · ${swarmGraph.leases} live leases · 1 contested edge`),
  );
  const swarmDrawn = (swarmFirst.match(/data-testid="swarm-node"/g) ?? []).length;
  check(
    "swarm: every node carries an accessible <title>",
    swarmDrawn === swarmGraph.nodes.length && (swarmFirst.match(/<title>/g) ?? []).length === swarmDrawn,
  );
  check("swarm: the dashed edge is drawn dashed", swarmFirst.includes('stroke-dasharray="5 4"'));
  /* Criterion 2: the two kinds are two different claims, so they may not be one
   * line. An ownership edge is `--hair-2` and thinner than any lease. */
  check(
    "swarm: an ownership edge is drawn quieter than a lease",
    swarmFirst.includes('data-kind="owns"') &&
      swarmFirst.includes('stroke="var(--hair-2)"') &&
      /* the mock's own numbers: a lease is 1.6 solid, ownership 1 and dashed 3 4 */
      /data-kind="owns"[^>]*stroke-width="1"[^>]*stroke-dasharray="3 4"/.test(swarmFirst) &&
      !/data-kind="lease"[^>]*stroke="var\(--hair-2\)"/.test(swarmFirst),
  );
  /* Criterion 1 and 3: the mockup's SVG is the specification, so its numbers are
   * asserted as numbers. The pane used to draw r=16 discs on a 460×330 board and
   * read as a bubble chart; nothing about the DATA changed to fix that. */
  check(
    "swarm: the svg is the mockup's viewBox, height and guide rings",
    swarmFirst.includes('viewBox="0 0 600 400"') &&
      swarmFirst.includes('height="440"') &&
      swarmFirst.includes('cx="300" cy="200" r="100"') &&
      swarmFirst.includes('cx="300" cy="200" r="130"') &&
      /* the grid is a 28px CSS background on the wrapper, not an SVG pattern */
      swarmFirst.includes("background-size:28px 28px") &&
      !swarmFirst.includes("<pattern"),
  );
  check(
    "swarm: a node is r=26 with a halo ring at r=34, opacity 0.22",
    /r="26" fill="var\(--pane\)" stroke="[^"]+" stroke-width="1.6"/.test(swarmFirst) &&
      /r="34" fill="none" stroke="[^"]+" stroke-width="1" opacity="0.22"/.test(swarmFirst),
  );
  /* Criterion 2: TWO texts per node — that is what makes it read as a diagram
   * rather than a bubble chart. */
  check(
    "swarm: a node carries its glyphs inside and its sub-label at dy=46",
    /dominant-baseline="central" font-size="12" font-weight="500"/.test(swarmFirst) &&
      /dy="46"[^>]*font-size="9.5"/.test(swarmFirst) &&
      swarmFirst.includes(">tk-aaa111<") &&
      swarmFirst.includes(">orchestrator<") &&
      /* the glyphs are `initials()` for an actor and the id without its `tk-`
       * for a card — three at most, because `w1` and `w10` exist */
      swarmFirst.includes(">ber<") &&
      swarmFirst.includes(">s1<") &&
      swarmFirst.includes(">aaa<") &&
      !swarmFirst.includes(">agent:berna/s1<"),
  );
  /* The ring is the mock's OUTER guide circle, centred where the mock centres
   * it: the coordinates in its SVG are 300+130·cosθ, 200+130·sinθ. */
  check(
    "swarm: every ring node sits on r=130 around the mockup's centre",
    swarmGraph.nodes
      .filter((n) => n.id !== "dev:berna")
      .every((n) => Math.abs(Math.hypot(n.x - 300, n.y - 200) - 130) < 0.05) &&
      swarmGraph.nodes[0]?.x === 300 &&
      swarmGraph.nodes[0]?.y === 200,
  );
  check(
    "swarm: every edge is the mockup's weight and opacity",
    /data-kind="lease"[^>]*stroke-width="1.6"[^>]*opacity="0.55"/.test(swarmFirst) &&
      /data-kind="contested"[^>]*stroke-width="1.6"[^>]*stroke-dasharray="5 4"[^>]*opacity="0.55"/.test(swarmFirst),
  );
  check(
    "swarm: the caveat is on the pane, in the Edit surface's own words",
    swarmFirst.includes("a warning, never a lock") &&
      swarmFirst.includes("never what a worker actually edited"),
  );

  /* Nothing running is the COMMON state, not an edge case: one sentence and no
   * graph — never an empty ring pretending to be a topology. */
  const swarmQuiet = renderToStaticMarkup(
    <Swarm team={swarmTeam} doing={[]} reviewing={[]} stalled={[]} />,
  );
  check(
    "swarm: nothing running is one sentence and no graph",
    swarmQuiet.includes('data-testid="pane-empty"') &&
      !swarmQuiet.includes('data-testid="swarm-graph"') &&
      !swarmQuiet.includes('data-testid="swarm-count"'),
  );
}
