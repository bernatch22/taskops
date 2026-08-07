/* STUB — the real panel lands in tk-f38042 (with EditSurface.tsx).
 *
 * Design: Taskops Nova.dc.html lines 301-319. Header padding `18px 20px 10px`,
 * body `4px 10px 12px`. Each node is a `PaneTileButton` (radius 10, hover
 * `--pane-2`, padding 9px 10px) laid out `minmax(0,1fr) auto`: an indent spacer
 * of `DagNode.depth`, a 7px dot, the title, the mono id, and the trailing note
 * right-aligned. */
import { Pane, PaneEmpty } from "./Pane";
import type { DependencyChainProps } from "./panels";

export function DependencyChain(_: DependencyChainProps): React.JSX.Element {
  return (
    <Pane
      testId="pane-dag"
      title="Dependency chain"
      subtitle="The block clears when the row above closes."
      headPad="18px 20px 10px"
    >
      <PaneEmpty>panel lands in tk-f38042</PaneEmpty>
    </Pane>
  );
}
