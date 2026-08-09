/* The chrome all eight Monitor sections share — lifted from Nova, not invented.
 *
 * Every `<section>` in Taskops Nova.dc.html lines 168-417 opens with the same four
 * declarations (`border-radius: 16px; background: var(--pane); border: 1px solid
 * var(--hair); overflow: hidden`) and every row inside one is drawn one of four
 * ways. This file is those five shapes, once, so that five workers building five
 * panels in five worktrees cannot each derive a slightly different hover.
 *
 * That is not a hypothetical: the last fan-out came back with
 * two `ago()` and three `initials()` — nobody
 * conflicted, and the tree was still wrong. The seam lands first, or it does not
 * land at all.
 *
 * Hover is `useState` + `onMouseEnter`, the same mechanism CardTile already uses:
 * the styles here are inline objects, and an inline object has no `:hover`. A
 * stylesheet rule would be a second place Nova's palette lives.
 *
 * The header PADDING is a prop with a default, because the design does not use
 * one value: `18px 20px 14px` on Live leases, Addressed to you and Event stream;
 * `18px 20px 6px` on Throughput; `18px 20px 4px` on Lease health; `18px 20px
 * 10px` on Dependency chain and Edit surface. Transcribing means carrying that
 * difference, not averaging it away. */
import { useState } from "react";

export interface PaneProps {
  /** The `h2`. Omitted on Chapter in focus, which draws its own eyebrow + 21px
   *  heading inside the body and has no `h2` header block in the design. */
  title?: string | undefined;
  /** The 12.5px line under the title. Verbatim from the design — never reworded. */
  subtitle?: string | undefined;
  /** The right-hand slot: the trailing note on Live leases and Event stream, the
   *  legend on Throughput, the "2 unanswered" pill on Addressed to you. */
  aside?: React.ReactNode;
  /** The header block's padding. Defaults to the most common of the five. */
  headPad?: string | undefined;
  /** `baseline` on Live leases, Throughput and Event stream; `center` on
   *  Addressed to you, whose aside is a pill. */
  headAlign?: "baseline" | "center" | undefined;
  children?: React.ReactNode;
  testId?: string | undefined;
}

const shell: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
};

const heading: React.CSSProperties = {
  margin: 0,
  fontSize: "16px",
  fontWeight: 500,
  letterSpacing: "-0.03em",
};

const sub: React.CSSProperties = {
  fontSize: "12.5px",
  color: "var(--text-3)",
  marginTop: "3px",
};

export function Pane(props: PaneProps): React.JSX.Element {
  const { title, subtitle, aside, headPad, headAlign, children, testId } =
    props;
  return (
    <section style={shell} data-testid={testId} data-pane={title}>
      {title !== undefined || aside ? (
        <div
          style={{
            display: "flex",
            alignItems: headAlign ?? "baseline",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
            padding: headPad ?? "18px 20px 14px",
          }}
        >
          <div>
            {title !== undefined ? <h2 style={heading}>{title}</h2> : null}
            {subtitle !== undefined ? <div style={sub}>{subtitle}</div> : null}
          </div>
          {aside}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/* ── the four row shapes ──────────────────────────────────────────────────── */

const bordered: React.CSSProperties = {
  boxSizing: "border-box",
  width: "100%",
  borderTop: "1px solid var(--hair)",
  transition: "background 130ms",
};

const tile: React.CSSProperties = {
  boxSizing: "border-box",
  width: "100%",
  borderRadius: "10px",
  transition: "background 130ms",
};

/** The cap every growing list wears, and the one deliberate departure from the
 *  design in this chapter.
 *
 *  Nova draws each list at mock scale — five files, nine chain rows — so only
 *  Event stream carries an explicit `max-height` in the .dc.html. On a real
 *  board these lists grow with the work: Edit surface came back 24 rows tall on
 *  a board with 7 open cards, which pushed everything under it off the screen
 *  and buried the two contended files it exists to warn about under 22 that
 *  claim nothing. A pane that has to be scrolled past is worse than one that
 *  scrolls.
 *
 *  Sized to show roughly six rows: enough that a quiet board never scrolls, and
 *  the panes keep the side-by-side proportions the grid was drawn for. The
 *  ordering inside each list already puts what matters on top, so what falls
 *  below the fold is the tail, never the warning. */
export const LIST_CAP: React.CSSProperties = {
  maxHeight: "352px",
  overflowY: "auto",
};

export interface PaneRowProps {
  children?: React.ReactNode;
  /** Defaults to the `14px 20px` of the Live leases row. */
  pad?: string | undefined;
  style?: React.CSSProperties | undefined;
}

/** A full-bleed block separated by a hairline: the Throughput totals strip, the
 *  Chapter footer. Not clickable — the design does not make these buttons. */
export function PaneRow({
  children,
  pad,
  style,
}: PaneRowProps): React.JSX.Element {
  return (
    <div style={{ ...bordered, padding: pad ?? "14px 20px", ...style }}>
      {children}
    </div>
  );
}

export interface PaneButtonProps extends PaneRowProps {
  cardId: string;
  onOpen: (id: string) => void;
  testId?: string | undefined;
}

/** A full-bleed hairline-separated row that opens the Dossier: the Live leases
 *  rows and the Addressed to you rows. `all: unset` on a button is the design's
 *  own reset, and the focus outline is inset so it is not clipped by the pane's
 *  `overflow: hidden`. */
export function PaneButton(props: PaneButtonProps): React.JSX.Element {
  const { children, pad, style, cardId, onOpen, testId } = props;
  const [hot, setHot] = useState(false);
  return (
    <button
      type="button"
      data-testid={testId}
      data-card={cardId}
      onClick={() => onOpen(cardId)}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      onFocus={() => setHot(true)}
      onBlur={() => setHot(false)}
      style={{
        all: "unset",
        ...bordered,
        cursor: "pointer",
        display: "block",
        padding: pad ?? "14px 20px",
        ...(hot ? { background: "var(--pane-2)" } : {}),
        ...style,
      }}
    >
      {children}
    </button>
  );
}

/** A radius-10 row inside a padded container, static: the Edit surface rows and
 *  the Chapter rules. `background` is the caller's — Edit surface tints a
 *  contended path, a rule sits on `var(--pane-2)`. */
export function PaneTile({
  children,
  pad,
  style,
}: PaneRowProps): React.JSX.Element {
  return (
    <div style={{ ...tile, padding: pad ?? "11px 10px", ...style }}>
      {children}
    </div>
  );
}

/** The same radius-10 row, clickable: the Dependency chain nodes. */
export function PaneTileButton(props: PaneButtonProps): React.JSX.Element {
  const { children, pad, style, cardId, onOpen, testId } = props;
  const [hot, setHot] = useState(false);
  return (
    <button
      type="button"
      data-testid={testId}
      data-card={cardId}
      onClick={() => onOpen(cardId)}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      onFocus={() => setHot(true)}
      onBlur={() => setHot(false)}
      style={{
        all: "unset",
        ...tile,
        cursor: "pointer",
        display: "block",
        padding: pad ?? "9px 10px",
        ...(hot ? { background: "var(--pane-2)" } : {}),
        ...style,
      }}
    >
      {children}
    </button>
  );
}

/** The body a stub draws until its panel card lands, and the body a real panel
 *  draws when its data is genuinely absent. Never a blank pane: a pane that
 *  renders nothing is indistinguishable from a pane somebody forgot. */
export function PaneEmpty({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div
      data-testid="pane-empty"
      style={{
        padding: "22px 20px 26px",
        borderTop: "1px solid var(--hair)",
        fontSize: "12.5px",
        color: "var(--text-3)",
        lineHeight: 1.6,
      }}
    >
      {children}
    </div>
  );
}
