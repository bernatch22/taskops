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
 * is the "pane somebody forgot" that `PaneEmpty` exists to prevent. */
import { Pane, PaneEmpty, PaneRow, PaneTile } from "./Pane";
import type { ChapterProps } from "./panels";

export function Chapter({ milestone, chapters }: ChapterProps): React.JSX.Element {
  if (milestone === null) {
    return (
      <Pane testId="pane-chapter">
        <div style={{ padding: "20px 20px 16px" }}>
          <div style={eyebrow}>Chapter in focus</div>
        </div>
        <PaneEmpty>
          {chapters > 1 ? (
            <>
              {chapters} chapters are open — the board focuses one on its own only when a
              single chapter is. Land or drop the finished ones, or read one with{" "}
              <code>taskops_board milestone=…</code>.
            </>
          ) : (
            <>
              No milestone is open. A chapter opens with <code>taskops_plan milestone=…</code>.
            </>
          )}
        </PaneEmpty>
      </Pane>
    );
  }
  /* `?? []` and not a non-null read: a board one version behind sends no
   * `criteria` key at all (types.ts::Milestone). Absent and empty are the same
   * fact here — no section. */
  const criteria = milestone.criteria ?? [];
  return (
    <Pane testId="pane-chapter">
      <div style={{ padding: "20px 20px 16px" }}>
        <div style={eyebrow}>Chapter in focus</div>
        <h2 style={title}>{milestone.title}</h2>
        <div style={{ fontSize: "13.5px", color: "var(--text-2)", lineHeight: 1.55 }}>
          {milestone.goal}
        </div>
      </div>
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
        <span className="mono" style={{ fontSize: "12px", color: "var(--accent)" }}>
          {milestone.branch}
        </span>
      </PaneRow>
    </Pane>
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
