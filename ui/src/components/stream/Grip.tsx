/* The handle that widens the rail — a drag, and nothing else.
 *
 * It is its own component for one reason: `EditorView` holds no hooks (it is
 * the pure half the headless harness renders, `pages/Editor.tsx` argues the
 * split), and a drag is three listeners on the DOCUMENT. Putting them here
 * keeps that split intact — the harness renders this element and no listener
 * ever fires, exactly as it renders `StreamRail` without a socket.
 *
 * THE LISTENERS ARE ON THE DOCUMENT, not on the handle. A `mousemove` bound to
 * a 6px strip is lost the first time the pointer outruns the render, which on
 * a fast drag is immediately: the cursor leaves the strip, the strip stops
 * hearing, and the pane sticks halfway. Bound to the document for the life of
 * the drag, the pointer can go anywhere — including outside the window — and
 * the pane still follows it.
 *
 * The width is the CALLER's state (App, beside which tree is open) so that a
 * reader who sizes the rail and leaves the tab comes back to the size they
 * chose. This component stores nothing.
 */
import { useEffect, useRef, useState } from "react";

/** What the rail may be dragged between. The floor is the width the entry
 *  markup was drawn for — narrower and a file chip cannot show enough of a
 *  path to be worth clicking. The ceiling leaves the code pane a readable
 *  column on a 1440px screen; past that the reader wants the Stream to be the
 *  page, not the rail. */
export const MIN_WIDTH = 240;
export const MAX_WIDTH = 760;

/** Where a drag from `startWidth` by `dx` pixels lands. Pure and exported so
 *  the clamp is pinned by calling it — no pointer, no jsdom. The rail is on
 *  the RIGHT, so dragging LEFT (negative dx) makes it wider: the sign is the
 *  whole reason this is a function and not two lines inside a handler. */
export function widthAfter(startWidth: number, dx: number): number {
  return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth - dx));
}

export function Grip({
  width,
  onWidth,
}: {
  width: number;
  onWidth: (px: number) => void;
}): React.JSX.Element {
  const [dragging, setDragging] = useState(false);
  const from = useRef<{ x: number; width: number } | null>(null);

  useEffect(() => {
    if (!dragging) return;
    const move = (e: MouseEvent): void => {
      const start = from.current;
      if (!start) return;
      onWidth(widthAfter(start.width, e.clientX - start.x));
    };
    const up = (): void => setDragging(false);
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
    /* While a drag is on, the whole document takes the resize cursor and stops
       selecting text — otherwise the drag paints the code pane blue behind the
       handle, which reads as a bug in the editor rather than a resize. */
    const had = document.body.style.cursor;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.style.cursor = had;
      document.body.style.userSelect = "";
    };
  }, [dragging, onWidth]);

  return (
    <div
      data-testid="stream-grip"
      role="separator"
      aria-orientation="vertical"
      aria-label="resize the stream"
      title="drag to resize · double-click to reset"
      onMouseDown={(e) => {
        from.current = { x: e.clientX, width };
        setDragging(true);
      }}
      onDoubleClick={() => onWidth(DEFAULT_WIDTH)}
      style={{
        position: "absolute",
        left: "-3px",
        top: 0,
        bottom: 0,
        width: "7px",
        cursor: "col-resize",
        zIndex: 4,
        // Invisible at rest and lit while dragging: it is an edge, and an edge
        // that draws itself is a border the reader did not ask for.
        background: dragging ? "var(--accent)" : "transparent",
      }}
    />
  );
}

/** The width the rail opens at, and the one a double-click returns to. */
export const DEFAULT_WIDTH = 320;
