/* STUB — the real panel lands in tk-c22565 (with Throughput.tsx).
 *
 * Design: Taskops Nova.dc.html lines 265-295. Header padding `18px 20px 4px`.
 * Body `14px 20px 20px`, flex, gap 20: a 104px donut drawn as four concentric
 * `<circle r="41" stroke-width="9">` arcs with `stroke-dasharray`/`dashoffset`
 * and `transform="rotate(-90 50 50)"`, the tracked count absolutely centred over
 * it, and a legend of `HealthSlice` rows (`9px 1fr auto`, gap 11). */
import { Pane, PaneEmpty } from "./Pane";
import type { LeaseHealthProps } from "./panels";

export function LeaseHealth(_: LeaseHealthProps): React.JSX.Element {
  return (
    <Pane
      testId="pane-health"
      title="Lease health"
      subtitle="Silence is data, not an error."
      headPad="18px 20px 4px"
    >
      <PaneEmpty>panel lands in tk-c22565</PaneEmpty>
    </Pane>
  );
}
