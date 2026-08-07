/* A markdown reader, written here rather than installed.
 *
 * The bundle ships INSIDE the wheel — every kilobyte of dependency is a kilobyte
 * every `pip install taskops` pays for, forever, and a markdown library is a
 * hundred of them for a feature whose whole job is to make a spec readable. This
 * handles what a spec actually contains: headings, paragraphs, bold, code spans,
 * fenced code, tables and lists. Anything it does not know stays as text, which
 * is the correct failure for a renderer — markdown is readable already.
 *
 * It produces DATA, not HTML. `components/shared/Markdown.tsx` turns these blocks
 * into React elements, so nothing here ever reaches `dangerouslySetInnerHTML` and
 * a spec cannot inject markup by being written. That split is also why the parser
 * lives beside `format.ts` rather than inside the component: it is a pure
 * string → data function with no React in it, and it is testable as one.
 *
 * Ported from v1's `~/taskops/ui/src/markdown.ts`, minus the report-specific
 * narration split — v2's drawer renders specs and comments, not report files.
 *
 * One deliberate departure from CommonMark: an indented line does NOT become a
 * code block. A spec's indentation carries meaning (a bullet's continuation, a
 * tree drawing), and under the real rule half of every spec would render as grey
 * code. Paragraphs keep their line breaks instead — `whiteSpace: pre-wrap` in the
 * renderer — which is what the field looks like in the editor it was typed in. */

export interface Span {
  text: string;
  code?: boolean;
  bold?: boolean;
  italic?: boolean;
}

export type Block =
  | { kind: "heading"; level: number; spans: Span[] }
  | { kind: "para"; spans: Span[] }
  | { kind: "code"; text: string; lang: string }
  | { kind: "list"; ordered: boolean; items: Span[][] }
  | { kind: "table"; head: Span[][]; rows: Span[][][] }
  | { kind: "rule" };

export function parse(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  /* Reading past the end returns "" rather than `undefined`: every rule here has
   * to look at the next line (a table's divider, a fence's close), and a
   * lookahead that could be undefined would put a `??` on each one. */
  const at_ = (index: number): string => lines[index] ?? "";
  const blocks: Block[] = [];
  let at = 0;

  while (at < lines.length) {
    const trimmed = at_(at).trim();

    if (!trimmed || trimmed.startsWith("<!--")) {
      at += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const lang = trimmed.slice(3).trim();
      const body: string[] = [];
      at += 1;
      while (at < lines.length && !at_(at).trim().startsWith("```")) body.push(at_(at++));
      at += 1; // the closing fence, or the end of the file — an unclosed fence still renders
      blocks.push({ kind: "code", text: body.join("\n"), lang });
      continue;
    }

    if (/^#{1,6}\s/.test(trimmed)) {
      const hashes = (/^#+/.exec(trimmed)?.[0] ?? "#").length;
      blocks.push({ kind: "heading", level: hashes, spans: spansOf(trimmed.slice(hashes).trim()) });
      at += 1;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push({ kind: "rule" });
      at += 1;
      continue;
    }

    if (trimmed.startsWith("|") && isDivider(at_(at + 1))) {
      const head = cells(trimmed);
      const rows: Span[][][] = [];
      at += 2;
      while (at < lines.length && at_(at).trim().startsWith("|")) rows.push(cells(at_(at++)));
      blocks.push({ kind: "table", head, rows });
      continue;
    }

    const bullet = item(trimmed);
    if (bullet) {
      const items: Span[][] = [];
      const ordered = bullet.ordered;
      while (at < lines.length) {
        const next = item(at_(at).trim());
        /* Same list only while the marker keeps its kind: a numbered list under a
         * bulleted one is a second list, and merging them would renumber
         * somebody's steps. */
        if (!next || next.ordered !== ordered) break;
        items.push(spansOf(next.text));
        at += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }

    const paragraph: string[] = [];
    while (at < lines.length && at_(at).trim() && !isBreak(at_(at))) paragraph.push(at_(at++));
    if (paragraph.length === 0) {
      at += 1;
      continue;
    }
    blocks.push({ kind: "para", spans: spansOf(paragraph.join("\n")) });
  }

  return blocks;
}

function isBreak(line: string): boolean {
  const trimmed = line.trim();
  return (
    /^#{1,6}\s/.test(trimmed) ||
    trimmed.startsWith("```") ||
    trimmed.startsWith("|") ||
    trimmed.startsWith("<!--") ||
    item(trimmed) !== null ||
    /^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)
  );
}

function item(trimmed: string): { ordered: boolean; text: string } | null {
  const bullet = /^[-*+]\s+(.*)$/.exec(trimmed);
  if (bullet) return { ordered: false, text: bullet[1] ?? "" };
  const numbered = /^\d+[.)]\s+(.*)$/.exec(trimmed);
  return numbered ? { ordered: true, text: numbered[1] ?? "" } : null;
}

function isDivider(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && /^[|\s:-]+$/.test(trimmed) && trimmed.includes("-");
}

function cells(line: string): Span[][] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => spansOf(cell.trim()));
}

/* Inline: code first, and code wins.
 *
 * `**not bold**` inside backticks must stay literal — a spec quotes shell and
 * markdown at each other constantly, and a renderer that emphasised the inside of
 * a code span would be lying about what is on disk. So the string is cut on
 * backticks first and only the gaps are scanned. */
export function spansOf(text: string): Span[] {
  const out: Span[] = [];
  for (const piece of text.split(/(`[^`]+`)/g)) {
    if (!piece) continue;
    if (piece.startsWith("`") && piece.endsWith("`") && piece.length > 1) {
      out.push({ text: piece.slice(1, -1), code: true });
    } else {
      out.push(...emphasis(piece));
    }
  }
  return out.length > 0 ? out : [{ text }];
}

function emphasis(text: string): Span[] {
  const out: Span[] = [];
  for (const piece of text.split(/(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*)/g)) {
    if (!piece) continue;
    const strong =
      (piece.startsWith("**") && piece.endsWith("**")) ||
      (piece.startsWith("__") && piece.endsWith("__"));
    if (strong) {
      out.push({ text: piece.slice(2, -2), bold: true });
    } else if (piece.startsWith("*") && piece.endsWith("*") && piece.length > 2) {
      out.push({ text: piece.slice(1, -1), italic: true });
    } else {
      out.push({ text: piece });
    }
  }
  return out;
}
