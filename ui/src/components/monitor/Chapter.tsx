/* Chapter in focus — Taskops Nova.dc.html lines 344-362.
 *
 * The ONE pane with no `h2` header block: it opens with a `20px 20px 16px` body
 * carrying an 11.5px `--text-3` eyebrow ("Chapter in focus"), then the milestone
 * title at 21px / weight 500 / letter-spacing -0.035em, then the goal at 13.5px
 * line-height 1.55. Below it the rules, each a `PaneTile` on `--pane-2` with its
 * mono index. It closes on a `PaneRow` footer: "Integration branch" against the
 * branch in `--accent`.
 *
 * So `Pane` is used WITHOUT `title` here — that is why the prop is optional.
 *
 * A milestone also carries `criteria` (docs/fan-out.md §10), and Nova has NO
 * slot for it: the design predates the field. tk-60334f raised it as a design
 * question and tk-77dc9c answered it — the field now reaches the browser
 * (`types.ts::Milestone.criteria`) and is drawn HERE, as a second numbered list
 * under the rules, subordinate: smaller type, `--pane-3` instead of `--pane-2`,
 * `--text-2` instead of `--text`.
 *
 * **This placement is provisional and belongs to Berna.** It is a deliberate
 * departure from the .dc.html, made rather than silently dropping a field the
 * board already gates a merge on. Two things about it are open:
 *
 *   · the placement — it could equally be a row above the "Integration branch"
 *     footer, its own pane, or a disclosure. Moving it is this one `<div>`;
 *     nothing else in the pane depends on where it sits.
 *   · the LABELS. The design draws the rules unlabelled, because they were the
 *     only list. Two adjacent numbered lists with no labels are confusable, and
 *     the card's own criterion is that they must not be — so both lists get a
 *     small eyebrow ("Rules — every card in this chapter" / "Accepted against —
 *     the chapter as a whole"). Adding one to the rules touches drawn design;
 *     if Berna wants Nova's bare rules back, make `NumberedList`'s `label`
 *     optional and drop it from the rules call.
 *
 * A chapter with no criteria draws NO section and no label — an empty heading
 * is the "pane somebody forgot" that `PaneEmpty` exists to prevent.
 *
 * ── SEVERAL CHAPTERS OPEN IS NOT A FAULT (tk-13d115) ──────────────────────
 *
 * `verbs/_facts.py::in_scope` returns `None` for zero open chapters AND for
 * several — it refuses to guess between them, and that refusal is right and
 * stays. What was wrong was this pane's reading of it: it drew a paragraph
 * apologising ("2 chapters are open — … Land or drop the finished ones"), so a
 * normal board with two chapters in flight got a screen that said NOTHING about
 * either one and told the reader to close one.
 *
 * Now it LISTS them, one foldable row each, first expanded. Two things decided
 * that shape:
 *
 *   · AN ACCORDION AND NOT TABS. Tabs mean CHOOSING one, and choosing a chapter
 *     is already the header picker's job — a second control that selects would
 *     be a second source of one fact, and the entry not chosen would disappear,
 *     which is the opposite of showing both. An accordion selects nothing: it
 *     is a list where each entry can be read in place.
 *   · THE `focus` ACTION IS A DOOR, NOT A DUPLICATE. It calls the SAME
 *     `setMilestone` the picker calls (`ChapterProps.onFocus`, threaded from
 *     `App.tsx` where the state lives). After it fires the picker and this pane
 *     agree because they ARE the same state. There is no pane-local selection.
 *
 * The expanded body is EXACTLY what the single-chapter pane draws — `Detail`
 * below is rendered by both paths, so the two cannot drift and the criteria
 * (which no other screen draws at all) cannot be lost from one of them.
 *
 * With ONE chapter open, or one in focus, this file renders what it always
 * rendered: no rows, no fold arrow, no accordion chrome. The common case must
 * not get louder because the uncommon one got useful. */
import { useState } from "react";
import { Pane, PaneEmpty, PaneRow, PaneTile } from "./Pane";
import { Ext, compareUrl } from "../../links";
import type { BoardRow, Milestone } from "../../types";
import type { ChapterProps } from "./panels";

type Repo = { host: string; slug: string; url: string } | null | undefined;

export function Chapter({ milestone, open, rows, repo, onFocus }: ChapterProps): React.JSX.Element {
  if (milestone !== null) {
    return (
      <Pane testId="pane-chapter">
        <div style={{ padding: "20px 20px 16px" }}>
          <div style={eyebrow}>Chapter in focus</div>
          <h2 style={title}>{milestone.title}</h2>
          <div style={goalText}>{milestone.goal}</div>
        </div>
        <Detail milestone={milestone} repo={repo} />
      </Pane>
    );
  }
  if (open.length > 1) {
    return <Several open={open} rows={rows} repo={repo} onFocus={onFocus} />;
  }
  /* Zero. (One open chapter never reaches here — `in_scope` focuses it.) */
  return (
    <Pane testId="pane-chapter">
      <div style={{ padding: "20px 20px 16px" }}>
        <div style={eyebrow}>Chapter in focus</div>
      </div>
      <PaneEmpty>
        No milestone is open. A chapter opens with <code>taskops_plan milestone=…</code>.
      </PaneEmpty>
    </Pane>
  );
}

/** The accordion. The fold is VIEW state and remembers nothing across reloads —
 *  it is not stored, not a URL, not a preference.
 *
 *  `null` means "nobody has folded anything yet", and then the FIRST chapter is
 *  the expanded one. That is deliberately not the same as seeding the state with
 *  `open[0].id`: the list is re-sent on every poll, and a seeded id would keep
 *  pointing at a chapter that may have landed between two of them, leaving every
 *  row collapsed with no explanation. Derived, the default follows the list. */
function Several({
  open,
  rows,
  repo,
  onFocus,
}: {
  open: readonly Milestone[];
  rows: readonly BoardRow[];
  repo: Repo;
  onFocus: ((id: string) => void) | undefined;
}): React.JSX.Element {
  const [folded, setFolded] = useState<string | null>(null);
  const counts = openCounts(rows);
  return (
    <Pane testId="pane-chapter">
      <div style={{ padding: "20px 20px 14px" }}>
        <div style={eyebrow}>Chapter in focus</div>
        <h2 style={title}>{open.length} chapters in flight</h2>
        <div style={goalText}>
          The board focuses one on its own only when a single chapter is open. Every one of
          them is here; focus one to narrow the whole dashboard to it.
        </div>
      </div>
      {open.map((m, i) => {
        const shown = folded === null ? i === 0 : folded === m.id;
        const n = counts?.get(m.id) ?? (counts === null ? null : 0);
        return (
          <div key={m.id} data-testid="chapter-row">
            <PaneRow
              pad="0"
              style={{ display: "flex", alignItems: "center", gap: "10px", paddingRight: "14px" }}
            >
              {/* A real button, not an arrow glyph: `aria-expanded` says what it
                  does and the keyboard reaches it. */}
              <button
                type="button"
                data-testid="chapter-fold"
                aria-expanded={shown}
                aria-controls={`chapter-body-${m.id}`}
                onClick={() => setFolded(shown ? "" : m.id)}
                style={foldButton}
              >
                <span className="mono" aria-hidden="true" style={arrow}>
                  {shown ? "▾" : "▸"}
                </span>
                <span style={rowTitle}>{m.title}</span>
              </button>
              {n === null ? null : (
                <span style={countText} data-testid="chapter-open-count">
                  {n} open
                </span>
              )}
              {onFocus === undefined ? null : (
                <button
                  type="button"
                  data-testid="chapter-focus"
                  onClick={() => onFocus(m.id)}
                  style={focusButton}
                >
                  focus
                </button>
              )}
            </PaneRow>
            {shown ? (
              <div id={`chapter-body-${m.id}`}>
                <div style={{ padding: "13px 20px 15px" }}>
                  <div style={goalText}>{m.goal}</div>
                </div>
                <Detail milestone={m} repo={repo} />
              </div>
            ) : null}
          </div>
        );
      })}
    </Pane>
  );
}

/** How many OPEN cards each chapter carries, folded from the rows the board
 *  already sends. `null` when NOT ONE row names a chapter — `BoardRow.milestone`
 *  is optional (types.ts), and on a payload that omits it every chapter would
 *  read `0 open`, which is a wrong number rather than a missing one. No count at
 *  all is the honest render; a total ("8 cards") is not derivable at any price,
 *  because `groups.done` is a capped tail. */
function openCounts(rows: readonly BoardRow[]): Map<string, number> | null {
  const counts = new Map<string, number>();
  for (const row of rows) {
    if (row.milestone) counts.set(row.milestone, (counts.get(row.milestone) ?? 0) + 1);
  }
  return counts.size === 0 ? null : counts;
}

/** Everything under the goal: the rules, the criteria, the integration branch.
 *  ONE component, rendered by the focused pane and by every expanded accordion
 *  row, so "the body is exactly what the pane draws today" is structural rather
 *  than a promise two blocks keep by hand. */
function Detail({ milestone, repo }: { milestone: Milestone; repo: Repo }): React.JSX.Element {
  /* `?? []` and not a non-null read: a board one version behind sends no
   * `criteria` key at all (types.ts::Milestone). Absent and empty are the same
   * fact here — no section. */
  const criteria = milestone.criteria ?? [];
  /* No base: the trunk is not on the board and the UI must not guess "main" —
   * the forge resolves its own default branch (`links.tsx`). */
  const chapterDiff = compareUrl(repo, milestone.branch);
  return (
    <>
      {milestone.rules.length > 0 ? (
        <NumberedList
          testId="chapter-rules"
          label="Rules — every card in this chapter"
          items={milestone.rules}
          background="var(--pane-2)"
          fontSize="13px"
          color="var(--text)"
        />
      ) : null}
      {criteria.length > 0 ? (
        <NumberedList
          testId="chapter-criteria"
          label="Accepted against — the chapter as a whole"
          items={criteria}
          background="var(--pane-3)"
          fontSize="12.5px"
          color="var(--text-2)"
        />
      ) : null}
      <PaneRow
        pad="14px 20px"
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span style={{ fontSize: "12px", color: "var(--text-3)" }}>Integration branch</span>
        {/* The chapter's whole diff, against the trunk. The branch NAME is the
            anchor rather than a second control beside it: the footer keeps its
            two-item shape, and with no slug it is the same mono text it always
            was — no icon, no underline, no extra row. */}
        <span className="mono" style={{ fontSize: "12px", color: "var(--accent)" }}>
          {chapterDiff === null ? (
            milestone.branch
          ) : (
            <Ext href={chapterDiff} title={`the trunk...${milestone.branch}`}>
              <span data-testid="chapter-compare">{milestone.branch} ↗</span>
            </Ext>
          )}
        </span>
      </PaneRow>
    </>
  );
}

/** One numbered list under the goal. The rules and the criteria are the same
 *  shape drawn at two weights — one component rather than two blocks, so the
 *  day the tile changes it changes for both. */
function NumberedList({
  testId,
  label,
  items,
  background,
  fontSize,
  color,
}: {
  testId: string;
  label: string;
  items: readonly string[];
  background: string;
  fontSize: string;
  color: string;
}): React.JSX.Element {
  return (
    <div
      data-testid={testId}
      style={{
        padding: "0 20px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "9px",
      }}
    >
      <div style={listLabel}>{label}</div>
      {items.map((item, i) => (
        <PaneTile
          key={item}
          pad="9px 12px"
          style={{ display: "flex", alignItems: "baseline", gap: "11px", background }}
        >
          <span
            className="mono"
            style={{ fontSize: "10.5px", color: "var(--faint)", flex: "none" }}
          >
            {i + 1}
          </span>
          <span style={{ fontSize, color, letterSpacing: "-0.015em" }}>{item}</span>
        </PaneTile>
      ))}
    </div>
  );
}

const listLabel: React.CSSProperties = {
  fontSize: "11px",
  color: "var(--text-3)",
  letterSpacing: "0.01em",
  marginBottom: "-1px",
};

const goalText: React.CSSProperties = {
  fontSize: "13.5px",
  color: "var(--text-2)",
  lineHeight: 1.55,
};

/** `all: unset` is the design's own button reset (Pane.tsx). The row grows to
 *  fill so the whole title strip is the hit area, not just the glyph. */
const foldButton: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "9px",
  flex: 1,
  minWidth: 0,
  padding: "12px 0 12px 20px",
};

const arrow: React.CSSProperties = {
  fontSize: "10px",
  color: "var(--text-3)",
  flex: "none",
};

const rowTitle: React.CSSProperties = {
  fontSize: "13.5px",
  fontWeight: 500,
  letterSpacing: "-0.02em",
  color: "var(--text)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const countText: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  flex: "none",
};

const focusButton: React.CSSProperties = {
  all: "unset",
  cursor: "pointer",
  flex: "none",
  fontSize: "11.5px",
  color: "var(--accent)",
  padding: "3px 8px",
  borderRadius: "7px",
  background: "var(--pane-2)",
};

const eyebrow: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--text-3)",
  marginBottom: "7px",
};

const title: React.CSSProperties = {
  margin: "0 0 8px",
  fontSize: "21px",
  fontWeight: 500,
  letterSpacing: "-0.035em",
};
