/* columns | flow — the Board page's own segmented control.
 *
 * `chrome/TabNav.tsx`'s pill bar, shrunk: same geometry vocabulary (a pane
 * strip, a hairline, the active pill on `--pane-3`), smaller, because this
 * chooses a way of READING one view and the tab bar chooses the view. Making it
 * a sixth tab was the alternative and it is wrong: the flow is the Board, drawn
 * differently, and a tab would put it beside Monitor and Actors as if it were
 * another page with another payload.
 *
 * It is not a router either — the choice is state on the page (`Board.tsx`),
 * remembered in `localStorage` and nowhere else. */

export type BoardView = "columns" | "flow";

export const VIEWS: ReadonlyArray<{ id: BoardView; name: string }> = [
  { id: "columns", name: "Columns" },
  { id: "flow", name: "Flow" },
];

const bar: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "3px",
  padding: "3px",
  borderRadius: "10px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
};

const base: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  padding: "5px 12px",
  borderRadius: "7px",
  fontSize: "12px",
  fontWeight: 450,
  letterSpacing: "-0.02em",
  whiteSpace: "nowrap",
};

export interface ViewToggleProps {
  active: BoardView;
  onSelect: (view: BoardView) => void;
}

export function ViewToggle({ active, onSelect }: ViewToggleProps): React.JSX.Element {
  return (
    <div style={bar} data-testid="board-view-toggle" role="group">
      {VIEWS.map((view) => {
        const on = view.id === active;
        return (
          <button
            key={view.id}
            type="button"
            data-view={view.id}
            aria-pressed={on}
            onClick={() => onSelect(view.id)}
            style={{
              ...base,
              color: on ? "var(--text)" : "var(--text-2)",
              background: on ? "var(--pane-3)" : "transparent",
            }}
          >
            {view.name}
          </button>
        );
      })}
    </div>
  );
}
