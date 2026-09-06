/* The tab strip over the code: one tab per open file, the active one raised,
 * a close on each. `role="tablist"` and `aria-selected`, because it IS one.
 *
 * A tab is a `<div role="tab">` holding TWO buttons — select and close —
 * rather than one button with a close inside it, because a button inside a
 * button is invalid HTML and unreachable by keyboard (the same reason the
 * Worktrees row keeps its anchor as a sibling). The name drawn is the
 * basename; the whole path is the title, and it is the tab's identity. */
import { useEffect, useRef } from "react";

import { STATE_INK } from "./FileTree";
import { FileGlyph } from "./Icon";
import { shorten } from "./icons";
import type { FileState } from "../../types";

export interface TabRow {
  path: string;
  /** git's state of the file, for the name's ink; undefined until listed */
  state?: FileState | undefined;
  /** the listing no longer names it: deleted on disk since it was opened */
  gone?: boolean | undefined;
}

export interface TabsProps {
  tabs: readonly TabRow[];
  active: string | null;
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
}

const strip: React.CSSProperties = {
  // `flex: none`: in the column it sits in, the code pane below has a
  // content-sized basis, and a strip allowed to shrink lost half its height
  // to a tall file — the tabs were drawn cut through the middle (seen live).
  flex: "none",
  display: "flex",
  alignItems: "stretch",
  gap: "2px",
  overflowX: "auto",
  scrollbarWidth: "none",
  borderBottom: "1px solid var(--hair)",
  background: "var(--pane-2)",
};

const tab = (on: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  flex: "none",
  borderBottom: on ? "2px solid var(--accent)" : "2px solid transparent",
  background: on ? "var(--pane)" : "transparent",
});

const name = (on: boolean): React.CSSProperties => ({
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  padding: "8px 6px 7px 12px",
  fontSize: "12.5px",
  whiteSpace: "nowrap",
  color: on ? "var(--text)" : "var(--text-2)",
});

const close: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  padding: "8px 10px 7px 4px",
  fontSize: "12px",
  color: "var(--text-3)",
};

/** The strip SCROLLS on its own axis and never the page: a vertical wheel is
 *  turned into horizontal travel, a drag (past a few pixels, so a click is
 *  still a click) pans it, and the active tab is scrolled into view whenever
 *  it changes — twelve open files used to run off the right edge with the
 *  last name cut to "er…". */
export function Tabs({ tabs, active, onSelect, onClose }: TabsProps): React.JSX.Element {
  const stripRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; left: number; moved: boolean } | null>(null);

  useEffect(() => {
    const el = stripRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [active]);

  return (
    <div
      ref={stripRef}
      role="tablist"
      data-testid="editor-tabs"
      style={strip}
      onWheel={(e) => {
        const el = stripRef.current;
        if (!el || el.scrollWidth <= el.clientWidth) return;
        el.scrollLeft += Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
        e.preventDefault();
      }}
      onPointerDown={(e) => {
        const el = stripRef.current;
        if (el) drag.current = { x: e.clientX, left: el.scrollLeft, moved: false };
      }}
      onPointerMove={(e) => {
        const el = stripRef.current;
        const d = drag.current;
        if (!el || !d) return;
        const dx = e.clientX - d.x;
        if (!d.moved && Math.abs(dx) < 4) return;
        d.moved = true;
        el.scrollLeft = d.left - dx;
      }}
      onPointerUp={() => {
        drag.current = null;
      }}
      onPointerLeave={() => {
        drag.current = null;
      }}
      onClickCapture={(e) => {
        // a drag that panned the strip is not a click on the tab under it
        if (drag.current?.moved) e.stopPropagation();
      }}
    >
      {tabs.map((t) => {
        const on = t.path === active;
        const base = t.path.split("/").pop() ?? t.path;
        return (
          <div key={t.path} role="tab" data-testid="editor-tab" data-path={t.path} aria-selected={on} style={tab(on)}>
            <button type="button" onClick={() => onSelect(t.path)} title={t.path} style={name(on)}>
              <FileGlyph path={t.path} />
              <span style={{ color: on ? "var(--text)" : STATE_INK[t.state ?? "clean"], marginLeft: "6px" }}>{shorten(base)}</span>
              {t.gone ? (
                <span data-testid="editor-tab-gone" style={{ color: "var(--danger)", marginLeft: "6px" }}>
                  deleted
                </span>
              ) : null}
            </button>
            <button
              type="button"
              data-testid="editor-tab-close"
              aria-label={`close ${base}`}
              onClick={() => onClose(t.path)}
              style={close}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
