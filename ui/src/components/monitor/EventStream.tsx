/* STUB — the real panel lands in tk-4b37dd.
 *
 * Design: Taskops Nova.dc.html lines 385-412. Header `18px 20px 14px` with a mono
 * counter as its aside. Body `4px 20px 20px`, `max-height: 620px; overflow-y:
 * auto`. Each entry is a `54px 1fr` grid, gap 14, padding 14px 0: the timestamp
 * and relative age right-aligned in the first column; in the second, a
 * `--hair` left rule with an 8px dot punched onto it (`box-shadow: 0 0 0 3px
 * var(--pane)` is what makes the dot sit ON the line), a kind pill, the actor,
 * the card id, and the body text.
 *
 * BUILT TO SHAPE, WITH NO VERB BEHIND IT. Nothing streams the log to this client:
 * `RpcVerb` is `board | card | report | mentions | update` and `BoardPayload`
 * carries no events, so `events` is `[]` and `total` is `null` (panels.ts, note
 * 1). That is the card: draw the pane exactly as designed and let its empty state
 * name the missing verb. The milestone rule is explicit that this pane is not
 * dropped for lack of data — dropping panes is what wrecked the last chapter. */
import { Pane, PaneEmpty } from "./Pane";
import type { EventStreamProps } from "./panels";

export function EventStream(_: EventStreamProps): React.JSX.Element {
  return (
    <Pane
      testId="pane-events"
      title="Event stream"
      subtitle="Complete, ordered, never truncated."
    >
      <PaneEmpty>panel lands in tk-4b37dd</PaneEmpty>
    </Pane>
  );
}
