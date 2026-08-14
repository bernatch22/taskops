/* One card on the kanban — Nova's tile (Taskops Nova.dc.html, the BOARD section).
 *
 * The tile knows NOTHING about groups. Everything that distinguishes a stalled
 * card from a doing one, or a card waiting for review from one being checked,
 * arrives as `chip` + `marker` from `Board.tsx`, which is where the derivation
 * lives. That is deliberate: v1 drew stored statuses straight onto the tile and
 * its teardown (§6) lists exactly what the shortcut hid — "handed over, nobody
 * checking" and "being verified" drew identically. A tile that cannot invent a
 * state cannot lose one either.
 *
 * It is a button, and the only thing it does is open the drawer. There is no
 * write verb on this page and no drag handle: the UI does not move cards. */
import { useState } from "react";

import { ago } from "../../format";
import { Avatar } from "../shared/Avatar";
import { Markdown } from "../shared/Markdown";
import type { BoardRow } from "../../types";

/** The five ways a thing can be coloured. Nothing here is a literal colour —
 *  the palette lives in theme/tokens.css and nowhere else. */
export type Tone = "accent" | "ok" | "warn" | "danger" | "neutral";

export const TONE_FG: Record<Tone, string> = {
  accent: "var(--accent)",
  ok: "var(--ok)",
  warn: "var(--warn)",
  danger: "var(--danger)",
  neutral: "var(--text-2)",
};

export const TONE_BG: Record<Tone, string> = {
  accent: "var(--accent-soft)",
  ok: "var(--ok-soft)",
  warn: "var(--warn-soft)",
  danger: "var(--danger-soft)",
  neutral: "var(--pane-3)",
};

/** A sub-state, spelled out. The Review column carries three of these and that
 *  is the whole point of merging its three groups into one column. */
export interface Chip {
  label: string;
  tone: Tone;
}

export interface CardTileProps {
  row: BoardRow;
  /** the sub-state badge, when the column has more than one kind of row in it */
  chip?: Chip | undefined;
  /** a coloured spine down the left edge — the danger marker on a stalled card */
  marker?: Tone | undefined;
  /** the reviewer's words, or the submit note; shown verbatim, never summarised */
  note?: string | undefined;
  /** blocked only: the cards this one is waiting for */
  waitingOn?: readonly string[] | undefined;
  /** WHICH CHAPTER this card belongs to — the milestone's TITLE, already
   *  resolved, and only when the view actually holds more than one of them.
   *
   *  The tile does not resolve it and does not decide whether to show it, for
   *  the same reason it does not know about groups: both answers are about the
   *  WHOLE view — which chapters are on screen — and a tile can only see itself.
   *  `Board.tsx::chapterLabels` owns both, computed once for the page. Absent is
   *  the normal case (a chapter in focus), and the line is then not drawn at all
   *  rather than drawn empty — the tile keeps its height. */
  chapter?: string | undefined;
  /** Hands the tile's element to whoever is animating the page (`useFlip`).
   *
   *  A plain callback prop and not `forwardRef`: the tile is not a generic
   *  primitive somebody composes, it is this board's tile, and the ref goes to
   *  exactly one caller. The tile itself still knows nothing about motion — it
   *  hands over a node and never reads it. */
  tileRef?: ((el: HTMLElement | null) => void) | undefined;
  /** A comment landed on this card moments ago.
   *
   *  DERIVED, never stored and never counted: `toasts/useToasts.ts::pulsing`
   *  answers it from the live toast stack, so the tile lights because a message
   *  about it is younger than the window and goes dark by arithmetic. There is
   *  no badge and no unread number here on purpose — this board has no
   *  read-receipts and must not grow one through the back door of a UI that
   *  remembers what you looked at.
   *
   *  The tile does not decide it, exactly as it does not decide `chip` or
   *  `chapter`: the answer is about the whole page (which cards were commented
   *  on), and a tile can only see itself. */
  recentComment?: boolean | undefined;
  onOpen: (id: string) => void;
}

/** p0 is urgent and p3 is idle, so the scale runs hot → cold. */
const PRIORITY: Record<number, Tone> = { 0: "danger", 1: "warn", 2: "accent", 3: "neutral" };

/** The board's own vocabulary, from `schema.py`: "0 urgent … 3 idle".
 *
 *  2 is the DEFAULT every card gets when nobody says otherwise, so it is not
 *  worth a pill on every tile — Nova wraps its priority pill in an `sc-if` for
 *  the same reason. What is left is what somebody chose deliberately. */
const PRIORITY_LABEL: Record<number, string> = { 0: "urgent", 1: "high", 3: "idle" };

/** The mono line at the top right: how long it has been quiet when nobody holds
 *  it, how long the lease has run when somebody does. `quiet_for` is null while
 *  a lease is live — that is the server's own distinction, kept. */
function meta(row: BoardRow): { text: string; tone: Tone } {
  if (row.quiet_for === null) {
    return { text: `${ago(Date.now() / 1000 - row.since)} in`, tone: "neutral" };
  }
  return { text: `quiet ${ago(row.quiet_for)}`, tone: row.assignee ? "warn" : "neutral" };
}

const tile: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  display: "block",
  background: "var(--pane)",
  /* Per-side LONGHANDS, never the `border` shorthand, and React says why out
   * loud: "Updating a style property during rerender (borderColor) when a
   * conflicting property is set (borderLeft) can lead to styling bugs." The
   * hover repaints three sides and the marker owns the fourth, so mixing the
   * shorthand with a per-side one left the border in whichever state React
   * happened to apply last — the grey edge that would not go away. */
  borderStyle: "solid",
  borderWidth: "1px",
  borderColor: "var(--hair)",
  borderRadius: "13px",
  padding: "14px 15px",
  // The design's own easing, not a linear stand-in: `cubic-bezier(0.2,0.8,0.2,1)`
  // overshoots slightly and is what makes the lift feel like a lift.
  transition: "all 150ms cubic-bezier(0.2, 0.8, 0.2, 1)",
};

/** `all: unset` on a button removes the focus ring with everything else, so the
 *  design re-adds one and so must we — a board you can tab through is the whole
 *  reason these are buttons and not divs. Offset outward, because the tile has
 *  no `overflow: hidden` to clip it. */
const focusRing: React.CSSProperties = {
  outline: "2px solid var(--accent)",
  outlineOffset: "2px",
};

const pill: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "3px 9px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
};

export function CardTile(props: CardTileProps): React.JSX.Element {
  const { row, chip, marker, note, waitingOn, chapter, tileRef, recentComment, onOpen } = props;
  const [lift, setLift] = useState(false);
  const [ring, setRing] = useState(false);
  const when = meta(row);
  const who = row.holder ?? row.assignee;
  const style: React.CSSProperties = {
    ...tile,
    /* THE HOVER DOES NOT TOUCH THE BORDER. Asked for three times, and the first
     * two answers were both wrong because I kept hearing "make it a different
     * colour" instead of "stop changing it": Nova's `--accent-line` composites
     * over `--pane` to rgb(63,60,96) and reads grey, and swapping it for solid
     * `--accent` only made the change louder. A border that recolours under the
     * cursor is the complaint, whatever colour it lands on.
     *
     * So the affordance is ELEVATION, which is what the design was already
     * saying with the half of the hover I kept: the 2px rise, plus the glow
     * borrowed from the dots Nova uses to mark a live thing. The tile lifts off
     * the column; its edges stay exactly where they were. The marker bar is
     * untouched by construction now — nothing repaints a border at all. */
    ...(lift
      ? { boxShadow: "0 0 0 3px var(--accent-soft)", transform: "translateY(-2px)" }
      : {}),
    /* JUST COMMENTED. The same glow the hover uses, one ring wider and without
     * the rise: the reader is not pointing at this card, the board is pointing
     * at it for them. It is the hover's vocabulary on purpose — a board with
     * two ways of saying "look here" reads as two boards — and it decays
     * through the tile's own 150ms transition when the flag goes false, which
     * is why there is no keyframe and nothing to replay.
     *
     * The BORDER is untouched, hover or pulse: a tile whose edge recolours was
     * the complaint this file's hover comment records, and a second feature
     * doing it would be that bug again under a new name.
     *
     * After the lift, so a card under the cursor reads as hovered — one
     * affordance at a time, and the cursor's is the one the reader caused. */
    ...(recentComment && !lift ? { boxShadow: "0 0 0 5px var(--accent-soft)" } : {}),
    /* The marker owns the left side, always — hover or not, there is no longer
     * anything competing for it. */
    ...(marker ? { borderLeftWidth: "3px", borderLeftColor: TONE_FG[marker] } : {}),
    ...(ring ? focusRing : {}),
  };

  return (
    <button
      type="button"
      ref={tileRef}
      style={style}
      data-testid="tile"
      data-card={row.id}
      onClick={() => onOpen(row.id)}
      onMouseEnter={() => setLift(true)}
      onMouseLeave={() => setLift(false)}
      onFocus={() => {
        setLift(true);
        setRing(true);
      }}
      onBlur={() => {
        setLift(false);
        setRing(false);
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "9px" }}>
        <span className="mono" style={{ fontSize: "10.5px", color: "var(--text-3)" }}>
          {row.id}
        </span>
        <span className="mono" style={{ fontSize: "10.5px", color: TONE_FG[when.tone] }}>
          {when.text}
        </span>
      </div>

      {chip ? (
        <div style={{ marginBottom: "9px" }}>
          <span
            data-testid="chip"
            style={{ ...pill, color: TONE_FG[chip.tone], background: TONE_BG[chip.tone] }}
          >
            {chip.label}
          </span>
        </div>
      ) : null}

      <div
        style={{ fontSize: "14px", fontWeight: 450, letterSpacing: "-0.025em", lineHeight: 1.35 }}
      >
        {row.title}
      </div>

      {/* The chapter — the Worktrees row's vocabulary, verbatim: the same `⌗`
          prefix, the same `--text-3` ink, one line, clipped. A chapter title is
          a sentence and a column is 278px wide. Not a link and not clickable:
          the header picker is the one way to narrow the board, and a second one
          is a second thing that can disagree with the first. */}
      {chapter ? (
        <div
          data-testid="tile-chapter"
          style={{
            fontSize: "11.5px",
            color: "var(--text-3)",
            marginTop: "6px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {`⌗ ${chapter}`}
        </div>
      ) : null}

      {note ? (
        <div style={{ fontSize: "11.5px", color: "var(--text-2)", marginTop: "8px" }}>
          {/* The submit note or the reviewer's words — prose, "verbatim, never
              summarised", and it quotes calls and file names as often as any
              comment does. INLINE: a tile is 278px of a kanban column, so the
              block renderer's headings and fences have no business here, but a
              backtick printing as a backtick had none either. */}
          <Markdown text={note} inline />
        </div>
      ) : null}

      {waitingOn && waitingOn.length > 0 ? (
        <div
          data-testid="waiting"
          style={{ fontSize: "11.5px", color: "var(--text-3)", marginTop: "8px" }}
        >
          waiting on{" "}
          {waitingOn.map((id) => (
            <span key={id} className="mono" style={{ color: "var(--text-2)", marginRight: "6px" }}>
              {id}
            </span>
          ))}
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "8px",
          marginTop: "13px",
        }}
      >
        <div style={{ display: "flex", gap: "5px", flexWrap: "wrap", minWidth: 0 }}>
          {row.labels.map((label) => (
            <span key={label} style={{ ...pill, color: "var(--text-2)", background: "var(--pane-3)" }}>
              {label}
            </span>
          ))}
          {/* Nova draws priority as a pill of TEXT beside the labels, not as a
              dot — a 7px disc in a row of worded pills says "something is
              coloured here" and nothing about which. The geometry is the
              design's, verbatim; the colour follows the priority instead of
              Nova's flat accent, because a board whose p0 and p3 read alike
              would need the reader to hover to find the urgent one. */}
          {PRIORITY_LABEL[row.priority] ? (
            <span
              data-testid="priority"
              title={`priority ${row.priority}`}
              style={{
                ...pill,
                color: TONE_FG[PRIORITY[row.priority] ?? "neutral"],
                background: TONE_BG[PRIORITY[row.priority] ?? "neutral"],
              }}
            >
              {PRIORITY_LABEL[row.priority]}
            </span>
          ) : null}
        </div>
        {/* WHO is on this card — the same disc the header's presence row draws,
            in the same actor's colour (`shared/Avatar.tsx`). It used to be a
            hand-rolled span here whose colour meant the ROLE, so one agent was
            purple in the header and grey on its own tile.

            `row.holder` is the LIVE lease and `row.assignee` is who it was
            handed to (`verbs/_rows.py::row`) — the first when there is one, and
            it is `holder` ALONE that decides `live`: a stalled card carries the
            second and not the first, and the ghosted disc is that group saying
            "this is whose card it is, and nobody is running it".

            The disc is INSIDE the tile, so a card crossing to another column
            carries its agent across with it — that is the whole of "you can see
            which agent is working the card" while it moves. */}
        {who ? <Avatar actor={who} live={row.holder !== null} /> : null}
      </div>
    </button>
  );
}
