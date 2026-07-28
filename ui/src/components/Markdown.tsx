/* Blocks to elements. The other half of `markdown.ts`, kept apart from the parsing so the reader
 * is testable as a pure function of a string and this file is only ever about tags.
 *
 * Everything is a React element, never `dangerouslySetInnerHTML`: a report is a file on disk that
 * a model wrote into, and a renderer that pasted it as HTML would let a narration inject markup —
 * or a script — into the board of whoever reads it. */

import type { Block, Span } from "../markdown";
import { parse } from "../markdown";

export function Markdown({ source }: { source: string }): JSX.Element {
  return <div className="md">{parse(source).map(block)}</div>;
}

function block(item: Block, index: number): JSX.Element {
  switch (item.kind) {
    case "heading": {
      /* Headings inside a report are demoted by one: the view already owns an `h2` for the day, and
       * a document that brought its own `h1` would fight with it. */
      const Tag = (`h${Math.min(item.level + 1, 6)}`) as "h2";
      return <Tag key={index} className="md-h">{spans(item.spans)}</Tag>;
    }
    case "code":
      return <pre key={index} className="md-code" data-lang={item.lang}><code>{item.text}</code></pre>;
    case "rule":
      return <hr key={index} className="md-rule" />;
    case "list":
      return item.ordered
        ? <ol key={index} className="md-list">{item.items.map((it, at) => <li key={at}>{spans(it)}</li>)}</ol>
        : <ul key={index} className="md-list">{item.items.map((it, at) => <li key={at}>{spans(it)}</li>)}</ul>;
    case "table":
      return (
        <div key={index} className="md-table-wrap">
          <table className="md-table">
            <thead><tr>{item.head.map((cell, at) => <th key={at}>{spans(cell)}</th>)}</tr></thead>
            <tbody>
              {item.rows.map((row, at) => (
                <tr key={at}>{row.map((cell, cellAt) => <td key={cellAt}>{spans(cell)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    default:
      /* `pre-wrap` in the stylesheet, and that is load-bearing: the dossier's indentation is what
       * puts a commit under its card, and a paragraph that collapsed it would flatten the report
       * into a wall. */
      return <p key={index} className="md-p">{spans(item.spans)}</p>;
  }
}

function spans(list: Span[]): JSX.Element[] {
  return list.map((span, at) => {
    if (span.code) return <code key={at}>{span.text}</code>;
    if (span.bold) return <strong key={at}>{span.text}</strong>;
    if (span.italic) return <em key={at}>{span.text}</em>;
    return <span key={at}>{span.text}</span>;
  });
}
