/* A portal, a backdrop, and ONE Escape that closes the top-most overlay only.
 *
 * WHO owns Escape is `overlayStack.ts` — a plain module with no DOM in it, so
 * "the top-most one, and only that one" is a rule that can be run under node. All
 * this file adds is the keyboard: one listener for the whole pile, attached when
 * it becomes non-empty and removed when it empties, so N overlays are still one
 * handler and a leaked entry cannot outlive its component (the pop IS the
 * effect's cleanup).
 *
 * `capture: true` so the overlay hears Escape before a focused control inside it
 * can swallow it — a textarea is exactly where that matters — and the stack, not
 * the event's path, still decides who gets it. */
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { depth, escape, push } from "./overlayStack";

type Close = () => void;

let listening = false;

function onKey(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  // One Escape closes ONE overlay, never the pile — and if nothing is open the
  // key is left alone rather than quietly eaten.
  if (!escape()) return;
  event.preventDefault();
  event.stopPropagation();
}

/** Own Escape while mounted, as the top-most overlay. Exported because a popover
 *  is an overlay too: the milestone dropdown has no scrim and no portal, so it
 *  does not render an `<Overlay>`, but "Escape closes the TOP-MOST one" must stay
 *  ONE mechanism — a second keydown listener somewhere else is exactly the bug
 *  `overlayStack.ts` was written to prevent. This file stays the only thing that
 *  knows what a keyboard is. */
export function useOverlayStack(onClose: Close): void {
  // The close handler is re-made on every render of the parent; the stack entry
  // must not be, or the pop below could remove a stranger's slot. So the entry is
  // a stable thunk that reads the latest handler through a ref.
  const latest = useRef(onClose);
  latest.current = onClose;

  useEffect(() => {
    const pop = push(() => latest.current());
    if (!listening && typeof document !== "undefined") {
      document.addEventListener("keydown", onKey, true);
      listening = true;
    }
    return () => {
      pop();
      if (depth() === 0 && listening && typeof document !== "undefined") {
        document.removeEventListener("keydown", onKey, true);
        listening = false;
      }
    };
  }, []);
}

const backdrop: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  /* A literal, and not a token: Nova's scrim is the same near-black in both
   * themes (the dossier block of Taskops Nova.dc.html), because a scrim is the
   * absence of the page rather than one of its surfaces. Inventing a
   * `--scrim` per theme would make the light one a grey haze over white. */
  background: "rgba(6,7,14,0.6)",
  backdropFilter: "blur(14px)",
  zIndex: 60,
  display: "grid",
  placeItems: "center",
  padding: "30px",
  animation: "tk-fade 140ms ease-out",
};

export interface OverlayProps {
  onClose: Close;
  label: string;
  children: React.ReactNode;
  /** The panel's width. A prop with a default rather than a second overlay: the
   *  dossier is a document and reads at 900px, the dev detail is a DRAWING —
   *  lanes on a shared time axis — and a narrow axis is an axis nobody can read.
   *  Everything else about the two is identical, and the one thing that must
   *  never be copied is the Escape ownership below. */
  width?: string | undefined;
}

export function Overlay({ onClose, label, children, width }: OverlayProps): React.JSX.Element | null {
  useOverlayStack(onClose);
  if (typeof document === "undefined") return null;

  return createPortal(
    /* Portalled to the body rather than rendered in place: the drawer must not
     * inherit a transform, a filter or an overflow clip from whatever panel
     * happened to hold the tile that opened it. */
    <div
      style={backdrop}
      data-testid="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose(); // the backdrop, not the panel
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          width: width ?? "min(900px, 100%)",
          maxHeight: "calc(100vh - 60px)",
          background: "var(--pane)",
          color: "var(--text)",
          border: "1px solid var(--hair-2)",
          borderRadius: "20px",
          boxShadow: "0 40px 120px rgba(0,0,0,0.55)",
          display: "grid",
          gridTemplateRows: "auto 1fr auto",
          minHeight: 0,
          overflow: "hidden",
          animation: "tk-lift 240ms cubic-bezier(0.2,0.9,0.2,1)",
        }}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
