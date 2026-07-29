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
 * looking like one program.
 *
 * Three things happen here that do not happen in the drawer's thread, and each earns its keep:
 * a session reply is MARKDOWN and it is REVEALED as it arrives, the sidebar says the session is
 * THINKING while nothing has come back, and the agent's tool calls run underneath as a strip.
 * The strip is observability and not conversation — see `Tools`. */

import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Event } from "../contracts";
import { Actor, ago } from "./bits";
import { Markdown } from "./Markdown";

/* How long the reveal takes, whatever the length of the answer.
 *
 * A duration and NOT a per-frame character budget, which is what the reference implementation
 * uses: there the text arrives token by token and the animation only ever has to catch up with a
 * few characters, while HERE the whole reply lands in one event. A budget of two characters a
 * frame would take sixteen seconds on a two-thousand-character answer — the reveal would stop
 * being a flourish and start being a wait. Time-based also makes it frame-rate independent. */
const REVEAL_MS = 1400;

/* How long "thinking…" is allowed to claim it knows something.
 *
 * There is no ack on this path: the sidebar posts a chat event and the session picks it up over
 * the channel, so an unanswered message is indistinguishable from a session that was never
 * running. Ninety seconds is past any answer worth waiting on in silence; after that the row says
 * so instead of spinning, because an indicator that lies forever teaches people to ignore the one
 * time it is telling the truth. */
const PATIENCE_MS = 90_000;

/* The strip keeps the last N calls. Fifty is roughly a screen of scrollback and a bound on the
 * DOM: a long agent run emits a line per tool call, and an unbounded list would grow all day. */
const TOOLS_CAP = 50;

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
  const [tools, setTools] = useState<Event[]>([]);
  const [dropped, setDropped] = useState(false);
  const [text, setText] = useState("");
  const [failed, setFailed] = useState("");
  /* When the last board-sourced line was sent, or 0 for "not waiting on anything". */
  const [waiting, setWaiting] = useState(0);
  const [patience, setPatience] = useState(false);
  const [strip, setStrip] = useState(true);
  const foot = useRef<HTMLDivElement>(null);
  const stripFoot = useRef<HTMLOListElement>(null);

  /* Which lines came in on the socket while this was mounted. A message REVEALS only if its id is
   * in here: history renders whole and instantly, because replaying the animation for the entire
   * conversation every time somebody hits ⌘K would read as a sidebar that had lost its place. */
  const arrived = useRef<Set<string>>(new Set());

  useEffect(() => { api.chat().then(setThread).catch(() => {}); }, []);

  useEffect(() => {
    if (!last) return;
    if (last.kind === "chat") {
      arrived.current.add(last.id);
      setThread((was) => (was.some((e) => e.id === last.id) ? was : [...was, last]));
      /* A reply ends the wait. A line the person themselves just sent arrives here too and would
       * clear it a millisecond after `send` set it, so only the session's side counts. */
      if (String(last.body["source"] ?? "") === "session") setWaiting(0);
      return;
    }
    if (last.kind === "activity") {
      /* The agent is working. That is a better answer than "thinking…", so the spinner stands
       * down — but the strip is NOT a reply, and nothing here touches the unread dot (which
       * `main.tsx` raises on `chat` alone) or the thread. */
      setWaiting(0);
      setTools((was) => {
        if (was.some((e) => e.id === last.id)) return was;
        const next = [...was, last];
        if (next.length <= TOOLS_CAP) return next;
        setDropped(true);
        return next.slice(next.length - TOOLS_CAP);
      });
    }
  }, [last]);

  /* The cap on the thinking row, armed fresh on every send. */
  useEffect(() => {
    if (!waiting) {
      setPatience(false);
      return;
    }
    setPatience(false);
    const timer = window.setTimeout(() => setPatience(true), PATIENCE_MS);
    return () => window.clearTimeout(timer);
  }, [waiting]);

  /* Newest at the bottom, so the bottom is where the eye goes. `smooth` is left to the browser,
   * which already honours a reduced-motion preference for it. */
  useEffect(() => {
    if (open) foot.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [open, thread.length, waiting]);

  /* The strip scrolls ITSELF, not the sidebar: a tool call must not drag the conversation out of
   * view while somebody is reading it. */
  useEffect(() => {
    if (stripFoot.current) stripFoot.current.scrollTop = stripFoot.current.scrollHeight;
  }, [tools.length, strip]);

  async function send() {
    setFailed("");
    try {
      await api.say(text, card);
      setText("");
      setWaiting(Date.now());
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
        {thread.map((event) => {
          /* Both sides of this conversation resolve to the same developer id — the person types
           * here, the session answers through the channel, and both come through one door on one
           * machine. Without the source the answer arrived looking exactly like the question,
           * which reads as nothing having happened. */
          const said = String(event.body["source"] ?? "") === "session";
          const body = String(event.body["text"] ?? "");
          return (
            <li key={event.id} className={said ? "said" : ""}>
              <div className="msg-head">
                {said ? <span className="tag">session</span> : <Actor id={event.actor} />}
                {String(event.body["card"] ?? "")
                  ? <span className="tag">{String(event.body["card"])}</span> : null}
                <span className="dim">{ago(event.ts)}</span>
              </div>
              {said
                /* Markdown for the session's side only. What a person typed is shown exactly as
                 * they typed it: nobody writing `*` in a sentence meant to emphasise anything. */
                ? <div className="msg"><Revealed source={sanitize(body)}
                                                 live={arrived.current.has(event.id)} /></div>
                : <p className="msg">{body}</p>}
            </li>
          );
        })}
        {thread.length === 0 ? <p className="dim">Nothing said yet.</p> : null}
        {waiting ? (
          <li className="think" aria-live="polite">
            {patience
              ? <span className="dim">still working — or the session is closed</span>
              : <><span className="dim">thinking</span><Dots /></>}
          </li>
        ) : null}
      </ol>
      <div ref={foot} />

      {tools.length ? (
        <Tools calls={tools} dropped={dropped} shown={strip} onToggle={() => setStrip((was) => !was)}
               listRef={stripFoot} />
      ) : null}

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

/* ── the reveal ─────────────────────────────────────────────────────────────── */

/**
 * A reply drawn character by character, then left alone.
 *
 * The markdown of the revealed PREFIX is re-rendered every frame rather than the finished text
 * being unmasked, so a heading is a heading the moment its `#` lands and the answer never
 * reflows at the end. That costs a parse per frame — fine at the size of a chat reply, and the
 * reason this is not the component that renders a report.
 *
 * `live` false renders the whole thing on the first paint: history is not an event, and animating
 * it would be the sidebar pretending something just happened.
 */
function Revealed({ source, live }: { source: string; live: boolean }): JSX.Element {
  /* Read at mount, not at module load: a person can change the preference without reloading, and
   * whether to animate is only ever asked when there is something to animate. */
  const whole = !live || calm();
  const [shown, setShown] = useState(whole ? source.length : 0);

  useEffect(() => {
    if (whole) {
      setShown(source.length);
      return;
    }
    let frame = 0;
    const started = performance.now();
    const tick = (at: number) => {
      const done = Math.min(1, (at - started) / REVEAL_MS);
      setShown(Math.ceil(done * source.length));
      /* No further frame once it has caught up — the loop ends itself rather than spinning for
       * the life of the sidebar. Cancelled on unmount either way. */
      if (done < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [source, whole]);

  return <Markdown source={source.slice(0, shown)} />;
}

/** Does this person want motion? Asked of the browser, never remembered. */
function calm(): boolean {
  return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function Dots(): JSX.Element {
  return <span className="dots" aria-hidden="true"><i /><i /><i /></span>;
}

/* ── the tool strip ─────────────────────────────────────────────────────────── */

/**
 * What the agent is doing, underneath what it is saying.
 *
 * OBSERVABILITY, not conversation, and every decision here follows from that. It is dimmer than a
 * message and collapsible, because it is glanceable rather than readable. Its arrival raises no
 * unread dot and appends nothing to the thread — a board that pinged somebody for each of an
 * agent's four hundred tool calls would have taught them to close the sidebar by lunchtime.
 *
 * The events are `activity`, which the hooks write on every PostToolUse (`usecases.track`), with
 * a body summary of "the tool, and the file or command it touched".
 */
function Tools({ calls, dropped, shown, onToggle, listRef }: {
  calls: Event[];
  dropped: boolean;
  shown: boolean;
  onToggle: () => void;
  listRef: React.RefObject<HTMLOListElement>;
}): JSX.Element {
  return (
    <section className="tools">
      <button className="tools-head linkish" onClick={onToggle} aria-expanded={shown}>
        {shown ? "▾" : "▸"} agent activity <span className="dim">({calls.length})</span>
      </button>
      {shown ? (
        <ol className="tool-list" ref={listRef}>
          {/* The truncation is stated rather than silent: a strip that quietly forgot its first
            * hundred lines would have somebody scrolling up looking for them. */}
          {dropped ? <li className="tool-more dim">· · ·</li> : null}
          {calls.map((call) => {
            const summary = String(call.body["summary"] ?? "");
            const gap = summary.indexOf(" ");
            const tool = gap < 0 ? summary : summary.slice(0, gap);
            const target = gap < 0 ? "" : summary.slice(gap + 1);
            return (
              <li key={call.id} className="tool-line">
                <span className="tool-chip">{tool}</span>
                {/* Middle-out, because both ends carry the meaning: the head says which package
                  * and the tail says which file, and a cut at either end loses one of them. */}
                <span className="tool-target" title={target}>{middle(target)}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}

function middle(text: string, max = 46): string {
  if (text.length <= max) return text;
  const head = Math.ceil((max - 1) / 2);
  return `${text.slice(0, head)}…${text.slice(text.length - (max - 1 - head))}`;
}

/* ── the leaked markup ──────────────────────────────────────────────────────── */

/**
 * Tool-call markup that corrupted mid-response and was stored as prose.
 *
 * A known Claude Code defect:
 *   https://github.com/anthropics/claude-code/issues/66011
 *   https://github.com/anthropics/claude-code/issues/68615
 * The channel strips this at the door (`plugin/channel/events.ts`, where it is tested), so this
 * copy is for the events ALREADY on disk — the board never rewrites what it stored, and a reply
 * Berna received before the fix is still in the log. Duplicated rather than shared because the
 * channel is a separate bun package that this bundle does not build.
 *
 * Only the TAIL is cut. Somebody quoting XML mid-sentence is writing, not leaking.
 */
const LEAKED_TAIL =
  /(?:\s*<\/?(?:antml:)?(?:invoke|parameter|function_calls|function_results)(?:\s[^<>]*)?\/?>)+\s*$/;

function sanitize(text: string): string {
  const cut = text.replace(LEAKED_TAIL, "");
  /* An answer that is nothing BUT markup comes back whole: unreadable beats vanished. */
  return cut === text || !cut.trim() ? text : cut.trimEnd();
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
