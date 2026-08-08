/* The card's whole history, oldest first — Nova's Thread block.
 *
 * The WHOLE of it, never a tail: `_context.py::dossier` sends `history` with the
 * comment "complete, in order, never cut", and a viewer that showed the last ten
 * would be the summary that docstring refuses. The drawer's body scrolls; the
 * thread does not get to decide what a reader needs.
 *
 * One line per event, drawn the same way on purpose: a PHRASE — the thing that
 * changed, `detail()` — and, under it, the PROSE somebody wrote, `prose()`. A
 * comment is not the only event that carries writing: a close carries the note
 * the worker signed off with (`body.reason`), a release and a hand-in carry
 * `body.note`, a verdict carries both its word and its note. All of it gets the
 * markdown renderer, because a close note is the most substantial writing on
 * most cards. Splitting comments off into their own list would break the one
 * thing a thread is for: what happened, in the order it happened.
 *
 * **This thread has TWO renderers and they must agree.** `mcp/thread.py::detail`
 * is the other one — the same log, read by an agent over MCP instead of by a
 * reader on this page. Change one and you have to change the other; there is no
 * shared code across the language boundary, so the agreement is by hand and this
 * paragraph is the only warning you get.
 *
 * It was NOT agreeing, and the bug is why this file says so now: `detail()` tried
 * body keys in the order `text, note, to, subject, into, verdict` — `reason` was
 * not in the list and `to` WAS, so every close in the log resolved to the string
 * "done" and the worker's note was never reached. The render then drew a text
 * block only for `kind === "comment"`, so even the right string would not have
 * appeared. Both are fixed below; the data was never wrong.
 *
 * One deliberate difference, and it is a superset rather than a disagreement: on
 * a `reviewed` event the Python renderer prints only the note (its fallback loop
 * reaches `note` before `verdict`), while this one prints `pass`/`changes` as the
 * phrase AND the note as prose. Nothing is dropped here that is shown there. */
import { ago, shortActor } from "../../format";
import { Ext, Numstat, commitUrl, readNumstat, type GitReader, type Repo } from "../../links";
import { TONE_FG, type Tone } from "../board/CardTile";
import { Markdown, Mentioned } from "../shared/Markdown";
import { CommitPatch } from "./Patch";
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

/** A body value, only when it is a non-empty string. */
function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** The one-phrase summary of an event: the thing that CHANGED, never the prose
 *  attached to it. Mirrors `mcp/thread.py::detail` branch for branch — the same
 *  log read twice must not grow a second vocabulary.
 *
 *  The trailing loop is the same fallback the Python one keeps, for a kind this
 *  bundle predates: `verdict` is gone from it because `reviewed` has its own
 *  branch now, and `reason`/`note` are absent on purpose — they are prose and
 *  belong to `prose()`, which is exactly the bug this list caused. */
export function detail(event: Event): string {
  const body = event.body;
  if (event.kind === "created") {
    const card = body["card"];
    const title = card && typeof card === "object" ? (card as { title?: string }).title : "";
    return title ?? "";
  }
  if (event.kind === "edited") return `${String(body["field"] ?? "")} → ${JSON.stringify(body["to"])}`;
  if (event.kind === "status") {
    // `(no code)` is the Python renderer's own wording: the card closed with no
    // commit bound to it (`verbs/update.py` writes `no_code`), which a reader
    // should never have to open the log to learn.
    return `${str(body["to"])}${body["no_code"] === true ? " (no code)" : ""}`;
  }
  // Everything these carry is writing; `prose()` draws all of it.
  if (event.kind === "comment" || event.kind === "released" || event.kind === "submitted") return "";
  if (event.kind === "reviewed") return str(body["verdict"]);
  for (const key of ["text", "to", "subject", "into"]) {
    const value = body[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

/** The human writing on an event, if it carries any — rendered as markdown, the
 *  same ink and width a comment gets.
 *
 *  Every kind that carries prose, walked off `verbs/` and `core/review.py`:
 *  `comment.text`, `status.reason` (a close, a drop — the drop reason is REQUIRED
 *  by the server so it can never legitimately be empty), `released.note`,
 *  `submitted.note`, `reviewed.note`. `commit` carries a subject and `claimed` a
 *  branch, which are phrases, not prose; `created`, `edited`, `merged`,
 *  `milestone` and `project` carry no human text at all. */
export function prose(event: Event): string {
  const body = event.body;
  if (event.kind === "comment") return str(body["text"]);
  // `note` as well as `reason`, because that is what the Python renderer accepts
  // and a log written by an older server may carry either.
  if (event.kind === "status") return str(body["reason"]) || str(body["note"]);
  if (event.kind === "released" || event.kind === "submitted" || event.kind === "reviewed") {
    return str(body["note"]);
  }
  return "";
}

/** Both halves on ONE line, joined the way `mcp/thread.py::detail` joins them —
 *  `done — <the note>`. The thread has two rows to spend and draws the prose as
 *  markdown; the Event stream has one, so it gets this. */
export function oneLine(event: Event): string {
  const phrase = detail(event);
  const written = prose(event);
  if (phrase && written) return `${phrase} — ${written}`;
  return phrase || written;
}

function addressed(event: Event): string[] {
  const to = event.body["mentions"];
  return Array.isArray(to) ? to.filter((who): who is string => typeof who === "string") : [];
}

/** The sha a `commit` event carries (`gitwork/bind.py::commit_facts`), read off
 *  an open body: anything that is not a commit, or a body that never had one,
 *  is "" and draws no link. */
function sha(event: Event): string {
  if (event.kind !== "commit") return "";
  const value = event.body["sha"];
  return typeof value === "string" ? value : "";
}

export function Thread({
  history,
  now,
  repo,
  reader,
}: {
  history: Event[];
  now: number;
  /** `BoardPayload.repo` — absent, and a commit line is exactly the text it was
   *  before this existed. See `links.tsx`. */
  repo?: Repo | null | undefined;
  /** The /git door. Absent, a commit line still offers its fold and the fold
   *  still says something true — the cascade's third or fourth step. */
  reader?: GitReader | null | undefined;
}): React.JSX.Element {
  return (
    <div data-testid="thread" style={{ display: "flex", flexDirection: "column" }}>
      {history.map((event) => {
        const tone = DOT[event.kind] ?? "neutral";
        const text = detail(event);
        const written = prose(event);
        const to = addressed(event);
        const ref = sha(event);
        const href = commitUrl(repo, ref);
        // Only a `commit` body has one, so every other line is untouched.
        const counts = event.kind === "commit" ? readNumstat(event.body["numstat"]) : null;
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
                {/* The sha rides on the kind line, the subject stays below in
                    `detail()` — a commit's identity and its sentence, in the
                    two places the thread already puts them. Plain mono text
                    with no slug: same characters, no anchor. */}
                {ref ? (
                  <span className="mono" style={{ color: "var(--accent)", marginLeft: "8px" }}>
                    {href ? (
                      <Ext href={href} title={ref}>
                        <span data-testid="thread-commit-link">{ref.slice(0, 8)}</span>
                      </Ext>
                    ) : (
                      ref.slice(0, 8)
                    )}
                  </span>
                ) : null}
                {counts ? (
                  <span style={{ marginLeft: "8px" }}>
                    <Numstat counts={counts} />
                  </span>
                ) : null}
                {to.length > 0 ? (
                  <span className="mono" style={{ color: "var(--accent)" }}>
                    {" → "}
                    {to.map(shortActor).join(", ")}
                  </span>
                ) : null}
              </div>
              {/* The phrase — the transition, the field, the verdict — stays
                  where it was, so a reader still sees at a glance that this was
                  a close and not a remark. */}
              {text ? (
                <div
                  data-testid="event-detail"
                  style={{ marginTop: "6px", fontSize: "14px", color: "var(--text-2)", lineHeight: 1.55 }}
                >
                  <Mentioned text={text} />
                </div>
              ) : null}
              {/* …and under it whatever somebody actually wrote, whichever kind
                  carried it. A close note is the most substantial writing on
                  most cards; it gets the same renderer a comment gets. */}
              {written ? (
                <div data-testid="event-prose" style={{ marginTop: "6px" }}>
                  <Markdown text={written} />
                </div>
              ) : null}
              {/* The same fold as the Commits section, from the same component:
                  a sha shown twice must not expand into two different panes. */}
              {ref ? (
                <div style={{ marginTop: "8px" }}>
                  <CommitPatch reader={reader} repo={repo} sha={ref} />
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
