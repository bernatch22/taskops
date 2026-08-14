/* The FLOW view's geometry, decided WITHOUT a DOM.
 *
 * The columns say WHAT is happening; the flow says WHY — which card unblocks
 * which. Everything about that answer that is not pixels lives here: which
 * nodes exist, what state each is in, which edges connect them, and which
 * left-to-right layer each node sits in. `FlowView.tsx` measures and paints;
 * it decides nothing.
 *
 * WHAT THE PAYLOAD ACTUALLY CARRIES — read, not guessed. A `BoardRow`
 * (`verbs/pulse.py::_row`) has NO `after`: the card's dependency list exists in
 * `core/types.py::Card` and is sent whole only on the CARD read
 * (`types.ts::CardPayload.after`). The one dependency fact on the board payload
 * is `waiting_on`, which `pulse.py::run` attaches to the BLOCKED group alone,
 * from `core/graph.py::blockers` — and `blockers` filters to the dependencies
 * that have NOT closed.
 *
 * Two consequences, and both are honesty rather than a shortcut:
 *
 *   1. Every edge this view can draw ends on a blocked node. There is no such
 *      thing here as an edge out of a done card, because the moment a blocker
 *      closes the server stops reporting it — that IS the derivation ("closing
 *      a blocker frees its dependents by definition").
 *   2. A blocker the payload does not carry as a row (aged past the `done` cap,
 *      or in another chapter while the board is unfocused) yields no edge. A
 *      line to a node that is not on screen is a line to nowhere.
 *
 * So the sketch's three bands cannot come from the edges alone — a done card
 * with no surviving edge would land in the same layer as a running one. They
 * come from a FLOOR per state (done 0 · in flight 1 · waiting 2), and the
 * longest-path rule pushes a node further right than its floor whenever a chain
 * of open blockers demands it. Both rules in one line:
 *
 *     layer(n) = max(floor(state(n)), 1 + max(layer(b) for b in blockers(n)))
 *
 * which is exactly "longest path from the roots" on a graph whose roots have
 * been given a starting column by what they are. */
import type { BlockedRow, BoardGroups, BoardRow } from "../../types";

/** The four ways a node reads. The nine groups fold into these the way
 *  `pages/Board.tsx::columns` folds them into six columns — one derivation, in
 *  one place, and a node that cannot invent a state cannot lose one either. */
export type FlowState = "done" | "doing" | "ready" | "blocked";

/** Which band a state starts in. Not a style: it is the left-to-right reading
 *  of the sketch — HECHO · EN VUELO · ESPERANDO — turned into a number the
 *  longest-path rule can raise but never lower. */
export const FLOOR: Record<FlowState, number> = {
  done: 0,
  doing: 1,
  ready: 1,
  blocked: 2,
};

export interface FlowNode {
  id: string;
  row: BoardRow;
  state: FlowState;
  layer: number;
}

/** `from` unblocks `to`. The direction is the one the eye follows and the
 *  reverse of how the fact arrives (`to` is the row that named `from` in its
 *  `waiting_on`). */
export interface FlowEdge {
  from: string;
  to: string;
}

export interface FlowLayer {
  layer: number;
  /** the band's word, for the column head */
  label: string;
  nodes: FlowNode[];
}

export interface Flow {
  nodes: FlowNode[];
  edges: FlowEdge[];
  layers: FlowLayer[];
}

/** The fold, in `pulse.py`'s own group order so a node's position inside its
 *  layer is the board's order and not a re-sort. `review`, `changes`,
 *  `reviewing` and `stalled` are all IN FLIGHT here: the flow answers "what is
 *  moving and what is waiting on it", and a card handed in for review is a card
 *  whose dependents are still waiting. The six-column board is where their
 *  sub-states are spelled out; repeating that distinction here would be a
 *  second derivation of the same thing. */
const FOLD: ReadonlyArray<readonly [keyof BoardGroups, FlowState]> = [
  ["done", "done"],
  ["merge", "done"],
  ["doing", "doing"],
  ["reviewing", "doing"],
  ["review", "doing"],
  ["changes", "doing"],
  ["stalled", "doing"],
  ["take", "ready"],
  ["blocked", "blocked"],
];

function label(layer: number, rank: number): string {
  if (rank === 0) return "Done";
  if (rank === 1) return "In flight";
  /* Every layer past the first waiting band is still waiting — deeper, not
     different. The depth is appended rather than invented into a new word:
     "Waiting · 2" is a chain two blockers long, which is a fact, and any prose
     for it would not be. */
  return layer > FLOOR.blocked ? `Waiting · ${layer - FLOOR.blocked + 1}` : "Waiting";
}

/** The whole view, pure.
 *
 *  Cycles cannot occur — `after` is a DAG the server enforces — but the walk
 *  still carries an in-progress guard, because the alternative to a guard here
 *  is an infinite recursion in a render, and a payload is not a proof. */
export function flow(groups: BoardGroups): Flow {
  const nodes = new Map<string, FlowNode>();
  const state = new Map<string, FlowState>();
  for (const [group, kind] of FOLD) {
    for (const row of (groups[group] ?? []) as BoardRow[]) {
      if (nodes.has(row.id)) continue; // first group wins; a card is in one
      nodes.set(row.id, { id: row.id, row, state: kind, layer: FLOOR[kind] });
      state.set(row.id, kind);
    }
  }

  const edges: FlowEdge[] = [];
  const into = new Map<string, string[]>();
  for (const row of groups.blocked as BlockedRow[]) {
    for (const blocker of row.waiting_on) {
      if (!nodes.has(blocker) || !nodes.has(row.id)) continue;
      edges.push({ from: blocker, to: row.id });
      into.set(row.id, [...(into.get(row.id) ?? []), blocker]);
    }
  }

  const depth = new Map<string, number>();
  const walking = new Set<string>();
  const layerOf = (id: string): number => {
    const known = depth.get(id);
    if (known !== undefined) return known;
    const node = nodes.get(id);
    if (!node) return 0;
    if (walking.has(id)) return FLOOR[node.state]; // a cycle: fall back to the floor
    walking.add(id);
    let deep = FLOOR[node.state];
    for (const blocker of into.get(id) ?? []) deep = Math.max(deep, layerOf(blocker) + 1);
    walking.delete(id);
    depth.set(id, deep);
    return deep;
  };

  const placed = [...nodes.values()].map((node) => ({ ...node, layer: layerOf(node.id) }));
  const byLayer = new Map<number, FlowNode[]>();
  for (const node of placed) byLayer.set(node.layer, [...(byLayer.get(node.layer) ?? []), node]);

  const layers: FlowLayer[] = [...byLayer.keys()]
    .sort((a, b) => a - b)
    .map((n) => {
      const inside = byLayer.get(n) ?? [];
      const rank = Math.min(...inside.map((node) => FLOOR[node.state]));
      return { layer: n, label: label(n, rank), nodes: inside };
    });

  return { nodes: placed, edges, layers };
}
