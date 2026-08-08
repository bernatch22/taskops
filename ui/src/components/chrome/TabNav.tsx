/* The views, as a pill bar. This is the whole router.
 *
 * No router library and no URL: which view is on is state in App, so a tab is a
 * button that calls back. A hash route would be a second source of truth for one
 * boolean and a reload that lands on a card that no longer exists.
 *
 * Four tabs, in Nova's own order: Monitor first — it is the design's first and
 * central section, and the default view — then Board, then Actors, then
 * Worktrees, which are the sections the design draws after it. The order here IS
 * the order on screen, so it is not a detail: `TABS[0]` is what App opens on.
 *
 * A tab is only ever added WITH its page. `App.tsx`'s switch falls through to the
 * Board, so a tab whose branch does not exist is a dead tab that still looks
 * alive — it highlights, the view does not change, and nothing says why. That is
 * why `TabId` is a union and not a string: adding a member here is a compile
 * error in App until it is wired.
 *
 * The badge is a SLOT, not a hardcoded count: a tab with nothing to say carries
 * nothing. The board's pending mentions are on the KPI rail, not on a pill. */

export type TabId = "monitor" | "board" | "actors" | "worktrees";

export interface Tab {
  id: TabId;
  name: string;
  /** Rendered as a pill next to the name; 0 or undefined renders nothing. */
  badge?: number;
}

export const TABS: readonly Tab[] = [
  { id: "monitor", name: "Monitor" },
  { id: "board", name: "Board" },
  { id: "actors", name: "Actors" },
  { id: "worktrees", name: "Worktrees" },
];

const bar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "3px",
  padding: "4px",
  borderRadius: "13px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflowX: "auto",
  scrollbarWidth: "none",
};

const base: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "8px",
  padding: "8px 14px",
  borderRadius: "9px",
  fontSize: "13px",
  fontWeight: 450,
  letterSpacing: "-0.02em",
  whiteSpace: "nowrap",
  flex: "none",
  transition: "all 160ms cubic-bezier(0.2,0.8,0.2,1)",
};

export interface TabNavProps {
  tabs: readonly Tab[];
  active: TabId;
  onSelect: (tab: TabId) => void;
}

export function TabNav({ tabs, active, onSelect }: TabNavProps): React.JSX.Element {
  return (
    <nav style={bar} data-testid="tabs">
      {tabs.map((tab) => {
        const on = tab.id === active;
        return (
          <button
            key={tab.id}
            data-tab={tab.id}
            aria-current={on ? "page" : undefined}
            onClick={() => onSelect(tab.id)}
            style={{
              ...base,
              color: on ? "var(--text)" : "var(--text-2)",
              background: on ? "var(--pane-3)" : "transparent",
              boxShadow: on ? "0 1px 3px rgba(0,0,0,0.18)" : "none",
            }}
          >
            <span>{tab.name}</span>
            {tab.badge ? (
              <span
                className="num"
                data-testid={`badge-${tab.id}`}
                style={{
                  fontSize: "10.5px",
                  padding: "1px 7px",
                  borderRadius: "20px",
                  background: "var(--accent-soft)",
                  color: "var(--accent-hi)",
                }}
              >
                {tab.badge}
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
