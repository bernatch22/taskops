/* The landing-timeline — what the Board page becomes when the chapter is DONE.
 *
 * A finished chapter in six kanban columns is one wall of identical done tiles:
 * the shape that answers "what needs a move?" has nothing to say when the
 * answer is "nothing, we finished". So this view replaces the columns for that
 * state only (App.tsx swaps on `story != null`) with the chapter told as a
 * story: a celebration header, then ONE vertical rail, each done card a
 * station on it in landing order, saying at a glance what it did.
 *
 * Read-only exactly like Board.tsx: every station title is a button into the
 * existing drawer (`openCard`), no write verb, no fetch — the `activity`
 * payload arrives whole through useBoard's one fetch path. The arithmetic
 * (landing order, per-card diff, the header strip) lives in `stats.ts`, pure,
 * so it is pinned headlessly; this file only decides what each number looks
 * like, in tokens. */
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
  padding: "0 24px 26px",
};

/** One centered measure for header and rail — a timeline is read down, not
 *  across, and full-width prose under a 1600px window is unreadable. */
const measure: React.CSSProperties = {
  maxWidth: "760px",
  margin: "0 auto",
  animation: "tk-lift 300ms cubic-bezier(0.2, 0.8, 0.2, 1)",
};

const chip: React.CSSProperties = {
  fontSize: "10.5px",
  padding: "3px 9px",
  borderRadius: "20px",
  whiteSpace: "nowrap",
};

/* ── the celebration header ─────────────────────────────────────────────── */

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

function Header({ story, stats }: { story: ActivityPayload; stats: ChapterStats }): React.JSX.Element {
  const stone = story.milestone;
  if (!stone) return <></>;
  return (
    <header data-testid="story-header" style={{ padding: "26px 0 30px", textAlign: "center" }}>
      {/* The completion mark: a laurel-toned disc with a check, drawn in the
          `ok` tone — the palette's own green, no emoji, no confetti. */}
      <div
        aria-hidden
        style={{
          width: "44px",
          height: "44px",
          margin: "0 auto 14px",
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          background: "var(--ok-soft)",
          border: "1px solid var(--ok)",
          color: "var(--ok)",
        }}
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M4 10.5 8.2 14.5 16 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div style={{ ...chip, display: "inline-block", color: "var(--ok)", background: "var(--ok-soft)", marginBottom: "10px" }}>
        {stone.status === "landed" ? "chapter landed" : "chapter complete"}
      </div>
      <h1 style={{ margin: "0 0 12px", fontSize: "26px", fontWeight: 550, letterSpacing: "-0.035em", lineHeight: 1.2 }}>
        {stone.title}
      </h1>
      {stone.goal ? (
        <div style={{ color: "var(--text-2)", fontSize: "14px", maxWidth: "560px", margin: "0 auto", textAlign: "left" }}>
          <Markdown text={stone.goal} />
        </div>
      ) : null}
      {(stone.criteria ?? []).length > 0 ? (
        <ul
          data-testid="story-criteria"
          style={{
            listStyle: "none",
            margin: "16px auto 0",
            padding: 0,
            maxWidth: "560px",
            textAlign: "left",
            display: "grid",
            gap: "6px",
          }}
        >
          {(stone.criteria ?? []).map((line) => (
            <li key={line} style={{ display: "flex", gap: "8px", fontSize: "12.5px", color: "var(--text-2)" }}>
              <span style={{ color: "var(--ok)", flex: "none" }}>✓</span>
              <Markdown text={line} inline />
            </li>
          ))}
        </ul>
      ) : null}
      <div
        data-testid="story-stats"
        style={{
          display: "flex",
          justifyContent: "center",
          gap: "30px",
          flexWrap: "wrap",
          marginTop: "24px",
          padding: "16px 20px",
          borderRadius: "16px",
          background: "var(--pane)",
          border: "1px solid var(--hair)",
        }}
      >
        {strip(stats).map((s) => (
          <Stat key={s.label} label={s.label} value={s.value} />
        ))}
      </div>
    </header>
  );
}

/* ── one station ────────────────────────────────────────────────────────── */

/** The diff bar: green added over red deleted, the WIDTH sqrt-scaled against
 *  the chapter's biggest card so one giant diff does not flatten the rest into
 *  hairlines — the eye reads area-ish, not linearly. The split inside the bar
 *  stays linear: it says "mostly additions", and sqrt there would lie. */
function DiffBar({ card, max }: { card: CardStory; max: number }): React.JSX.Element | null {
  const diff = diffOf(card);
  const total = diff.added + diff.deleted;
  if (total === 0 && !diff.binary) return null;
  const width = max > 0 && total > 0 ? Math.max(4, (Math.sqrt(total) / Math.sqrt(max)) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "7px" }}>
      {total > 0 ? (
        <>
          <div
            data-testid="diff-bar"
            title={`+${diff.added} −${diff.deleted}`}
            style={{ display: "flex", height: "5px", borderRadius: "3px", overflow: "hidden", width: `${width}%`, maxWidth: "100%" }}
          >
            {diff.added > 0 ? (
              <span style={{ background: "var(--ok)", flexGrow: diff.added, minWidth: "2px" }} />
            ) : null}
            {diff.deleted > 0 ? (
              <span style={{ background: "var(--danger)", flexGrow: diff.deleted, minWidth: "2px" }} />
            ) : null}
          </div>
          <span className="num mono" style={{ fontSize: "10.5px", color: "var(--text-3)", flex: "none" }}>
            +{diff.added} −{diff.deleted}
          </span>
        </>
      ) : null}
      {diff.binary ? (
        <span data-testid="bin-chip" style={{ ...chip, color: "var(--text-2)", background: "var(--pane-3)" }}>
          bin
        </span>
      ) : null}
    </div>
  );
}

function Station({
  card,
  max,
  openCard,
}: {
  card: CardStory;
  max: number;
  openCard: (id: string) => void;
}): React.JSX.Element {
  const dropped = card.status === "dropped";
  const summary = summaryOf(card);
  return (
    <li
      data-testid="station"
      data-card={card.id}
      data-dropped={dropped ? "true" : undefined}
      style={{ display: "grid", gridTemplateColumns: "34px 1fr", gap: "14px", opacity: dropped ? 0.55 : 1 }}
    >
      {/* the disc on the rail: a check for a landed card, a strike for a
          dropped one — part of the story, told in a lower voice */}
      <div style={{ display: "grid", justifyItems: "center" }}>
        <span
          aria-hidden
          style={{
            width: "22px",
            height: "22px",
            borderRadius: "50%",
            display: "grid",
            placeItems: "center",
            fontSize: "11px",
            background: dropped ? "var(--pane-3)" : "var(--ok-soft)",
            border: `1px solid ${dropped ? "var(--hair-2)" : "var(--ok)"}`,
            color: dropped ? "var(--text-3)" : "var(--ok)",
          }}
        >
          {dropped ? "—" : "✓"}
        </span>
      </div>
      <div
        style={{
          background: "var(--pane)",
          border: "1px solid var(--hair)",
          borderRadius: "13px",
          padding: "13px 15px",
          marginBottom: "14px",
          minWidth: 0,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", alignItems: "baseline" }}>
          <button
            type="button"
            data-testid="station-title"
            onClick={() => openCard(card.id)}
            style={{
              all: "unset",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: 450,
              letterSpacing: "-0.025em",
              lineHeight: 1.35,
              color: "var(--text)",
              textDecoration: dropped ? "line-through" : "none",
            }}
          >
            {card.title}
          </button>
          <span className="mono" style={{ fontSize: "10.5px", color: "var(--text-3)", flex: "none" }}>
            {card.id}
          </span>
        </div>
        {summary ? (
          <div style={{ fontSize: "12px", color: "var(--text-2)", marginTop: "6px" }}>
            <Markdown text={summary} inline />
          </div>
        ) : null}
        <DiffBar card={card} max={max} />
        <div style={{ display: "flex", gap: "5px", marginTop: "9px", flexWrap: "wrap" }}>
          {dropped ? (
            <span style={{ ...chip, color: "var(--text-2)", background: "var(--pane-3)" }}>dropped</span>
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
      </div>
    </li>
  );
}

/* ── the page ───────────────────────────────────────────────────────────── */

export function ChapterStory({ story, openCard }: ChapterStoryProps): React.JSX.Element {
  const stations = landingOrder(story.cards);
  const stats = chapterStats(story.cards);
  const max = Math.max(0, ...stations.map((c) => {
    const d = diffOf(c);
    return d.added + d.deleted;
  }));
  return (
    <div style={page} data-testid="chapter-story">
      <div style={measure}>
        <Header story={story} stats={stats} />
        <ol
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            position: "relative",
          }}
        >
          {/* the rail itself: one hairline behind the discs, top to bottom */}
          <div
            aria-hidden
            style={{
              position: "absolute",
              left: "16px",
              top: "10px",
              bottom: "24px",
              width: "2px",
              background: "var(--hair-2)",
            }}
          />
          {stations.map((card) => (
            <Station key={card.id} card={card} max={max} openCard={openCard} />
          ))}
        </ol>
      </div>
    </div>
  );
}

export default ChapterStory;
