/* The FLOW — the open board's dependency graph, drawn left to right.
 *
 *     HECHO            EN VUELO              ESPERANDO
 *     [done ✓]─┐      [doing ◔ avatar]──┐   [blocked ⏳]
 *     [done ✓]─┴────▶                   ├─▶
 *                                        ┘
 *
 * Berna's sketch, and the reason it exists beside the columns: the columns say
 * WHAT each card is, the flow says WHY — which card unblocks which. Read-only,
 * exactly like the kanban: a node is a button and the only thing it does is
 * open the drawer.
 *
 * This file decides NOTHING about the graph. `layout.ts` is pure and tested
 * headlessly (which nodes, which edges, which layer, and what the payload can
 * honestly carry); what is left here is the half that needs a browser — measure
 * the nodes, draw the curves between them — plus the tile idiom at a compact
 * size.
 *
 * THE EDGES ARE MEASURED, NOT COMPUTED. A curve between two grid cells cannot
 * be known from the payload: it depends on wrapping, on the column widths and
 * on the scroll position. So the nodes hand over their elements, a layout
 * effect reads `getBoundingClientRect` relative to the container, and the SVG
 * overlay is drawn from that. Under `react-dom/server` there is no layout, so
 * the overlay renders empty and every assertion the smoke makes is against
 * `layout.ts` — a pixel path is not a promise a headless test can keep. */
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Avatar } from "../shared/Avatar";
import { prefersReducedMotion } from "../board/flip";
import type { MotionEnv } from "../board/flip";
import { flow } from "./layout";
import type { FlowNode, FlowState } from "./layout";
import type { BoardPayload } from "../../types";

/** `useLayoutEffect` warns under `react-dom/server` and the smoke renders every
 *  page there; without a DOM the effect is a no-op anyway (`useFlip.ts`). */
const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export interface FlowViewProps {
  board: BoardPayload;
  openCard: (id: string) => void;
  /** injectable exactly as `useFlip`'s is — the reduced-motion query, live */
  env?: MotionEnv | undefined;
}

/** The node's ink, per state. Nothing here is a literal colour (tokens.css). */
const TONE: Record<FlowState, string> = {
  done: "var(--ok)",
  doing: "var(--accent)",
  ready: "var(--text-2)",
  blocked: "var(--danger)",
};

/** The glyph the sketch puts on each band. `ready` carries none on purpose: a
 *  card nobody has started is the plain case, and a mark for "nothing yet" is
 *  noise on every node of the middle band. */
const GLYPH: Record<FlowState, string> = {
  done: "✓",
  doing: "◔",
  ready: "",
  blocked: "⏳",
};

const wrap: React.CSSProperties = {
  height: "100%",
  overflow: "auto",
  padding: "0 24px 26px",
};

const rail: React.CSSProperties = {
  position: "relative",
  display: "grid",
  gridAutoFlow: "column",
  gridAutoColumns: "minmax(228px, 1fr)",
  gap: "34px",
  alignItems: "start",
  minHeight: "100%",
};

const head: React.CSSProperties = {
  fontSize: "11px",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "var(--text-3)",
  padding: "0 2px 10px",
};

/** One card in the graph. The kanban tile's idiom — pane, hairline, 13px radius,
 *  the lift on hover — at the size a graph node can be: id line, title clamped
 *  to two lines, the holder's disc. Everything that distinguishes the states is
 *  handed in as `state`; the node derives nothing (`CardTile.tsx`'s rule). */
function Node({
  node,
  onOpen,
  hold,
  motion,
}: {
  node: FlowNode;
  onOpen: (id: string) => void;
  hold: (el: HTMLElement | null) => void;
  motion: boolean;
}): React.JSX.Element {
  const [lift, setLift] = useState(false);
  const { row, state } = node;
  const who = row.holder ?? row.assignee;
  return (
    <button
      type="button"
      ref={hold}
      data-testid="flow-node"
      data-card={row.id}
      data-state={state}
      onClick={() => onOpen(row.id)}
      onMouseEnter={() => setLift(true)}
      onMouseLeave={() => setLift(false)}
      onFocus={() => setLift(true)}
      onBlur={() => setLift(false)}
      style={{
        all: "unset",
        boxSizing: "border-box",
        cursor: "pointer",
        display: "block",
        width: "100%",
        background: "var(--pane)",
        borderStyle: state === "blocked" ? "dashed" : "solid",
        borderWidth: "1px",
        borderColor: state === "doing" ? "var(--accent-line)" : "var(--hair)",
        borderRadius: "13px",
        padding: "11px 12px",
        /* The done band is MUTED, not greyed: it is history, and it has to stay
           readable enough to follow an edge back into it. */
        opacity: state === "done" ? 0.66 : 1,
        ...(state === "doing" ? { boxShadow: "0 0 0 3px var(--accent-soft)" } : {}),
        ...(lift ? { transform: "translateY(-2px)" } : {}),
        /* The same easing the tile uses — and skipped entirely when the reader
           asked for less motion, which is the hover as much as the FLIP. */
        ...(motion ? { transition: "transform 150ms cubic-bezier(0.2, 0.8, 0.2, 1)" } : {}),
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
        <span className="mono" style={{ fontSize: "10.5px", color: "var(--text-3)" }}>
          {row.id}
        </span>
        <span style={{ fontSize: "11px", color: TONE[state] }}>{GLYPH[state]}</span>
      </div>
      <div
        style={{
          fontSize: "12.5px",
          fontWeight: 450,
          letterSpacing: "-0.02em",
          lineHeight: 1.35,
          marginTop: "6px",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {row.title}
      </div>
      {who ? (
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "9px" }}>
          {/* The same disc as everywhere else, in the actor's own colour, and
              `holder` ALONE decides `live` — a stalled node shows whose card it
              is, ghosted (`shared/Avatar.tsx`). */}
          <Avatar actor={who} live={row.holder !== null} size={20} />
        </div>
      ) : null}
    </button>
  );
}

/** A cubic between two node anchors: out of the right edge of `from`, into the
 *  left edge of `to`, with horizontal handles so the curve leaves and arrives
 *  flat — the reading direction stays horizontal even when the two nodes are
 *  rows apart. */
function curve(a: DOMRect, b: DOMRect, box: DOMRect): string {
  const x1 = a.right - box.left;
  const y1 = a.top + a.height / 2 - box.top;
  const x2 = b.left - box.left;
  const y2 = b.top + b.height / 2 - box.top;
  const bend = Math.max(24, (x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
}

export function FlowView({
  board,
  openCard,
  env = typeof window === "undefined" ? undefined : window,
}: FlowViewProps): React.JSX.Element {
  const graph = flow(board.groups);
  const nodes = useRef(new Map<string, HTMLElement>());
  const rail_ = useRef<HTMLDivElement | null>(null);
  const [paths, setPaths] = useState<{ key: string; d: string }[]>([]);
  /* The effect runs after EVERY commit — including the one it causes itself by
     storing the paths. The last drawing, serialised, is what stops that: an
     unchanged measurement writes nothing and the loop ends after one pass. */
  const drawn_ = useRef("");
  const motion = !prefersReducedMotion(env);

  const hold = (id: string) => (el: HTMLElement | null) => {
    if (el) nodes.current.set(id, el);
    else nodes.current.delete(id);
  };

  /* Measured after every commit, because a refetch can add a node, close one,
     or move it into another layer — and every edge that touches it is then
     wrong. Cheap: one rect per node, no observer, no timer. */
  useIsomorphicLayoutEffect(() => {
    const box = rail_.current?.getBoundingClientRect();
    if (!box) return;
    const drawn: { key: string; d: string }[] = [];
    for (const edge of graph.edges) {
      const a = nodes.current.get(edge.from);
      const b = nodes.current.get(edge.to);
      if (!a || !b) continue;
      drawn.push({
        key: `${edge.from}→${edge.to}`,
        d: curve(a.getBoundingClientRect(), b.getBoundingClientRect(), box),
      });
    }
    const stamp = JSON.stringify(drawn);
    if (stamp === drawn_.current) return;
    drawn_.current = stamp;
    setPaths(drawn);
  });

  return (
    <div style={wrap} data-testid="flow">
      <div style={rail} ref={rail_}>
        {/* Under the nodes, and never in the way of a click. */}
        <svg
          data-testid="flow-edges"
          style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "visible" }}
        >
          {paths.map((path) => (
            <path
              key={path.key}
              d={path.d}
              fill="none"
              stroke="var(--accent-line)"
              strokeWidth="1.5"
            />
          ))}
        </svg>
        {graph.layers.map((layer) => (
          <div key={layer.layer} data-testid="flow-layer" data-layer={layer.layer}>
            <div style={head}>{layer.label}</div>
            <div style={{ display: "grid", gap: "10px", position: "relative" }}>
              {layer.nodes.map((node) => (
                <Node
                  key={node.id}
                  node={node}
                  onOpen={openCard}
                  hold={hold(node.id)}
                  motion={motion}
                />
              ))}
            </div>
          </div>
        ))}
        {graph.nodes.length === 0 ? (
          <div style={{ color: "var(--text-3)", fontSize: "13px" }}>Nothing open.</div>
        ) : null}
      </div>
    </div>
  );
}

export default FlowView;
