/* STUB — the real panel lands in tk-60334f (with Chapter.tsx).
 *
 * Design: Taskops Nova.dc.html lines 364-383. The header aligns `center` (its
 * aside is a `--danger-soft` pill counting the unanswered), and each mention is
 * a `PaneButton` at `15px 20px`: a 24px initials disc, the mono author, the age
 * pushed right, the comment text at 13.5px, then the card id in `--accent` beside
 * the card's title.
 *
 * Reuse `initials()` and `ago()` from `../../format` — both already exist, and
 * `docs/fan-out.md` is the post-mortem of the fan-out that wrote them twice. */
import { Pane, PaneEmpty } from "./Pane";
import type { MentionsProps } from "./panels";

export function Mentions(_: MentionsProps): React.JSX.Element {
  return (
    <Pane testId="pane-mentions" title="Addressed to you" headAlign="center">
      <PaneEmpty>panel lands in tk-60334f</PaneEmpty>
    </Pane>
  );
}
