/* The segmented control, once.
 *
 * `board/ViewToggle.tsx` drew it first — `chrome/TabNav.tsx`'s pill bar, shrunk,
 * because choosing a way of READING one view is not choosing a view. The Actors
 * page needs the same gesture for its hours window, so the geometry moved HERE
 * and `ViewToggle` became one caller of it rather than a second style: two bars
 * that look almost alike is how a dashboard stops looking like one thing.
 *
 * It is not a router and it stores nothing. The choice is state on the page that
 * owns it, and this draws it. `name` is the attribute the option id is written
 * into (`data-view`, `data-window`) so each caller keeps the hooks its own smoke
 * section already reads. */

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

export interface SegmentedProps<Id extends string> {
  /** `data-testid` on the bar — the caller's own hook */
  testid: string;
  /** the `data-<name>` each option carries */
  name: string;
  options: ReadonlyArray<{ id: Id; name: string }>;
  active: Id;
  onSelect: (id: Id) => void;
}

export function Segmented<Id extends string>({
  testid,
  name,
  options,
  active,
  onSelect,
}: SegmentedProps<Id>): React.JSX.Element {
  return (
    <div style={bar} data-testid={testid} role="group">
      {options.map((option) => {
        const on = option.id === active;
        return (
          <button
            key={option.id}
            type="button"
            {...{ [`data-${name}`]: option.id }}
            aria-pressed={on}
            onClick={() => onSelect(option.id)}
            style={{
              ...base,
              color: on ? "var(--text)" : "var(--text-2)",
              background: on ? "var(--pane-3)" : "transparent",
            }}
          >
            {option.name}
          </button>
        );
      })}
    </div>
  );
}

export default Segmented;
