/* Markdown → React elements. Never `dangerouslySetInnerHTML`.
 *
 * That is not a style preference, it is the whole security posture of this page:
 * a spec, a comment and a released note are written by whoever holds the card,
 * and one of them containing `<img onerror=…>` must render as those characters.
 * React escapes every string it is handed, so building elements is the escaping —
 * there is no sanitiser to keep up to date and no allowlist to get wrong.
 *
 * The parse is in `ui/src/markdown.ts` (pure, no React); this file only decides
 * what each block LOOKS like, in tokens. Splitting them that way is what lets the
 * parser be exercised without a DOM.
 *
 * `useMemo` on the parse because a spec is re-rendered on every feed poke (~one
 * refetch per event on a busy board) and the text almost never changes. */
import { useMemo } from "react";

import { parse, spansOf, type Block, type Span } from "../../markdown";

/* The family comes from the `.mono` class in tokens.css — the one place a font
 * stack is written down. Only the size and the colour are decided here. */
const code: React.CSSProperties = {
  fontSize: "0.9em",
  color: "var(--accent)",
  background: "var(--pane-3)",
  borderRadius: "5px",
  padding: "1px 5px",
};

const block: React.CSSProperties = {
  margin: 0,
  padding: "12px 14px",
  borderRadius: "11px",
  background: "var(--pane-3)",
  overflowX: "auto",
  fontSize: "12.5px",
  lineHeight: 1.55,
};

const cell: React.CSSProperties = {
  textAlign: "left",
  padding: "7px 12px",
  borderBottom: "1px solid var(--hair)",
  fontSize: "13px",
  fontWeight: 400,
  verticalAlign: "top",
};

/** `@name` drawn as an address rather than as text.
 *
 *  It lives HERE, not in the thread, because it is an inline decoration of plain
 *  text and that is what `Spans` is — and because a comment is markdown too: an
 *  agent quoting `taskops_update task=… mentions=[…]` wants the backticks read
 *  and the address highlighted, and two renderers could only give it one.
 *
 *  Split on the actor grammar's own alphabet (`dev:berna`, `agent:berna/w1`) so
 *  the colon and the slash stay INSIDE the highlight — "@agent" followed by grey
 *  ":berna/w1" would name the role, which is nobody. Never applied to a code
 *  span: inside backticks an `@` is a character. */
export function Mentioned({ text }: { text: string }): React.JSX.Element {
  return (
    <>
      {text.split(/(@[A-Za-z0-9][A-Za-z0-9_.:/-]*)/g).map((piece, i) =>
        piece.startsWith("@") ? (
          <span
            key={i}
            className="mono"
            data-testid="mention"
            style={{
              color: "var(--accent)",
              background: "var(--accent-soft)",
              borderRadius: "5px",
              padding: "1px 5px",
            }}
          >
            {piece}
          </span>
        ) : (
          <span key={i}>{piece}</span>
        ),
      )}
    </>
  );
}

function Spans({ spans }: { spans: Span[] }): React.JSX.Element {
  return (
    <>
      {spans.map((span, i) => {
        if (span.code) {
          return (
            <code key={i} className="mono" style={code}>
              {span.text}
            </code>
          );
        }
        if (span.bold) {
          return (
            <strong key={i} style={{ fontWeight: 600, color: "var(--text)" }}>
              {span.text}
            </strong>
          );
        }
        if (span.italic) return <em key={i}>{span.text}</em>;
        return <Mentioned key={i} text={span.text} />;
      })}
    </>
  );
}

function One({ block: b }: { block: Block }): React.JSX.Element | null {
  switch (b.kind) {
    case "heading":
      return (
        <div
          style={{
            fontSize: b.level <= 2 ? "15px" : "13.5px",
            fontWeight: 500,
            letterSpacing: "-0.02em",
            color: "var(--text)",
            marginTop: "4px",
          }}
        >
          <Spans spans={b.spans} />
        </div>
      );
    case "para":
      /* pre-wrap, not a <br> pass: the source's own line breaks ARE the shape of
       * a spec, and re-flowing them loses the author's paragraphing. */
      return (
        <p style={{ margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.65 }}>
          <Spans spans={b.spans} />
        </p>
      );
    case "code":
      return (
        <pre className="mono" style={block}>
          {b.text}
        </pre>
      );
    case "list":
      return b.ordered ? (
        <ol style={{ margin: 0, paddingLeft: "22px", lineHeight: 1.65 }}>
          {b.items.map((spans, i) => (
            <li key={i}>
              <Spans spans={spans} />
            </li>
          ))}
        </ol>
      ) : (
        <ul style={{ margin: 0, paddingLeft: "22px", lineHeight: 1.65 }}>
          {b.items.map((spans, i) => (
            <li key={i}>
              <Spans spans={spans} />
            </li>
          ))}
        </ul>
      );
    case "table":
      return (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                {b.head.map((spans, i) => (
                  <th key={i} style={{ ...cell, color: "var(--text-3)", fontSize: "11.5px" }}>
                    <Spans spans={spans} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((spans, c) => (
                    <td key={c} style={cell}>
                      <Spans spans={spans} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "rule":
      return <hr style={{ border: 0, borderTop: "1px solid var(--hair)", margin: "2px 0" }} />;
  }
}

/** The SAME renderer, one mode down: spans only, no block wrapper at all.
 *
 *  A chapter's rule and a card's criterion are prose too — axion's nine rules
 *  carry `code` in every one of them — but they are drawn INSIDE a layout that
 *  already owns their shape: a numbered tile whose mono index is a sibling of
 *  the text, baseline-aligned. Handed the block renderer, each one becomes a
 *  flex column of `<p>`s, the baseline moves off the number, and a rule that
 *  happens to start `1. ` or `- ` becomes a LIST — a second numbering beside
 *  the one the tile draws. All three are the numbering breaking.
 *
 *  So `inline` exists on THIS component rather than in a second one: same
 *  parser (`spansOf`, the inline half of `markdown.ts`), same `Spans`, same
 *  code/bold/italic/mention decisions. Nothing block-level renders — a heading
 *  or a fence inside a one-line rule stays the characters it was typed as,
 *  which is the correct failure for a field whose whole contract is one line.
 *
 *  It is additive: `<Markdown text=…>` with no prop is byte-for-byte the
 *  element tree it always produced, which is what keeps a spec and a comment
 *  unmoved. */
export function Markdown({
  text,
  inline,
}: {
  text: string;
  inline?: boolean;
}): React.JSX.Element {
  const blocks = useMemo(() => (inline === true ? [] : parse(text)), [text, inline]);
  const spans = useMemo(() => (inline === true ? spansOf(text) : []), [text, inline]);
  if (inline === true) {
    return (
      <span data-testid="markdown-inline">
        <Spans spans={spans} />
      </span>
    );
  }
  return (
    <div
      data-testid="markdown"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "11px",
        fontSize: "14.5px",
        color: "var(--text)",
        letterSpacing: "-0.015em",
      }}
    >
      {blocks.map((b, i) => (
        <One key={i} block={b} />
      ))}
    </div>
  );
}
