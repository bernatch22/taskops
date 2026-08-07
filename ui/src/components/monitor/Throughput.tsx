/* STUB — the real panel lands in tk-c22565 (with LeaseHealth.tsx).
 *
 * Design: Taskops Nova.dc.html lines 221-263. Header padding is `18px 20px 6px`
 * — narrower than the default, because the legend sits tight above the chart —
 * and the legend is the `aside`. Body: an SVG `viewBox="0 0 380 130"` with two
 * rounded rects per day (commits in `--hair-2` behind, closes in `--accent`) and
 * a `--warn` review polyline over them; then a `repeat(14, 1fr)` strip of day
 * labels; then a three-cell totals row on a hairline (`PaneRow`).
 *
 * `ThroughDay.reviews` is `null` and the review line has no source (panels.ts,
 * note 2). Draw the pane whole and say so on its face — do not drop the legend
 * entry and do not substitute a number. */
import { Pane, PaneEmpty } from "./Pane";
import type { ThroughputProps } from "./panels";

export function Throughput(_: ThroughputProps): React.JSX.Element {
  return (
    <Pane testId="pane-throughput" title="Throughput" subtitle="Last 14 days" headPad="18px 20px 6px">
      <PaneEmpty>panel lands in tk-c22565</PaneEmpty>
    </Pane>
  );
}
