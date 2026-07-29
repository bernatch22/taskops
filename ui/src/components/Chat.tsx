/* A conversation with the open session, over whatever you are looking at.
 *
 * NOT a fourth view, and that is the whole design. A view is a place you GO, and this is a thing
 * you say WHILE reading something else — usually about the card on screen. Making it a
 * destination would mean losing your place to ask a question about it.
 *
 * So it is mounted always and hidden with a class, never conditionally rendered: an unmount would
 * throw away the scroll position every time somebody switched tab, which is the one thing the
 * card asked it to keep. It costs one DOM subtree that is `visibility: hidden` most of the time.
 *
 * It borrows `.panel`, `.thread` and `.compose` verbatim from the task drawer. The reply box was
 * the sibling Berna was shown before asking for this, so it should read as the same box in a
 * different place — and a second set of borders and radii for the same idea is how a UI stops
 * looking like one program. */

import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Event } from "../contracts";
import { Actor, ago } from "./bits";

export function Chat({ open, card, readonly, last, onClose }: {
  open: boolean;
  /* The card the board has open, or "". Sent as context so the session knows what "this" means. */
  card: string;
  readonly: boolean;
  /* The newest event off the shared socket. A chat line is not a projection anybody derives, so
   * it is appended from the frame rather than refetched — the board's rule does not apply. */
  last: Event | null;
  onClose: () => void;
}): JSX.Element {
  const [thread, setThread] = useState<Event[]>([]);
  const [text, setText] = useState("");
  const [failed, setFailed] = useState("");
  const foot = useRef<HTMLDivElement>(null);

  useEffect(() => { api.chat().then(setThread).catch(() => {}); }, []);

  useEffect(() => {
    if (!last || last.kind !== "chat") return;
    setThread((was) => (was.some((e) => e.id === last.id) ? was : [...was, last]));
  }, [last]);

  /* Newest at the bottom, so the bottom is where the eye goes. `smooth` is left to the browser,
   * which already honours a reduced-motion preference for it. */
  useEffect(() => {
    if (open) foot.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [open, thread.length]);

  async function send() {
    setFailed("");
    try {
      await api.say(text, card);
      setText("");
    } catch (failure) {
      setFailed(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <aside className={`side${open ? " on" : ""}`} aria-hidden={!open}
           aria-label="chat with the session">
      <header className="panel-head">
        <strong>Session</strong>
        <button className="close" onClick={onClose} aria-label="close">✕</button>
      </header>

      <ol className="thread">
        {thread.map((event) => (
          /* Both sides of this conversation resolve to the same developer id — the person types
           * here, the session answers through the channel, and both come through one door on one
           * machine. Without the source the answer arrived looking exactly like the question,
           * which reads as nothing having happened. */
          <li key={event.id}
              className={String(event.body["source"] ?? "") === "session" ? "said" : ""}>
            <div className="msg-head">
              {String(event.body["source"] ?? "") === "session"
                ? <span className="tag">session</span>
                : <Actor id={event.actor} />}
              {String(event.body["card"] ?? "")
                ? <span className="tag">{String(event.body["card"])}</span> : null}
              <span className="dim">{ago(event.ts)}</span>
            </div>
            <p className="msg">{String(event.body["text"] ?? "")}</p>
          </li>
        ))}
        {thread.length === 0 ? <p className="dim">Nothing said yet.</p> : null}
      </ol>
      <div ref={foot} />

      {readonly ? <p className="dim">Read-only — start it without <code>--readonly</code> to talk.</p> : (
        <section className="compose">
          {/* The one line that says what will happen, and only when it is true. */}
          {card ? <p className="dim">Carries <code>{card}</code> as context.</p> : null}
          <textarea value={text} rows={3} placeholder="Say it while you are looking at it. ⌘/Ctrl+Enter sends."
                    onChange={(change) => setText(change.target.value)}
                    onKeyDown={(keys) => {
                      if (keys.key === "Enter" && (keys.metaKey || keys.ctrlKey)) void send();
                    }} />
          <div className="actions">
            <button className="primary" disabled={!text.trim()} onClick={() => void send()}>Send</button>
          </div>
          {failed ? <p className="failed">{failed}</p> : null}
        </section>
      )}
    </aside>
  );
}

/* The shortcut, as a hook so the component above stays about the conversation.
 *
 * ⌘/Ctrl+K, and the modifier is the point: nothing in this UI binds a bare key (the only handler
 * anywhere is Enter on a focused card), but a bare letter would fire mid-word in the reply box or
 * the search field — the two places a person types most. A modified chord cannot, so the handler
 * needs no "am I in an input" guard, which is the check everybody forgets to update later.
 * Escape closes, and only closes: a toggle on Escape would reopen the sidebar for somebody
 * dismissing the task drawer behind it. */
export function useChatKeys(toggle: () => void, close: () => void): void {
  useEffect(() => {
    const onKey = (keys: KeyboardEvent) => {
      if (keys.key.toLowerCase() === "k" && (keys.metaKey || keys.ctrlKey)) {
        keys.preventDefault();
        toggle();
      } else if (keys.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, close]);
}
