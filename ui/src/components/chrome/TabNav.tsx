/* The three views, as a pill bar. This is the whole router.
 *
 * No router library and no URL: which view is on is state in App, so a tab is a
 * button that calls back. A hash route would be a second source of truth for one
 * boolean and a reload that lands on a card that no longer exists.
 *
 * The badge is a SLOT, not a hardcoded mention count: Attention carries the
 * pending mentions today, and a tab with nothing to say carries nothing. */

export type TabId = "attention" | "board" | "hours";

export interface Tab {
  id: TabId;
  name: string;
  /** Rendered as a pill next to the name; 0 or undefined renders nothing. */
  badge?: number;
}

export const TABS: readonly Tab[] = [
  { id: "attention", name: "Attention" },
  { id: "board", name: "Board" },
  { id: "hours", name: "Hours" },
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
