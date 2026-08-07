/* STUB — the real panel lands in tk-f38042 (with DependencyChain.tsx).
 *
 * Design: Taskops Nova.dc.html lines 321-337. Header padding `18px 20px 10px`,
 * body `4px 10px 12px`. Each path is a `PaneTile` (NOT a button — the design
 * draws a `<div>`, so there is no `onOpen` on `EditSurfaceProps`): the mono path,
 * the detail line under it, and a claims pill right-aligned. A contended path
 * tints its background; the pane's own subtitle is the reason it never locks. */
import { Pane, PaneEmpty } from "./Pane";
import type { EditSurfaceProps } from "./panels";

export function EditSurface(_: EditSurfaceProps): React.JSX.Element {
  return (
    <Pane
      testId="pane-files"
      title="Edit surface"
      subtitle="A warning, never a lock."
      headPad="18px 20px 10px"
    >
      <PaneEmpty>panel lands in tk-f38042</PaneEmpty>
    </Pane>
  );
}
