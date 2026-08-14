/* The stack, bottom right — what a comment LOOKS like when it lands.
 *
 * Every decision about which comments are news, what a preview says, how deep
 * the stack goes and when a toast leaves is already made, once, in `model.ts`.
 * Nothing in this file re-decides any of it: it renders a `Toast[]` it is
 * handed and reports three intentions back (expand, open, dismiss). That is the
 * same split `CardTile` has against `Board.tsx` and for the same reason — a
 * component that cannot invent a state cannot lose one either.
 *
 * THE IDIOM IS THE TILE'S, deliberately. `--pane` under a `--hair` hairline, a
 * 13px radius and `cubic-bezier(0.2, 0.8, 0.2, 1)` are what a card on this
 * board is made of (`board/CardTile.tsx`), so a notification about a card reads
 * as the same material arriving from off screen rather than as a second design
 * language parked in the corner. What it adds over a tile is the one thing a
 * tile never has: ELEVATION off the page — the drop shadow the floating
 * surfaces here already use (`chrome/MilestonePicker.tsx`,
 * `shared/Overlay.tsx`), which is the only kind of colour tokens.css does not
 * own, because a shadow is depth and not palette.
 *
 * WHY THE BUBBLE GROWS INSTEAD OF OPENING SOMETHING. A toast that had to open
 * the drawer to be read would make every comment cost the reader their place on
 * the board — and the drawer is 900px of thread for one sentence. So the body
 * is a button that expands the bubble IN PLACE to the whole message, and the
 * drawer is a SEPARATE, smaller affordance beside it. Two intentions, two
 * targets, neither reachable by accident: expanding pins the toast against its
 * own expiry (`model.ts::expire`), so a reader is never cut off mid-sentence.
 *
 * REDUCED MOTION SUPPRESSES THE MOTION AND NEVER THE CONTENT. The slide, the
 * scale and the height transition go; the toast, its text and both affordances
 * stay exactly where they were. `board/flip.ts::prefersReducedMotion` answers
 * it — asked live, per render, by the hook above (`useToasts.ts`).
 */
import { useEffect, useState } from "react";

import { Avatar } from "../shared/Avatar";
import { trim, type Toast } from "./model";

/** The design's easing, the tile's own — see the header. */
const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";

/** How tall a collapsed bubble's text may be: two lines at 12px/1.45. The
 *  expanded ceiling is generous rather than unbounded — a 4000-word comment
 *  must not become a full-height column — and scrolls inside itself past it. */
const COLLAPSED_H = 36;
const EXPANDED_H = 260;

const stackStyle: React.CSSProperties = {
  position: "fixed",
  right: "20px",
  bottom: "20px",
  zIndex: 60,
  width: "336px",
  display: "grid",
  gap: "10px",
  /* The stack must not eat clicks on the board underneath it: the container is
     transparent to the pointer and each bubble takes its own back. */
  pointerEvents: "none",
};

const bubble: React.CSSProperties = {
  boxSizing: "border-box",
  pointerEvents: "auto",
  background: "var(--pane)",
  /* Per-side longhands, never the shorthand — CardTile.tsx:100 argues it, and
     the rule is about this whole board, not about that one file. */
  borderStyle: "solid",
  borderWidth: "1px",
  borderColor: "var(--hair)",
  borderRadius: "13px",
  boxShadow: "0 12px 40px rgba(0, 0, 0, 0.32)",
  padding: "11px 12px",
  display: "grid",
  gap: "8px",
};

const bodyButton: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr)",
  gap: "9px",
  alignItems: "start",
};

const smallButton: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "10.5px",
  padding: "3px 8px",
  borderRadius: "20px",
  color: "var(--text-2)",
  background: "var(--pane-3)",
  whiteSpace: "nowrap",
};

export interface ToastStackProps {
  /** newest FIRST, as `model.ts::push` keeps it */
  toasts: readonly Toast[];
  /** the reader clicked the body: expand it in place, and pin it */
  onExpand: (id: string) => void;
  /** the × */
  onDismiss: (id: string) => void;
  /** the separate affordance — App's `openCard`, unchanged */
  onOpen: (task: string) => void;
  /** answered by `flip.ts::prefersReducedMotion`, live, above this component */
  reduced?: boolean;
}

function Bubble(props: {
  toast: Toast;
  onExpand: (id: string) => void;
  onDismiss: (id: string) => void;
  onOpen: (task: string) => void;
  reduced: boolean;
}): React.JSX.Element {
  const { toast, onExpand, onDismiss, onOpen, reduced } = props;
  /* The entrance, as state rather than as a keyframe: one render at rest, one
     frame later at home, and the transition does the rest. A keyframe would
     have to live in tokens.css and would replay on every re-render of a toast
     that is merely being expanded. Under reduced motion the bubble is BORN at
     home — there is no first frame to see. */
  const [home, setHome] = useState(reduced);
  useEffect(() => setHome(true), []);
  const motion = !reduced;
  return (
    <div
      data-testid="toast"
      data-task={toast.task}
      data-expanded={toast.expanded ? "1" : "0"}
      style={{
        ...bubble,
        ...(motion
          ? {
              transition: `transform 260ms ${EASE}, opacity 260ms ${EASE}`,
              opacity: home ? 1 : 0,
              transform: home ? "none" : "translateX(18px) scale(0.98)",
            }
          : {}),
      }}
    >
      <button
        type="button"
        data-testid="toast-body"
        style={bodyButton}
        onClick={() => onExpand(toast.id)}
      >
        <Avatar actor={toast.actor} size={26} />
        <div style={{ minWidth: 0 }}>
          <div
            data-testid="toast-title"
            style={{
              fontSize: "12.5px",
              fontWeight: 500,
              letterSpacing: "-0.02em",
              color: "var(--text)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {toast.cardTitle}
          </div>
          <div
            data-testid="toast-text"
            style={{
              fontSize: "12px",
              lineHeight: 1.45,
              color: "var(--text-2)",
              marginTop: "3px",
              whiteSpace: "pre-wrap",
              overflowY: toast.expanded ? "auto" : "hidden",
              maxHeight: `${toast.expanded ? EXPANDED_H : COLLAPSED_H}px`,
              ...(motion ? { transition: `max-height 240ms ${EASE}` } : {}),
            }}
          >
            {/* The WHOLE text is on the toast (`model.ts::Toast.text`), so
                expanding needs no second lookup and no second fetch. */}
            {toast.expanded ? toast.text : trim(toast.text)}
          </div>
        </div>
      </button>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button
          type="button"
          data-testid="toast-open"
          data-task={toast.task}
          className="mono"
          title={`open ${toast.task}`}
          style={smallButton}
          onClick={() => onOpen(toast.task)}
        >
          {`${toast.task} ↗`}
        </button>
        <button
          type="button"
          data-testid="toast-dismiss"
          aria-label="dismiss"
          title="dismiss"
          style={{ ...smallButton, background: "transparent", color: "var(--text-3)" }}
          onClick={() => onDismiss(toast.id)}
        >
          ×
        </button>
      </div>
    </div>
  );
}

/** Nothing at all when the stack is empty — not an empty fixed box sitting over
 *  the board's bottom-right column for the whole session. */
export function ToastStack(props: ToastStackProps): React.JSX.Element | null {
  const { toasts, onExpand, onDismiss, onOpen, reduced = false } = props;
  if (toasts.length === 0) return null;
  return (
    <div style={stackStyle} data-testid="toast-stack">
      {toasts.map((toast) => (
        <Bubble
          key={toast.id}
          toast={toast}
          onExpand={onExpand}
          onDismiss={onDismiss}
          onOpen={onOpen}
          reduced={reduced}
        />
      ))}
    </div>
  );
}
