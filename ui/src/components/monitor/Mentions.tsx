/* Addressed to you — Taskops Nova.dc.html lines 364-383.
 *
 * The header aligns `center` (its aside is a `--danger-soft` pill counting the
 * unanswered), and each mention is a `PaneButton` at `15px 20px`: a 24px initials
 * disc, the mono author, the age pushed right, the comment text at 13.5px, then
 * the card id in `--accent` beside the card's title.
 *
 * There is NO dismiss and NO mark-as-read here, and there must never be one: a
 * mention clears by being ANSWERED on its card (ARCHITECTURE.md §11
 * bans the ack verb outright). Clicking a row opens the Dossier, where the one
 * comment box in the UI lives — that is the entire interaction.
 *
 * `initials()`, `shortActor()` and `ago()` come from ../../format —
 * a past fan-out wrote them twice, which is why they live in one place. */
import { ago, initials, shortActor } from "../../format";
import { Pane, PaneButton, PaneEmpty } from "./Pane";
import { Markdown } from "../shared/Markdown";
import type { MentionCard, MentionsProps } from "./panels";

export function Mentions({ mentions, now, onOpen }: MentionsProps): React.JSX.Element {
  const rows: MentionCard[] = mentions.map((m) => ({
    card: m.id,
    by: shortActor(m.by),
    ago: ago(now - m.ts),
    text: m.text,
    title: m.title,
  }));
  return (
    <Pane
      testId="pane-mentions"
      title="Addressed to you"
      headAlign="center"
      aside={
        rows.length > 0 ? (
          <span
            style={{
              fontSize: "10.5px",
              padding: "3px 10px",
              borderRadius: "20px",
              background: "var(--danger-soft)",
              color: "var(--danger)",
            }}
          >
            {rows.length} unanswered
          </span>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <PaneEmpty>
          Nobody is waiting on you. A mention clears by being answered on its card — there is
          nothing to mark as read.
        </PaneEmpty>
      ) : (
        rows.map((m, i) => (
          <PaneButton
            key={`${m.card}-${i}`}
            testId="mention-row"
            cardId={m.card}
            onOpen={onOpen}
            pad="15px 20px"
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                marginBottom: "9px",
              }}
            >
              <div
                style={{
                  width: "24px",
                  height: "24px",
                  borderRadius: "50%",
                  background: "var(--pane-3)",
                  color: "var(--text)",
                  fontSize: "10px",
                  fontWeight: 500,
                  display: "grid",
                  placeItems: "center",
                  textTransform: "uppercase",
                }}
              >
                {initials(m.by)}
              </div>
              <span className="mono" style={{ fontSize: "11.5px", color: "var(--text-2)" }}>
                {m.by}
              </span>
              <span
                style={{ fontSize: "11px", color: "var(--text-3)", marginLeft: "auto" }}
              >
                {m.ago}
              </span>
            </div>
            <div
              style={{
                fontSize: "13.5px",
                color: "var(--text)",
                lineHeight: 1.55,
                marginBottom: "9px",
              }}
            >
              {/* The comment that named you, verbatim — the same string the
                  thread draws through the same renderer. INLINE: this is one
                  row of a dense pane, sitting between an author line and a card
                  line, and the block renderer's own column layout would fight
                  the button's. The mention that put the row here is highlighted
                  by `Spans` on the way through, which the raw draw never did. */}
              <Markdown text={m.text} inline />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="mono" style={{ fontSize: "10.5px", color: "var(--accent)" }}>
                {m.card}
              </span>
              <span style={{ fontSize: "11px", color: "var(--text-3)" }}>{m.title}</span>
            </div>
          </PaneButton>
        ))
      )}
    </Pane>
  );
}
