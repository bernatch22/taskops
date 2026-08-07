/* The card's whole history, oldest first — Nova's Thread block.
 *
 * The WHOLE of it, never a tail: `_context.py::dossier` sends `history` with the
 * comment "complete, in order, never cut", and a viewer that showed the last ten
 * would be the summary that docstring refuses. The drawer's body scrolls; the
 * thread does not get to decide what a reader needs.
 *
 * Two kinds of line, drawn the same way on purpose. A `comment` carries prose and
 * gets the markdown renderer; everything else — created, claimed, edited, commit,
 * status, released, submitted, reviewed, merged — is a fact with at most a phrase
 * attached. Splitting them into two lists would break the one thing a thread is
 * for: what happened, in the order it happened. */
import { ago, shortActor } from "../../format";
import { TONE_FG, type Tone } from "../board/CardTile";
import { Markdown, Mentioned } from "../shared/Markdown";
import type { Event } from "../../types";

/** What a kind means, as a colour. Anything unlisted is neutral rather than
 *  invisible: an event kind this bundle predates still draws a dot. */
export const DOT: Record<string, Tone> = {
  comment: "accent",
  commit: "ok",
  status: "ok",
  merged: "ok",
  claimed: "accent",
  released: "warn",
  submitted: "warn",
  reviewed: "warn",
};

/** The one-phrase summary of a non-comment event, from its body. Mirrors the
 *  vanilla page's `detail()` — the same keys, in the same order — because the two
 *  read the same log and disagreeing about it would be a third vocabulary. */
export function detail(event: Event): string {
  const body = event.body;
  if (event.kind === "created") {
    const card = body["card"];
    const title = card && typeof card === "object" ? (card as { title?: string }).title : "";
    return title ?? "";
  }
  if (event.kind === "edited") return `${String(body["field"] ?? "")} → ${JSON.stringify(body["to"])}`;
  for (const key of ["text", "note", "to", "subject", "into", "verdict"]) {
    const value = body[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function addressed(event: Event): string[] {
  const to = event.body["mentions"];
  return Array.isArray(to) ? to.filter((who): who is string => typeof who === "string") : [];
}

export function Thread({ history, now }: { history: Event[]; now: number }): React.JSX.Element {
  return (
    <div data-testid="thread" style={{ display: "flex", flexDirection: "column" }}>
      {history.map((event) => {
        const tone = DOT[event.kind] ?? "neutral";
        const text = detail(event);
        const to = addressed(event);
        return (
          <div
            key={event.id}
            data-testid="event"
            data-kind={event.kind}
            style={{ display: "grid", gridTemplateColumns: "52px 1fr", gap: "16px", paddingBottom: "18px" }}
          >
            <span
              className="mono"
              style={{ fontSize: "11.5px", color: "var(--faint)", textAlign: "right", paddingTop: "2px" }}
            >
              {ago(now - event.ts)}
            </span>
            <div style={{ borderLeft: "1px solid var(--hair)", paddingLeft: "18px", position: "relative" }}>
              <span
                style={{
                  position: "absolute",
                  left: "-4.5px",
                  top: "5px",
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: TONE_FG[tone],
                  boxShadow: "0 0 0 3px var(--pane)",
                }}
              />
              <div style={{ fontSize: "12.5px", color: "var(--text-3)" }}>
                <span style={{ color: "var(--text-2)" }} title={event.actor}>
                  {shortActor(event.actor)}
                </span>{" "}
                {event.kind}
                {to.length > 0 ? (
                  <span className="mono" style={{ color: "var(--accent)" }}>
                    {" → "}
                    {to.map(shortActor).join(", ")}
                  </span>
                ) : null}
              </div>
              {event.kind === "comment" && text ? (
                <div style={{ marginTop: "6px" }}>
                  <Markdown text={text} />
                </div>
              ) : text ? (
                <div style={{ marginTop: "6px", fontSize: "14px", color: "var(--text-2)", lineHeight: 1.55 }}>
                  <Mentioned text={text} />
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
