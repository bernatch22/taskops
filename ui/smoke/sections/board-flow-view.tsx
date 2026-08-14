/* The FLOW view — the dependency graph the Board page draws instead of columns.
 *
 * Two halves, pinned in the two places they can honestly be pinned:
 *
 *   the GRAPH   `components/flow/layout.ts`, pure — which nodes, which edges,
 *               which layer. Asserted on a hand-built DIAMOND, because a
 *               diamond is the one shape a naive "depth = 1 + first blocker"
 *               gets wrong: the join must land one layer past the LONGEST of
 *               its two paths, not the first one walked.
 *   the SHAPE   the rendered markup — the toggle offering both, the columns
 *               unchanged when they are the ones selected, the node states, and
 *               the holder's disc on a running node.
 *
 * What is NOT here is a pixel: the edge curves are measured from
 * `getBoundingClientRect` in a layout effect, and `react-dom/server` has no
 * layout. The overlay renders empty headlessly and that is the honest
 * boundary — the geometry that CAN be decided without a browser is all in
 * `layout.ts`, which is why that file exists.
 *
 * The rows are the server's own (`fixture.board`), cloned and re-identified: no
 * BoardRow shape is written by hand here, so a payload change breaks this
 * section instead of quietly agreeing with it. */
import { renderToStaticMarkup } from "react-dom/server";

import { Board, BoardColumns, VIEW_KEY } from "../../src/pages/Board";
import type { ViewStore } from "../../src/pages/Board";
import { flow } from "../../src/components/flow/layout";
import type { BlockedRow, BoardGroups, BoardPayload, BoardRow } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

/** A storage that remembers exactly one answer — the injectable seam
 *  `Board.tsx::ViewStore` exists for. */
function store(kept: string | null): ViewStore & { wrote: string[] } {
  const wrote: string[] = [];
  return {
    wrote,
    getItem: (key) => (key === VIEW_KEY ? kept : null),
    setItem: (_key, value) => void wrote.push(value),
  };
}

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const any =
    fixture.board.groups.take[0] ??
    fixture.board.groups.doing[0] ??
    fixture.board.groups.blocked[0];
  check("the fixture has a row to build the graph from", any !== undefined);
  if (!any) return;

  const clone = (id: string, over: Partial<BoardRow> = {}): BoardRow =>
    ({ ...(JSON.parse(JSON.stringify(any)) as BoardRow), id, ...over });
  const waits = (id: string, on: string[]): BlockedRow => ({ ...clone(id), waiting_on: on });

  /* ── The DIAMOND ──────────────────────────────────────────────────────
   *
   *      tk-old (done)      tk-root ──▶ tk-left ──▶ tk-right ──┐
   *      no edge: a closed        └───────────────────────────┴─▶ tk-join
   *      blocker is not
   *      reported at all
   *
   * ASYMMETRIC on purpose. A diamond whose two sides are the same length is not
   * a test of "longest path" at all — first-blocker-wins scores it identically,
   * and a mutation that replaces the max with the first blocker passes it (it
   * did, before this fixture was rewritten). So the two paths from `tk-root` to
   * `tk-join` are one hop and three, and only the long one puts the join in
   * layer 4.
   *
   * `tk-join` also names a blocker this payload does not carry — a card aged
   * past the `done` cap or in another chapter. It must produce NO edge, because
   * a line to a node that is not on screen is a line to nowhere. */
  const groups = {
    ...fixture.board.groups,
    merge: [],
    review: [],
    changes: [],
    reviewing: [],
    stalled: [],
    done: [clone("tk-old")],
    take: [clone("tk-root", { holder: null })],
    doing: [clone("tk-run", { holder: "agent:berna/w9", assignee: "agent:berna/w9" })],
    blocked: [
      waits("tk-left", ["tk-root"]),
      waits("tk-right", ["tk-left"]),
      waits("tk-join", ["tk-root", "tk-right", "tk-gone"]),
    ],
  } as BoardGroups;

  const graph = flow(groups);
  const layer = (id: string): number | undefined => graph.nodes.find((n) => n.id === id)?.layer;

  check("a closed card sits in the leftmost layer", layer("tk-old") === 0);
  check("in flight and ready share the middle band", layer("tk-run") === 1 && layer("tk-root") === 1);
  check("a blocked card sits one past its blocker", layer("tk-left") === 2 && layer("tk-right") === 3);
  check(
    "the diamond's join lands past the LONGEST path, not the first",
    layer("tk-join") === 4,
    JSON.stringify(graph.layers.map((l) => [l.layer, l.label, l.nodes.map((n) => n.id)])),
  );

  const edges = graph.edges.map((e) => `${e.from}→${e.to}`).sort();
  check(
    "every edge runs blocker → blocked, and only between nodes on screen",
    JSON.stringify(edges) ===
      JSON.stringify([
        "tk-left→tk-right",
        "tk-right→tk-join",
        "tk-root→tk-join",
        "tk-root→tk-left",
      ]),
    JSON.stringify(edges),
  );
  check(
    "a blocker the payload does not carry draws nothing",
    !edges.some((e) => e.includes("tk-gone")),
  );
  check(
    "the bands are named left to right",
    JSON.stringify(graph.layers.map((l) => l.label)) ===
      JSON.stringify(["Done", "In flight", "Waiting", "Waiting · 2", "Waiting · 3"]),
    JSON.stringify(graph.layers.map((l) => l.label)),
  );

  /* ── The two shapes ───────────────────────────────────────────────────── */

  const payload = { ...fixture.board, groups } as BoardPayload;

  const columnsOnly = renderToStaticMarkup(<BoardColumns board={payload} openCard={() => {}} />);
  const asColumns = renderToStaticMarkup(<Board board={payload} openCard={() => {}} store={store(null)} />);
  check("with nothing remembered the board opens on columns", asColumns.includes('data-testid="board"'));
  check(
    "and the columns are byte-identical — the toggle costs the kanban nothing",
    asColumns.includes(columnsOnly),
    asColumns,
  );
  check(
    "the toggle offers both ways to read it",
    asColumns.includes('data-testid="board-view-toggle"') &&
      asColumns.includes('data-view="columns"') &&
      asColumns.includes('data-view="flow"'),
  );
  check("a stored value the reader never wrote falls back to columns", !asColumns.includes('data-testid="flow"'));

  const asFlow = renderToStaticMarkup(
    <Board board={payload} openCard={(id) => h.opened.push(id)} store={store("flow")} />,
  );
  check("flow remembered opens on flow", asFlow.includes('data-testid="flow"'));
  check("and the kanban is not rendered underneath it", !asFlow.includes('data-testid="board"'));
  check(
    "every node in the graph is on screen",
    graph.nodes.every((n) => asFlow.includes(`data-card="${n.id}"`)),
    asFlow,
  );
  for (const [id, state] of [
    ["tk-old", "done"],
    ["tk-run", "doing"],
    ["tk-root", "ready"],
    ["tk-join", "blocked"],
  ] as const) {
    check(
      `${id} draws as ${state}`,
      asFlow.includes(`data-card="${id}" data-state="${state}"`),
      h.slice(asFlow, `data-card="${id}"`, "</button>"),
    );
  }
  check(
    "a node somebody is running carries that agent's disc",
    h.slice(asFlow, 'data-card="tk-run"', "</button>").includes('data-actor="agent:berna/w9"'),
    h.slice(asFlow, 'data-card="tk-run"', "</button>"),
  );
  check(
    "the edge overlay exists even where a headless render cannot measure it",
    asFlow.includes('data-testid="flow-edges"'),
  );
}
