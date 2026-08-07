/* The ONE write this dashboard has: say something on a card, optionally addressed.
 *
 * It goes through the same door every agent uses — `update` with `comment=` and
 * `mentions=` riding on it, the same token, the same server-side validation — so
 * a refusal comes back in the server's own words and this file re-implements
 * nothing. There is no status control here and there never will be: a second way
 * to move a card is a second way for the board and the browser to disagree
 * (milestone rule 1).
 *
 * THE DRAFT SURVIVES A REFUSAL. `setDraft("")` runs only after the promise
 * resolves, and the failure path touches nothing but the error line. A person who
 * typed a paragraph to a working agent and lost it to a 409 does not type the
 * second one — that is the entire reason the clear is not in a `finally`.
 *
 * The picker offers `board.team`, which is PRESENCE: an actor nobody has seen in
 * a day is not somebody you reach by writing to them. The addresses travel as the
 * `mentions` argument, not as text spliced into the comment — the server
 * validates each one against the actor grammar and refuses a typo at the write,
 * and a mention parsed back out of prose could never be validated at all. */
import { useState } from "react";

import { RpcError } from "../../client";
import { shortActor } from "../../format";
import type { TeamMember } from "../../types";

/** `useBoard.comment` — resolves on ok, rejects with the board's own refusal. */
export type Send = (text: string, mentions: string[]) => Promise<void>;

export interface CommentBoxProps {
  team: TeamMember[];
  onSend: Send;
}

/** What the box looks like after a send attempt. The whole rule, in one pure
 *  function, and the reason it is not written inline: **on a refusal the draft
 *  comes back unchanged**, and that is a claim a test can run without a browser.
 *  Somebody who typed a paragraph to a working agent and lost it to a refusal
 *  does not type the second one; a clear in a `finally` would be exactly that
 *  bug, and it would look correct in review. */
export interface Draft {
  draft: string;
  picked: readonly string[];
  failed: string;
}

export async function submit(draft: string, picked: readonly string[], send: Send): Promise<Draft> {
  const text = draft.trim();
  if (!text) return { draft, picked, failed: "" };
  try {
    await send(text, [...picked]);
    // Accepted. The feed's change frame brings it back into the thread on the
    // next refetch, so there is nothing else to do here.
    return { draft: "", picked: [], failed: "" };
  } catch (err) {
    // The server's words, verbatim: a Refused message NAMES the call that fixes
    // it, and paraphrasing would throw away the only instruction there is.
    return { draft, picked, failed: err instanceof RpcError ? err.message : String(err) };
  }
}

const chip: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: "11px",
  padding: "3px 10px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
};

export function CommentBox({ team, onSend }: CommentBoxProps): React.JSX.Element {
  const [draft, setDraft] = useState("");
  const [picked, setPicked] = useState<readonly string[]>([]);
  const [failed, setFailed] = useState<string>("");
  const [sending, setSending] = useState(false);

  function toggle(actor: string): void {
    setPicked((now) => (now.includes(actor) ? now.filter((a) => a !== actor) : [...now, actor]));
  }

  async function send(): Promise<void> {
    if (!draft.trim() || sending) return;
    setSending(true);
    setFailed("");
    const next = await submit(draft, picked, onSend);
    setDraft(next.draft);
    setPicked(next.picked);
    setFailed(next.failed);
    setSending(false);
  }

  return (
    <div
      data-testid="comment-box"
      style={{ padding: "16px 28px 20px", borderTop: "1px solid var(--hair)", background: "var(--pane-2)" }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginBottom: "10px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "12px", color: "var(--text-3)" }}>Reply</span>
        {team.map((member) => {
          const on = picked.includes(member.actor);
          return (
            <button
              key={member.actor}
              type="button"
              data-testid="mention-pick"
              data-actor={member.actor}
              aria-pressed={on}
              title={`${member.actor} · seen ${member.ago}s ago`}
              onClick={() => toggle(member.actor)}
              className="mono"
              style={{
                ...chip,
                color: on ? "var(--accent-hi)" : "var(--text-3)",
                background: on ? "var(--accent-soft)" : "var(--pane-3)",
              }}
            >
              @{shortActor(member.actor)}
            </button>
          );
        })}
        <span style={{ fontSize: "11.5px", color: "var(--text-3)", marginLeft: "auto" }}>
          delivered on the agent&apos;s next action
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "10px", alignItems: "end" }}>
        <textarea
          data-testid="comment"
          rows={2}
          value={draft}
          placeholder="a comment — the @buttons above address it"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter alone is a newline: this is a paragraph to a colleague, not a
            // chat line. ⌘/Ctrl+Enter sends, as every editor of prose does.
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send();
          }}
          style={{
            fontFamily: "inherit",
            fontSize: "14px",
            lineHeight: 1.55,
            resize: "vertical",
            background: "var(--pane)",
            border: "1px solid var(--hair-2)",
            borderRadius: "11px",
            padding: "12px 15px",
            color: "var(--text)",
            outline: "none",
          }}
        />
        <button
          type="button"
          data-testid="send"
          disabled={sending || !draft.trim()}
          onClick={() => void send()}
          style={{
            fontFamily: "inherit",
            fontSize: "13.5px",
            fontWeight: 500,
            background: "var(--accent)",
            border: "1px solid var(--accent)",
            color: "#fff",
            padding: "12px 24px",
            borderRadius: "11px",
            cursor: sending || !draft.trim() ? "default" : "pointer",
            opacity: sending || !draft.trim() ? 0.5 : 1,
          }}
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>

      {failed ? (
        <div
          data-testid="comment-error"
          style={{ marginTop: "10px", fontSize: "12.5px", color: "var(--danger)", lineHeight: 1.5 }}
        >
          {failed}
        </div>
      ) : null}
    </div>
  );
}
