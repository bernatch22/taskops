/* columns | flow — the Board page's own segmented control.
 *
 * `chrome/TabNav.tsx`'s pill bar, shrunk: same geometry vocabulary (a pane
 * strip, a hairline, the active pill on `--pane-3`), smaller, because this
 * chooses a way of READING one view and the tab bar chooses the view. Making it
 * a sixth tab was the alternative and it is wrong: the flow is the Board, drawn
 * differently, and a tab would put it beside Monitor and Actors as if it were
 * another page with another payload.
 *
 * The geometry itself now lives in `shared/Segmented.tsx`, because the Actors
 * page needed the same gesture for its hours window. This file kept what is
 * ITS decision — the two views, their names, and the `data-view` hook — and
 * nothing was restyled: same testid, same attributes, same pills.
 *
 * It is not a router either — the choice is state on the page (`Board.tsx`),
 * remembered in `localStorage` and nowhere else. */

import { Segmented } from "../shared/Segmented";

export type BoardView = "columns" | "flow";

export const VIEWS: ReadonlyArray<{ id: BoardView; name: string }> = [
  { id: "columns", name: "Columns" },
  { id: "flow", name: "Flow" },
];

export interface ViewToggleProps {
  active: BoardView;
  onSelect: (view: BoardView) => void;
}

export function ViewToggle({ active, onSelect }: ViewToggleProps): React.JSX.Element {
  return (
    <Segmented
      testid="board-view-toggle"
      name="view"
      options={VIEWS}
      active={active}
      onSelect={onSelect}
    />
  );
}
