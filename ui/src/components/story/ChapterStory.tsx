/* The landed chapter — what the Board page becomes when the chapter is DONE.
 *
 * A finished chapter in six kanban columns is one wall of identical done tiles:
 * the shape that answers "what needs a move?" has nothing to say when the
 * answer is "nothing, we finished". So this view replaces the columns for that
 * state only (App.tsx swaps on `story != null`) with the chapter told as a
 * result: ONE strip of aggregate stats, then the cards themselves, SIDE BY
 * SIDE in a responsive grid, in landing order — left to right, top to bottom.
 *
 * The header was a celebration block for one day (2026-08-14) and it was a
 * DUPLICATE: the milestone's title is already on the picker and its goal prose
 * already has a home in the Monitor tab's chapter pane (monitor/Chapter.tsx,
 * which owns the clamp and the reasoning about how tall a goal is allowed to
 * be). Repeating goal, criteria and a 26px title here pushed the actual
 * content — the cards — below the fold for no gain. What survives is the
 * arithmetic and the completion signal, folded INTO the strip as a mark and a
 * chip, so the grid starts immediately under one line of chrome.
 *
 * It was a vertical rail for one day (2026-08-14) and that was the wrong read:
 * one card per row, a disc and a spine, everything narrow and stacked, and the
 * only clickable thing was the title. A chapter is a body of work, not a
 * procession; a grid puts it on one screen and lets the eye compare. The WHOLE
 * tile is the target now, hover-lifted and tab-reachable, because "it did not
 * look clickable" was half of the complaint and "only the title was" the other.
 *
 * Read-only exactly like Board.tsx: every tile opens the EXISTING drawer
 * (`openCard` → App.tsx mounts `Drawer` over any page), no write verb, no
 * fetch — the `activity` payload arrives whole through useBoard's one fetch
 * path. The arithmetic (landing order, per-card diff, the header strip) lives
 * in `stats.ts`, pure, so it is pinned headlessly; this file only decides what
 * each number looks like, in tokens. */
import { useState } from "react";

import { ago } from "../../format";
import { Markdown } from "../shared/Markdown";
import type { ActivityPayload, CardStory } from "../../types";
import { chapterStats, diffOf, landingOrder, summaryOf, type ChapterStats } from "./stats";

export interface ChapterStoryProps {
  story: ActivityPayload;
  openCard: (id: string) => void;
}

const page: React.CSSProperties = {
  height: "100%",
  overflowY: "auto",
  padding: "0 24px 30px",
};

const gridMeasure: React.CSSProperties = {
  maxWidth: "1180px",
  margin: "0 auto",
  animation: "tk-lift 300ms cubic-bezier(0.2, 0.8, 0.2, 1)",
};

const chip: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "3px 9px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
};

/* ── the stats strip — the whole header ─────────────────────────────────── */

function Stat({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div style={{ display: "grid", gap: "2px" }}>
      <span className="num" style={{ fontSize: "17px", fontWeight: 550, letterSpacing: "-0.03em" }}>
        {value}
      </span>
      <span style={{ fontSize: "10.5px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </span>
    </div>
  );
}

/** The strip's own wording, one place. `+/−` share a cell — they are one fact. */
function strip(s: ChapterStats): { label: string; value: string }[] {
  const cards = s.dropped > 0 ? `${s.done} + ${s.dropped} dropped` : `${s.done}`;
  return [
    { label: "cards", value: cards },
    { label: "commits", value: `${s.commits}` },
    { label: "files", value: `${s.files}` },
    { label: "lines", value: `+${s.added} −${s.deleted}` },
    { label: "worked", value: ago(s.seconds) || "0s" },
    { label: "span", value: ago(Math.max(0, s.to - s.from)) || "0s" },
  ];
}

/** The completion signal, folded into the strip: a small `ok`-toned disc with a
 *  check and the word for what happened. The palette's own green, no emoji, no
 *  confetti — and no separate celebration block above it, which is the point. */
function Landed({ status }: { status: string }): React.JSX.Element {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "9px", flex: "none" }}>
      <span
        aria-hidden
        style={{
          width: "26px",
          height: "26px",
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          background: "var(--ok-soft)",
          border: "1px solid var(--ok)",
          color: "var(--ok)",
        }}
      >
        <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
          <path d="M4 10.5 8.2 14.5 16 6" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span style={{ ...chip, color: "var(--ok)", background: "var(--ok-soft)" }}>
        {status === "landed" ? "chapter landed" : "chapter complete"}
      </span>
    </div>
  );
}

function Header({ story, stats }: { story: ActivityPayload; stats: ChapterStats }): React.JSX.Element {
  const stone = story.milestone;
  if (!stone) return <></>;
  return (
    <header data-testid="story-header" style={{ padding: "18px 0 14px" }}>
      <div
        data-testid="story-stats"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "26px",
          flexWrap: "wrap",
          padding: "13px 20px",
          borderRadius: "14px",
          background: "var(--pane)",
          border: "1px solid var(--hair)",
        }}
      >
        <Landed status={stone.status} />
        <span aria-hidden style={{ width: "1px", alignSelf: "stretch", background: "var(--hair)" }} />
        {strip(stats).map((s) => (
          <Stat key={s.label} label={s.label} value={s.value} />
        ))}
      </div>
    </header>
  );
}

/* ── one tile ───────────────────────────────────────────────────────────── */

/** The diff, as NUMBERS. The rail drew a sqrt-scaled bar whose width compared
 *  one card against the chapter's biggest; in a grid that comparison is a lie
 *  the eye cannot make anyway — tiles sit in different columns and rows, and a
 *  bar there reads as decoration. So the counts are the fact, coloured in the
 *  same two tones, and `bin` still says "git could not count this file" rather
 *  than letting a binary vanish into a 0. */
function Diff({ card }: { card: CardStory }): React.JSX.Element | null {
  const diff = diffOf(card);
  if (diff.added === 0 && diff.deleted === 0 && !diff.binary) return null;
  return (
    <div data-testid="diff" className="num mono" style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px" }}>
      {/* One pill, two tones: the pair is a single fact and reads as one shape
          at a glance instead of two loose numbers among the chips. */}
      <span
        style={{
          display: "inline-flex",
          gap: "6px",
          padding: "2px 7px",
          borderRadius: "6px",
          background: "var(--pane-3)",
        }}
      >
        <span style={{ color: "var(--ok)" }}>+{diff.added}</span>
        <span style={{ color: "var(--danger)" }}>−{diff.deleted}</span>
      </span>
      {diff.binary ? (
        <span data-testid="bin-chip" style={{ ...chip, color: "var(--text-2)", background: "var(--pane-3)" }}>
          bin
        </span>
      ) : null}
    </div>
  );
}

/** The whole tile is the button — the same idiom as `board/CardTile.tsx`: same
 *  radius, hairline, pane background, chip geometry and type scale, and the
 *  same affordance (a 2px rise plus the accent glow, never a recoloured
 *  border) so this page reads as the dashboard and not as a second design
 *  system. `all: unset` takes the focus ring with it, so it is re-added: a
 *  chapter you can tab through is why this is a button and not a div. */
function Tile({
  card,
  ordinal,
  openCard,
}: {
  card: CardStory;
  ordinal: number;
  openCard: (id: string) => void;
}): React.JSX.Element {
  const [lift, setLift] = useState(false);
  const [ring, setRing] = useState(false);
  const dropped = card.status === "dropped";
  const summary = summaryOf(card);
  const style: React.CSSProperties = {
    all: "unset",
    boxSizing: "border-box",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    height: "100%",
    width: "100%",
    /* A gradient of two of the page's OWN pane tones — no new colour, just a
       hint of depth so the tile reads as a raised object and not as a box. */
    background: "linear-gradient(180deg, var(--pane-2), var(--pane))",
    borderStyle: "solid",
    borderWidth: "1px",
    borderColor: "var(--hair)",
    borderRadius: "14px",
    padding: "15px 16px",
    transition: "all 150ms cubic-bezier(0.2, 0.8, 0.2, 1)",
    /* Dropped is muted, never shouted: it stays fully legible, one notch back
       in the page's own ink, and says so on a chip. */
    opacity: dropped ? 0.62 : 1,
    ...(lift
      ? {
          boxShadow: "0 0 0 3px var(--accent-soft), 0 10px 24px var(--glow)",
          borderColor: "var(--accent-line)",
          transform: "translateY(-2px)",
          opacity: 1,
        }
      : {}),
    ...(ring ? { outline: "2px solid var(--accent)", outlineOffset: "2px" } : {}),
  };
  return (
    <button
      type="button"
      style={style}
      data-testid="story-tile"
      data-card={card.id}
      data-dropped={dropped ? "true" : undefined}
      title={card.title}
      onClick={() => openCard(card.id)}
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
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        {/* The ordinal is the one thing a grid loses that the rail had: reading
            order is landing order, and a two-dimensional layout cannot say so
            on its own. Small, mono, in the faintest ink that is still legible. */}
        <span
          data-testid="ordinal"
          className="num mono"
          style={{
            fontSize: "10px",
            color: dropped ? "var(--text-3)" : "var(--ok)",
            background: dropped ? "var(--pane-3)" : "var(--ok-soft)",
            borderRadius: "6px",
            padding: "2px 6px",
            flex: "none",
          }}
        >
          {ordinal}
        </span>
        {/* The id is a handle, not a heading: fainter than the title by a
            whole step so the hierarchy inside the tile is title first. */}
        <span className="mono" style={{ fontSize: "10px", color: "var(--faint)", letterSpacing: "0.01em" }}>
          {card.id}
        </span>
        <span style={{ flex: 1 }} />
        <Diff card={card} />
      </div>

      {/* Two lines, CLAMPED — a card title is a sentence and a 300px column
          would end it after four words if this were a single ellipsised line. */}
      <div
        style={{
          fontSize: "14px",
          fontWeight: 550,
          letterSpacing: "-0.025em",
          lineHeight: 1.35,
          color: "var(--text)",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          textDecoration: dropped ? "line-through" : "none",
        }}
      >
        {card.title}
      </div>

      {summary ? (
        <div
          data-testid="story-summary"
          style={{
            fontSize: "11.5px",
            color: "var(--text-2)",
            lineHeight: 1.45,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {/* INLINE: these are commit subjects and reviewer notes — they quote
              calls and paths, so backticks must read as code, but a heading or
              a fence has no business inside a tile. */}
          <Markdown text={summary} inline />
        </div>
      ) : null}

      {/* The chips sit at the BOTTOM of every tile, whatever the title's
          height — that is what `marginTop: auto` under a column flex buys, and
          it is what makes a row of tiles scan as a row. */}
      <div style={{ display: "flex", gap: "5px", flexWrap: "wrap", marginTop: "auto", paddingTop: "3px" }}>
        {dropped ? (
          <span data-testid="dropped-chip" style={{ ...chip, color: "var(--text-2)", background: "var(--pane-3)" }}>
            dropped
          </span>
        ) : null}
        {card.seconds > 0 ? (
          <span data-testid="worked" style={{ ...chip, color: "var(--text-2)", background: "var(--pane-3)" }}>
            {ago(card.seconds)} worked
          </span>
        ) : null}
        {card.commits_total > 0 ? (
          <span data-testid="commit-count" style={{ ...chip, color: "var(--text-2)", background: "var(--pane-3)" }}>
            {card.commits_total} commit{card.commits_total === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
    </button>
  );
}

/** The order connector. Ordinals say WHICH position a card holds; the arrow
 *  says the positions are a sequence — together they make development order
 *  legible in two dimensions, which neither does alone.
 *
 *  It is drawn per TILE, in the gutter to its right, on every tile but the
 *  chapter's last. Not per ROW-END, deliberately: `auto-fill` decides the
 *  column count from the container's width at paint time, so "is this tile at
 *  the end of its row?" is only answerable by measuring the DOM — and this
 *  view is rendered and pinned headlessly through react-dom/server, where
 *  there is no layout to measure. A wrapping arrow would also have to be a
 *  different glyph (down-and-back), which is a diagram; this stays chrome:
 *  --text-3, 11px, aria-hidden, pointer-events off so it never eats a click. */
function Step({ last, children }: { last: boolean; children: React.ReactNode }): React.JSX.Element {
  return (
    <div style={{ position: "relative", display: "flex" }}>
      {children}
      {last ? null : (
        <span
          data-testid="story-arrow"
          aria-hidden
          style={{
            position: "absolute",
            right: "-12.5px",
            top: "50%",
            transform: "translateY(-50%)",
            display: "flex",
            color: "var(--text-3)",
            pointerEvents: "none",
          }}
        >
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <path
              d="M1.5 6h8M6.4 3l3 3-3 3"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      )}
    </div>
  );
}

/* ── the page ───────────────────────────────────────────────────────────── */

export function ChapterStory({ story, openCard }: ChapterStoryProps): React.JSX.Element {
  const cards = landingOrder(story.cards);
  const stats = chapterStats(story.cards);
  return (
    <div style={page} data-testid="chapter-story">
      <div style={gridMeasure}>
        <Header story={story} stats={stats} />
        {/* `auto-fill` + `minmax(300px, 1fr)` is the whole responsive rule: as
            many columns as fit at 300px each, one column below that. No media
            query, no breakpoint list, and it works inside the drawer-narrowed
            pane as well as at 1600px. */}
        <div
          data-testid="story-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: "14px",
            alignItems: "stretch",
          }}
        >
          {cards.map((card, i) => (
            <Step key={card.id} last={i === cards.length - 1}>
              <Tile card={card} ordinal={i + 1} openCard={openCard} />
            </Step>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ChapterStory;
