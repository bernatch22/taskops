/* STUB — the real panel lands in tk-db88c4.
 *
 * This file already draws Nova's pane chrome, its verbatim title and subtitle,
 * and it already typechecks against `LiveLeasesProps`. Replacing it is the whole
 * of tk-db88c4: keep the signature, fill the body. Do not edit Monitor.tsx or
 * Pane.tsx to do it — Monitor already passes exactly these props.
 *
 * The design is Taskops Nova.dc.html lines 176-216: a four-column grid row
 * (`minmax(150px,1.6fr) minmax(70px,1fr) 72px 78px`, gap 12, padding 14px 20px),
 * a dot with a 3px ring, the `card → actor` mono line, an SVG sparkline, the
 * remaining TTL right-aligned, and a state pill. `LeaseProc.load` is `null` and
 * says why (panels.ts, note 3) — the sparkline has no series behind it. */
import { Pane, PaneEmpty } from "./Pane";
import type { LiveLeasesProps } from "./panels";

export function LiveLeases(_: LiveLeasesProps): React.JSX.Element {
  return (
    <Pane
      testId="pane-leases"
      title="Live leases"
      subtitle="15-minute TTL, renewed on every call. A dead process is a lapsing lease."
    >
      <PaneEmpty>panel lands in tk-db88c4</PaneEmpty>
    </Pane>
  );
}
