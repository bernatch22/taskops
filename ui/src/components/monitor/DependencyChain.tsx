/* Dependency chain — Taskops Nova.dc.html lines 301-319.
 *
 * The INDENT is the relation. The design binds a per-row `{{ d.pad }}` on a
 * leading spacer and nothing else draws the edge: no line, no arrow, no arrow
 * head. A blocker renders above what it blocks, one step further left, and the
 * eye reads the chain off the left margin. So `DagNode.depth` is not decoration
 * — it is the pane's entire claim, and computing it wrong is the only way this
 * panel can lie.
 *
 * ── The walk, and why it is bounded ───────────────────────────────────────
 *
 * `waiting_on` comes from `core/graph.py::blockers`, and the graph it reads is
 * whatever the board was told: `taskops_update after=` adds an edge and nothing
 * refuses A→B→A. The board is right to allow it — a cycle is a real planning
 * mistake and hiding it would leave two cards stalled with no visible reason —
 * but a naive depth-first walk over one hangs the browser, which turns a
 * planning mistake into an unusable dashboard.
 *
 * So the walk carries its own path and stops on two conditions: a node already
 * on the current path (a cycle — emitted ONCE, marked, not followed), and
 * `MAX_DEPTH` (a chain longer than the indent can express). Nodes reachable
 * only from inside a cycle would otherwise never be emitted at all, so what the
 * roots did not reach is emitted afterwards at depth 0 rather than silently
 * dropped. Rendering a cycle honestly beats both looping and hiding it.
 */
import { PaneTileButton, Pane, PaneEmpty } from "./Pane";
import { TONE_FG } from "../board/CardTile";
import type { DagNode, DependencyChainProps, Tone } from "./panels";

/** How deep the indent may go. Eight steps is 126px of spacer — past that the
 *  title column is narrower than the id beside it, and the chain stops reading
 *  as a chain. A deeper graph is not truncated: the tail renders flattened at
 *  the cap, which is visible, rather than omitted, which is not. */
const MAX_DEPTH = 8;

/** One indent step, in px. */
const STEP = 18;

interface Node {
  id: string;
  title: string;
  /** ids this one waits FOR */
  blockers: readonly string[];
  /** on the board, or only named by a `waiting_on` we cannot resolve */
  known: boolean;
}

function index(props: DependencyChainProps): Map<string, Node> {
  const nodes = new Map<string, Node>();
  // Only cards IN a relation. `others` is every open row Monitor could pass
  // (take + doing + stalled) and listing all of them would drown the chain in
  // rows that wait on nothing — a blocker earns its line by being named.
  const named = new Set<string>();
  for (const row of props.blocked) for (const id of row.waiting_on) named.add(id);
  for (const row of props.others) {
    if (named.has(row.id)) {
      nodes.set(row.id, { id: row.id, title: row.title, blockers: [], known: true });
    }
  }
  for (const row of props.blocked) {
    nodes.set(row.id, {
      id: row.id,
      title: row.title,
      blockers: row.waiting_on,
      known: true,
    });
  }
  // A `waiting_on` may name a card outside the four groups Monitor passes —
  // another milestone's, or one already closed and not yet reflected. Naming it
  // as unresolved keeps the chain complete; dropping it would draw a blocked
  // card with nothing above it, which is the one thing this pane must not do.
  for (const row of props.blocked) {
    for (const id of row.waiting_on) {
      if (!nodes.has(id)) nodes.set(id, { id, title: "(not on this board)", blockers: [], known: false });
    }
  }
  return nodes;
}

function noteFor(node: Node, nodes: Map<string, Node>): string {
  if (!node.known) return "closed, or another chapter";
  const live = node.blockers.filter((id) => nodes.has(id));
  if (live.length === 0) return "clear — nothing above it";
  if (live.length === 1) return `waits on ${live[0]}`;
  return `waits on ${live.length} cards`;
}

function toneFor(node: Node, cyclic: boolean, nodes: Map<string, Node>): Tone {
  if (cyclic) return "danger";
  if (!node.known) return "neutral";
  return node.blockers.some((id) => nodes.has(id)) ? "warn" : "ok";
}

/** Blockers first, each dependent one step in. Returns the rows in render
 *  order; every node is emitted at least once. */
export function chain(props: DependencyChainProps): DagNode[] {
  const nodes = index(props);
  const dependents = new Map<string, string[]>();
  for (const node of nodes.values()) {
    for (const id of node.blockers) {
      if (!nodes.has(id)) continue;
      const kids = dependents.get(id) ?? [];
      kids.push(node.id);
      dependents.set(id, kids);
    }
  }

  const out: DagNode[] = [];
  const emitted = new Set<string>();

  const emit = (node: Node, depth: number, cyclic: boolean): void => {
    out.push({
      id: node.id,
      title: cyclic ? `${node.title} — cycle` : node.title,
      depth,
      note: cyclic ? `already above: ${node.id} waits on itself` : noteFor(node, nodes),
      tone: toneFor(node, cyclic, nodes),
    });
    emitted.add(node.id);
  };

  const walk = (id: string, depth: number, path: readonly string[]): void => {
    const node = nodes.get(id);
    if (!node) return;
    if (path.includes(id)) {
      emit(node, Math.min(depth, MAX_DEPTH), true);
      return; // the cycle is stated and NOT followed — this is the bound
    }
    emit(node, Math.min(depth, MAX_DEPTH), false);
    if (depth >= MAX_DEPTH) return;
    for (const kid of dependents.get(id) ?? []) walk(kid, depth + 1, [...path, id]);
  };

  // A root is a node nothing above it is waiting for — i.e. it blocks, and is
  // not blocked by, anything we can see.
  for (const node of nodes.values()) {
    if (node.blockers.filter((id) => nodes.has(id)).length === 0) walk(node.id, 0, []);
  }
  // Whatever the roots could not reach lives entirely inside a cycle. It is
  // still real work; it renders flat, marked, instead of vanishing.
  for (const node of nodes.values()) {
    if (!emitted.has(node.id)) walk(node.id, 0, []);
  }
  return out;
}

const row: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  gap: "12px",
  alignItems: "center",
};

const dot: React.CSSProperties = {
  width: "7px",
  height: "7px",
  borderRadius: "50%",
  marginRight: "12px",
  flex: "none",
};

const label: React.CSSProperties = {
  fontSize: "13.5px",
  fontWeight: 450,
  letterSpacing: "-0.02em",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const idStyle: React.CSSProperties = {
  fontSize: "10.5px",
  color: "var(--faint)",
  marginLeft: "10px",
  flex: "none",
};

export function DependencyChain(props: DependencyChainProps): React.JSX.Element {
  const nodes = chain(props);
  return (
    <Pane
      testId="pane-dag"
      title="Dependency chain"
      subtitle="The block clears when the row above closes."
      headPad="18px 20px 10px"
    >
      {nodes.length === 0 ? (
        <PaneEmpty>Nothing is waiting on anything. Every open card is free to move.</PaneEmpty>
      ) : (
        <div style={{ padding: "4px 10px 12px" }}>
          {nodes.map((node, i) => (
            <PaneTileButton
              key={`${node.id}-${i}`}
              testId="dag-node"
              cardId={node.id}
              onOpen={props.onOpen}
              pad="9px 10px"
              style={row}
            >
              <div style={{ display: "flex", alignItems: "center", minWidth: 0 }}>
                <span style={{ width: `${node.depth * STEP}px`, flex: "none" }} />
                <span style={{ ...dot, background: TONE_FG[node.tone] }} />
                <span
                  style={{
                    ...label,
                    color: node.tone === "neutral" ? "var(--text-3)" : "var(--text)",
                  }}
                >
                  {node.title}
                </span>
                <span className="mono" style={idStyle}>
                  {node.id}
                </span>
              </div>
              <span style={{ fontSize: "11px", color: TONE_FG[node.tone], whiteSpace: "nowrap" }}>
                {node.note}
              </span>
            </PaneTileButton>
          ))}
        </div>
      )}
    </Pane>
  );
}
