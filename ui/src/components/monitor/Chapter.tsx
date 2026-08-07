/* STUB — the real panel lands in tk-60334f (with Mentions.tsx).
 *
 * Design: Taskops Nova.dc.html lines 344-362. This is the ONE pane with no `h2`
 * header block: it opens with a `20px 20px 16px` body carrying an 11.5px
 * `--text-3` eyebrow ("Chapter in focus"), then the milestone title at 21px /
 * weight 500 / letter-spacing -0.035em, then the goal at 13.5px line-height
 * 1.55. Below it the rules, each a `PaneTile` on `--pane-2` with its mono index.
 * It closes on a `PaneRow` footer: "Integration branch" against the branch in
 * `--accent`.
 *
 * So `Pane` is used WITHOUT `title` here — that is why the prop is optional. */
import { Pane, PaneEmpty } from "./Pane";
import type { ChapterProps } from "./panels";

export function Chapter(_: ChapterProps): React.JSX.Element {
  return (
    <Pane testId="pane-chapter">
      <div style={{ padding: "20px 20px 16px" }}>
        <div style={{ fontSize: "11.5px", color: "var(--text-3)", marginBottom: "7px" }}>
          Chapter in focus
        </div>
      </div>
      <PaneEmpty>panel lands in tk-60334f</PaneEmpty>
    </Pane>
  );
}
