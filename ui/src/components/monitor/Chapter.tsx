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
 * A milestone now also carries `criteria` (docs/fan-out.md §10), and Nova has NO
 * slot for it. It is deliberately NOT drawn here: the design predates the field,
 * and inventing a place for it is the substitution that cost the previous
 * chapter a full rollback. Raised on tk-60334f as a design question. */
import { Pane, PaneEmpty, PaneRow, PaneTile } from "./Pane";
import type { ChapterProps } from "./panels";

export function Chapter({ milestone }: ChapterProps): React.JSX.Element {
  if (milestone === null) {
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
        <div
          style={{
            padding: "0 20px 16px",
            display: "flex",
            flexDirection: "column",
            gap: "9px",
          }}
        >
          {milestone.rules.map((rule, i) => (
            <PaneTile
              key={rule}
              pad="9px 12px"
              style={{ display: "flex", alignItems: "baseline", gap: "11px", background: "var(--pane-2)" }}
            >
              <span
                className="mono"
                style={{ fontSize: "10.5px", color: "var(--faint)", flex: "none" }}
              >
                {i + 1}
              </span>
              <span style={{ fontSize: "13px", letterSpacing: "-0.015em" }}>{rule}</span>
            </PaneTile>
          ))}
        </div>
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
