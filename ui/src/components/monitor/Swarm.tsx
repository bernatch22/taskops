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
import { shortActor } from "../../format";
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
    what: "plans and dispatches; never holds a card",
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

  /* The centre is an orchestrator, and it is the one node in the diagram with no
   * edge of its own — a `dev:` never holds a card (the role rule). Sorted, so
   * "the first dev" does not depend on presence ordering. */
  const devs = team
    .map((member) => member.actor)
    .filter((actor) => actor.startsWith("dev:"))
    .sort();
  const centre = devs[0];

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

  return { nodes, edges, contested: edges.filter((e) => e.kind === "contested").length, quiet };
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
  const count = `${graph.nodes.length} ${graph.nodes.length === 1 ? "node" : "nodes"} · ${graph.contested} contested ${graph.contested === 1 ? "edge" : "edges"}`;

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
                  stroke={contested ? TONE_FG.warn : TONE_FG.neutral}
                  strokeWidth={contested ? 1.4 : 1}
                  strokeDasharray={contested ? "5 4" : undefined}
                  opacity={edge.kind === "lapsed" ? 0.35 : contested ? 0.9 : 0.55}
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
