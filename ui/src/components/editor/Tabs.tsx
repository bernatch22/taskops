/* The tab strip over the code: one tab per open file, the active one raised,
 * a close on each. `role="tablist"` and `aria-selected`, because it IS one.
 *
 * A tab is a `<div role="tab">` holding TWO buttons — select and close —
 * rather than one button with a close inside it, because a button inside a
 * button is invalid HTML and unreachable by keyboard (the same reason the
 * Worktrees row keeps its anchor as a sibling). The name drawn is the
 * basename; the whole path is the title, and it is the tab's identity. */
import { STATE_INK } from "./FileTree";
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

export function Tabs({ tabs, active, onSelect, onClose }: TabsProps): React.JSX.Element {
  return (
    <div role="tablist" data-testid="editor-tabs" style={strip}>
      {tabs.map((t) => {
        const on = t.path === active;
        const base = t.path.split("/").pop() ?? t.path;
        return (
          <div key={t.path} role="tab" data-testid="editor-tab" data-path={t.path} aria-selected={on} style={tab(on)}>
            <button type="button" onClick={() => onSelect(t.path)} title={t.path} style={name(on)}>
              <span style={{ color: on ? "var(--text)" : STATE_INK[t.state ?? "clean"] }}>{base}</span>
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
