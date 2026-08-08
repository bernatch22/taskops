/* Swarm topology — who is attached to what, right now.
 *
 * The pane's own subtitle is its contract, and it is honoured literally:
 *
 *     "Who is attached to what, right now. Drawn from live leases and files[]
 *      — no new data."
 *
 * No verb, no payload key, no store, no second fetch, no socket. Every node and
 * every edge below is folded out of four slices the board already sends
 * (`SwarmProps` in panels.ts) — `team`, `doing`, `reviewing`, `stalled`.
 *
 * ── Why it is hand-written SVG ────────────────────────────────────────────
 *
 * The same reasoning `components/card/Patch.tsx` gives for shipping no syntax
 * highlighter: this is circles, lines and text, and a graph library is 200 kB
 * of bundle for that — bundle this dashboard COMMITS (`src/taskops/ui/`), so
 * every kilobyte is in the repo forever.
 *
 * ── Why the layout is arithmetic and not a simulation ─────────────────────
 *
 * `topology()` is a pure function: payload in, placed nodes out, positions a
 * deterministic circle by index. No force simulation, no animation loop, no
 * `Math.random()` — anywhere in this file. That is not an aesthetic preference,
 * it is what makes the pane testable: `ui/smoke/main.tsx` runs under
 * `react-dom/server` with no browser and no jsdom, so a layout that settles
 * over frames is a layout the harness can only render blank. Rendering the same
 * payload twice yields byte-identical coordinates, which is criterion 5.
 *
 * ── The chain, and why it was wrong ───────────────────────────────────────
 *
 * With one worker running, this pane used to read, on screen:
 *
 *     s14 ─── dev:berna ─── tk-13d115        ← what it drew
 *     dev:berna ─── s14 ─── tk-13d115        ← what is true
 *
 * The orchestrator sat between the worker and its card, touching the card. It
 * never touches one: `verbs/__init__.py::REGISTRY` refuses `take` to a `dev:`
 * in those exact words — "you are the orchestrator — you dispatch, you do not
 * hold cards". A pane whose whole subject is who is attached to what may not
 * draw the one attachment the server makes impossible.
 *
 * So the two edges around an actor are two different KINDS of fact:
 *
 *   dev:berna → agent:berna/s14   OWNERSHIP. It is in the name — `agent:<dev>/
 *                                 <name>` (`core/types.py::role_of`,
 *                                 `format.ts::ownerOf`) — and it is what
 *                                 `http/auth.py::authorize` enforces on the
 *                                 wire: a dev may act as its own agents and
 *                                 nobody else's. A standing fact about a name.
 *   agent:berna/s14 → tk-13d115   the LEASE. The live fact, the one that makes
 *                                 a card `doing`, and the one that expires.
 *
 * A dev's edges therefore go to its AGENTS and never to a card, and every card
 * edge starts at the agent that holds it. Nothing new is stored and nothing new
 * is fetched: `ownerOf()` on the actor id is the whole derivation. Drawn
 * differently on purpose (`--hair-2`, thinner) so an ownership edge cannot be
 * misread as "berna is working on that", and NOT counted in the header for the
 * same reason — the count is about live work, and a name is not work.
 *
 * An agent whose dev is not on `team` still draws: the ownership edge simply
 * has nothing at its far end and is not emitted. An orchestrator node is never
 * invented for a `dev:` the presence list does not carry.
 *
 * ── The caveat that must stay on screen ───────────────────────────────────
 *
 * A dashed edge means two cards DECLARED a path in common. `files` is typed
 * into `taskops_plan` by a human; the board never reads a diff and taskops never
 * parses source (`docs/fan-out.md` §10 declines to widen this on purpose). So
 * the dashed edge is, in the Edit surface pane's own words, "a warning, never a
 * lock" — that wording is reused verbatim rather than reworded, because two
 * spellings of one caveat is two things a reader has to reconcile.
 */
import { Pane, PaneEmpty } from "./Pane";
import { TONE_FG } from "../board/CardTile";
import { ownerOf, shortActor } from "../../format";
import type { Tone } from "../board/CardTile";
import type { SwarmEdge, SwarmGraph, SwarmKind, SwarmNode, SwarmProps } from "./panels";

/* ── the geometry, as constants ───────────────────────────────────────────── */

const W = 460;
const H = 330;
const CX = W / 2;
const CY = H / 2;
const RADIUS = 116;
/** Nodes start at twelve o'clock and go clockwise. */
const START = -Math.PI / 2;

/** Two decimals, so the markup a payload produces is stable to the byte and the
 *  harness can compare two renders as strings. */
const round = (n: number): number => Math.round(n * 100) / 100;

const TONE_OF: Record<SwarmKind, Tone> = {
  orchestrator: "accent",
  worker: "ok",
  verifier: "warn",
  lapsed: "danger",
  card: "neutral",
};

/** The four legend entries, exactly the four the mock draws — the roles. A card
 *  circle is what they are attached TO and is not a role, so it is not one. */
const LEGEND: { kind: SwarmKind; label: string; what: string }[] = [
  {
    kind: "orchestrator",
    label: "Orchestrator",
    what: "plans and dispatches; its edges go to its agents, never to a card",
  },
  { kind: "worker", label: "Worker", what: "holds a live work lease right now" },
  {
    kind: "verifier",
    label: "Verifier",
    what: "holds a review lease — a second lease on the same card",
  },
  { kind: "lapsed", label: "Lapsed", what: "assigned, and nobody is running it" },
];

/* ── the pure part ────────────────────────────────────────────────────────── */

/** Payload → nodes + edges + counts. Exported so the topology can be asserted
 *  without rendering anything at all. */
export function topology(props: SwarmProps): SwarmGraph {
  const { team, doing, reviewing, stalled } = props;

  /* Whom to draw, in ring order. Built by walking the groups in the order the
   * pane talks about them — worker beside its card, then the review lease, then
   * what stopped — so adjacency on the ring says something instead of nothing. */
  const kinds = new Map<string, SwarmKind>();
  const titles = new Map<string, string>();
  const order: string[] = [];
  const edges: SwarmEdge[] = [];

  function put(id: string, kind: SwarmKind, title: string): void {
    if (!kinds.has(id)) {
      order.push(id);
      kinds.set(id, kind);
      titles.set(id, title);
    }
  }

  /** One actor, one card, one edge. The actor may already be on the ring under
   *  another kind — the first one wins, so a worker who is also somebody's
   *  verifier elsewhere keeps the colour of the first lease it was drawn for
   *  and does not silently become two circles. */
  function attach(actor: string, card: { id: string; title: string }, kind: SwarmKind, edge: SwarmEdge["kind"], verb: string): void {
    if (actor === "") return;
    put(actor, kind, `${actor} — ${verb} ${card.id}`);
    put(card.id, "card", `${card.id} — ${card.title}`);
    edges.push({ from: actor, to: card.id, kind: edge });
  }

  for (const row of doing) {
    if (row.holder !== null) attach(row.holder, row, "worker", "lease", "holding");
  }
  /* A card under review gets a SECOND edge, to a differently coloured node, and
   * that is the truth rather than a duplicate: the review lease is its own mutex
   * (`store/reviews.py`) and the work lease above may still be held. */
  for (const row of reviewing) {
    if (row.holder !== null) attach(row.holder, row, "verifier", "lease", "checking");
  }
  /* Not a lease at all — an assignment with nothing running behind it, which is
   * why the edge is drawn faint and the node is `danger`. */
  for (const row of stalled) {
    attach(row.assignee, row, "lapsed", "lapsed", "assigned");
  }

  /* Nothing running is a real state and the common one — a board holds leases
   * during a fan-out and at almost no other moment. */
  const quiet = order.length === 0;

  /* A dashed edge per pair of DRAWN cards declaring a path in common. Only cards
   * already on the ring: an edge needs two nodes, and inventing a circle for a
   * card nobody is attached to would make this a second Edit surface. */
  const files = new Map<string, readonly string[]>();
  for (const row of [...doing, ...reviewing, ...stalled]) {
    if (kinds.get(row.id) === "card") files.set(row.id, row.files);
  }
  const declared = [...files.entries()];
  declared.forEach(([left, mine], i) => {
    const paths = new Set(mine);
    for (const [right, theirs] of declared.slice(i + 1)) {
      if (theirs.some((path) => paths.has(path))) {
        edges.push({ from: left, to: right, kind: "contested" });
      }
    }
  });

  /* The centre is an orchestrator. Its edges go to its AGENTS and to nothing
   * else — a `dev:` never holds a card (the role rule, refused by
   * `verbs/__init__.py::REGISTRY`). Sorted, so "the first dev" does not depend
   * on presence ordering. */
  const devs = team
    .map((member) => member.actor)
    .filter((actor) => actor.startsWith("dev:"))
    .sort();
  const centre = devs[0];

  /* OWNERSHIP, one edge per drawn agent: `agent:<dev>/<name>` says whose it is,
   * and that is the whole derivation. Only to a dev `team` actually carries —
   * an agent whose dev is absent stands on its own rather than conjuring an
   * orchestrator that is not there. Emitted after the leases so an ownership
   * edge draws UNDER nothing it could be confused with and the lease edges keep
   * their order. */
  const present = new Set(devs);
  for (const id of order) {
    if (kinds.get(id) === "card") continue;
    const dev = ownerOf(id);
    if (dev !== id && present.has(dev)) edges.push({ from: dev, to: id, kind: "owns" });
  }

  /* Any FURTHER dev joins the ring rather than fighting for the centre — one
   *  board, one middle. Real boards have one dev; two is not an error. */
  const ring: { id: string; kind: SwarmKind; title: string }[] = [
    ...devs.slice(1).map((d) => ({ id: d, kind: "orchestrator" as SwarmKind, title: `${d} — orchestrator` })),
    ...order.map((id) => ({
      id,
      kind: kinds.get(id) ?? "card",
      title: titles.get(id) ?? id,
    })),
  ];

  const nodes: SwarmNode[] = ring.map((node, i) => {
    const angle = START + (i * 2 * Math.PI) / ring.length;
    return {
      id: node.id,
      kind: node.kind,
      label: node.kind === "card" ? node.id : shortActor(node.id),
      title: node.title,
      x: round(CX + RADIUS * Math.cos(angle)),
      y: round(CY + RADIUS * Math.sin(angle)),
    };
  });

  if (centre !== undefined && !kinds.has(centre)) {
    nodes.unshift({
      id: centre,
      kind: "orchestrator",
      label: shortActor(centre),
      title: `${centre} — orchestrator; plans and dispatches, never holds a card`,
      x: CX,
      y: CY,
    });
  }

  return {
    nodes,
    edges,
    leases: edges.filter((e) => e.kind === "lease").length,
    contested: edges.filter((e) => e.kind === "contested").length,
    quiet,
  };
}

/* ── the drawing ──────────────────────────────────────────────────────────── */

const dot = (kind: SwarmKind): React.CSSProperties => ({
  display: "inline-block",
  width: "8px",
  height: "8px",
  borderRadius: "50%",
  background: TONE_FG[TONE_OF[kind]],
  marginRight: "7px",
  flex: "none",
});

function Node({ node }: { node: SwarmNode }): React.JSX.Element {
  const colour = TONE_FG[TONE_OF[node.kind]];
  const r = node.kind === "card" ? 13 : 16;
  return (
    <g data-testid="swarm-node" data-node={node.id} data-kind={node.kind}>
      <title>{node.title}</title>
      {/* the soft halo the mock draws under every circle */}
      <circle cx={node.x} cy={node.y} r={r + 9} fill={colour} opacity={0.09} />
      <circle
        cx={node.x}
        cy={node.y}
        r={r}
        fill="var(--pane)"
        stroke={colour}
        strokeWidth={node.kind === "card" ? 1.2 : 1.8}
      />
      <text
        x={node.x}
        y={node.y + r + 15}
        textAnchor="middle"
        fontSize="10"
        fill="var(--text-3)"
      >
        {node.label}
      </text>
    </g>
  );
}

export function Swarm(props: SwarmProps): React.JSX.Element {
  const graph = topology(props);
  const at = new Map(graph.nodes.map((n) => [n.id, n]));
  /* Nodes, LIVE LEASES, contested edges. Leases are counted apart now that two
   * kinds of line meet at an actor: an ownership edge is not work and is not in
   * this number, and a lapsed assignment is not a lease either — that is the
   * pane's own distinction, spent here rather than lumped. */
  const count = `${graph.nodes.length} ${graph.nodes.length === 1 ? "node" : "nodes"} · ${graph.leases} live ${graph.leases === 1 ? "lease" : "leases"} · ${graph.contested} contested ${graph.contested === 1 ? "edge" : "edges"}`;

  return (
    <Pane
      testId="pane-swarm"
      title="Swarm topology"
      subtitle="Who is attached to what, right now. Drawn from live leases and files[] — no new data."
      headPad="18px 20px 10px"
      aside={
        graph.quiet ? undefined : (
          <span className="mono" style={{ fontSize: "11px", color: "var(--text-3)" }} data-testid="swarm-count">
            {count}
          </span>
        )
      }
    >
      {graph.quiet ? (
        <PaneEmpty>
          Nobody holds a lease and nothing is assigned, so there is no topology to
          draw. This pane only ever sees live leases and what a card declared —
          never what a worker actually edited.
        </PaneEmpty>
      ) : (
        <div style={{ borderTop: "1px solid var(--hair)", padding: "10px 12px 0" }}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            width="100%"
            role="img"
            aria-label={"Swarm topology: " + count}
            data-testid="swarm-graph"
            style={{ display: "block" }}
          >
            <defs>
              <pattern id="swarm-grid" width="26" height="26" patternUnits="userSpaceOnUse">
                <path d="M 26 0 L 0 0 0 26" fill="none" stroke="var(--hair)" strokeWidth="0.6" />
              </pattern>
            </defs>
            <rect width={W} height={H} fill="url(#swarm-grid)" opacity={0.5} />
            {graph.edges.map((edge) => {
              const a = at.get(edge.from);
              const b = at.get(edge.to);
              if (a === undefined || b === undefined) return null;
              const contested = edge.kind === "contested";
              /* An ownership edge is a standing fact about a NAME, not work in
               * flight: hair-thin and quiet, so it can never be read as "this
               * dev is on that card". */
              const owns = edge.kind === "owns";
              return (
                <line
                  key={`${edge.kind}:${edge.from}->${edge.to}`}
                  data-testid="swarm-edge"
                  data-kind={edge.kind}
                  data-from={edge.from}
                  data-to={edge.to}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={contested ? TONE_FG.warn : owns ? "var(--hair-2)" : TONE_FG.neutral}
                  strokeWidth={contested ? 1.4 : owns ? 0.7 : 1}
                  strokeDasharray={contested ? "5 4" : undefined}
                  opacity={owns ? 1 : edge.kind === "lapsed" ? 0.35 : contested ? 0.9 : 0.55}
                />
              );
            })}
            {graph.nodes.map((node) => (
              <Node key={node.id} node={node} />
            ))}
          </svg>

          <div
            data-testid="swarm-legend"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              gap: "8px 16px",
              borderTop: "1px solid var(--hair)",
              margin: "6px -12px 0",
              padding: "12px 20px 14px",
            }}
          >
            {LEGEND.map((entry) => (
              <div key={entry.kind} style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", fontSize: "12px", color: "var(--text)" }}>
                  <span style={dot(entry.kind)} />
                  {entry.label}
                </div>
                <div style={{ fontSize: "11px", color: "var(--text-3)", marginTop: "2px", paddingLeft: "15px" }}>
                  {entry.what}
                </div>
              </div>
            ))}
            <div style={{ gridColumn: "1 / -1", fontSize: "11px", color: "var(--text-3)", lineHeight: 1.6 }}>
              A solid edge is a lease: the agent holding that card right now. The{" "}
              <strong style={{ fontWeight: 500 }}>hairline</strong> from a dev to an
              agent is ownership — it is in the name, <span className="mono">agent:&lt;dev&gt;/&lt;name&gt;</span>{" "}
              — and it is not work.
            </div>
            <div style={{ gridColumn: "1 / -1", fontSize: "11px", color: "var(--text-3)", lineHeight: 1.6 }}>
              A dashed edge is two cards declaring a file in common:{" "}
              <strong style={{ fontWeight: 500 }}>a warning, never a lock</strong>. It
              is what a card declared — never what a worker actually edited.
            </div>
          </div>
        </div>
      )}
    </Pane>
  );
}

export default Swarm;
