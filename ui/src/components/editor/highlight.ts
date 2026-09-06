/* Syntax colour for the Editor, with NO dependency — a compact tokenizer, not
 * a grammar engine, and the trade is stated here so nobody re-makes it blind.
 *
 * WHAT WAS WEIGHED. highlight.js with the eleven grammars this page needs is
 * ~45 kB minified; Prism with the same set ~25 kB; shiki is a WASM engine and
 * out of the question for a bundle that ships React and nothing else. This
 * file is ~4 kB minified and knows exactly enough to make code READABLE — a
 * keyword, a string, a comment, a number, a tag, an attribute — which is what
 * a reader watching a worker's tree needs, and all a 13px mono pane can show.
 * It is not a parser: a regex literal in JavaScript is punctuation and text, a
 * template's `${…}` is part of its string, and a Python decorator is `@` and
 * a name. Every one of those reads fine; none of them is worth 40 kB.
 *
 * SHAPE. Two engines share one token vocabulary. `scan()` is a character
 * scanner driven by a per-language `Spec` — comments, quotes, keywords — and it
 * is what Python, the script family, JSON, TOML, SQL, bash and CSS run through.
 * The line-shaped languages (YAML, Markdown) are a list of sticky regexes per
 * line with one bit of state between lines (a fence). HTML is its own small
 * scanner because a tag's inside and outside are two different alphabets.
 *
 * OUTPUT is per LINE, always — `Token[][]`, one array per line of the input —
 * because the pane draws line numbers and gutter marks per line and a token
 * that spanned two rows would break both. A block comment or a triple-quoted
 * string that spans lines is split at each newline into a token per line, all
 * of the same kind. Pure, no React: `ui/smoke/sections/editor-page.tsx` pins
 * the rules here without a DOM. */

export type TokenKind = "keyword" | "string" | "comment" | "number" | "tag" | "attr" | "punct" | "text";

export interface Token {
  kind: TokenKind;
  text: string;
}

export type Language =
  | "python"
  | "script"
  | "json"
  | "yaml"
  | "toml"
  | "markdown"
  | "sql"
  | "bash"
  | "html"
  | "css"
  | "plain";

const BY_EXT: Record<string, Language> = {
  py: "python",
  pyi: "python",
  ts: "script",
  tsx: "script",
  js: "script",
  jsx: "script",
  mjs: "script",
  cjs: "script",
  json: "json",
  jsonc: "json",
  yml: "yaml",
  yaml: "yaml",
  toml: "toml",
  md: "markdown",
  markdown: "markdown",
  sql: "sql",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  html: "html",
  htm: "html",
  svg: "html",
  xml: "html",
  css: "css",
};

const BY_NAME: Record<string, Language> = {
  Dockerfile: "bash",
  Makefile: "bash",
  ".env": "bash",
  ".gitignore": "plain",
};

/** Which grammar a path gets, by its extension, else by its whole name, else
 *  plain — and plain is a real answer: every line is one `text` token. */
export function languageOf(path: string): Language {
  const name = path.split("/").pop() ?? path;
  const named = BY_NAME[name];
  if (named) return named;
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  return BY_EXT[ext] ?? "plain";
}

/* ── the character scanner ────────────────────────────────────────────────── */

interface Spec {
  /** line-comment openers, e.g. `#`, `//`, `--` */
  line: readonly string[];
  /** block-comment pairs */
  block: readonly (readonly [string, string])[];
  /** string delimiters, LONGEST FIRST so `"""` wins over `"` */
  quotes: readonly string[];
  /** the delimiters that may span lines */
  spanning: ReadonlySet<string>;
  keywords: ReadonlySet<string>;
  /** keywords compared upper-cased (SQL) */
  ci?: boolean;
  /** `$name` and `${name}` are attributes (bash) */
  vars?: boolean;
}

const words = (list: string): ReadonlySet<string> => new Set(list.split(" "));

const PYTHON: Spec = {
  line: ["#"],
  block: [],
  quotes: ['"""', "'''", '"', "'"],
  spanning: new Set(['"""', "'''"]),
  keywords: words(
    "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case self",
  ),
};

const SCRIPT: Spec = {
  line: ["//"],
  block: [["/*", "*/"]],
  quotes: ["`", '"', "'"],
  spanning: new Set(["`"]),
  keywords: words(
    "abstract as async await break case catch class const continue debugger declare default delete do else enum export extends false finally for from function if implements import in instanceof interface is keyof let namespace new null of override private protected public readonly return satisfies static super switch this throw true try type typeof undefined var void while with yield",
  ),
};

const JSON_SPEC: Spec = {
  line: [],
  block: [],
  quotes: ['"'],
  spanning: new Set(),
  keywords: words("true false null"),
};

const TOML: Spec = {
  line: ["#"],
  block: [],
  quotes: ['"""', "'''", '"', "'"],
  spanning: new Set(['"""', "'''"]),
  keywords: words("true false"),
};

const SQL: Spec = {
  line: ["--"],
  block: [["/*", "*/"]],
  quotes: ['"', "'"],
  spanning: new Set(),
  keywords: words(
    "SELECT FROM WHERE AND OR NOT IN IS NULL AS ON JOIN LEFT RIGHT INNER OUTER FULL CROSS GROUP BY ORDER HAVING LIMIT OFFSET INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE INDEX VIEW DROP ALTER ADD COLUMN PRIMARY KEY FOREIGN REFERENCES UNIQUE DEFAULT CHECK CONSTRAINT IF EXISTS BEGIN COMMIT ROLLBACK TRANSACTION WITH UNION ALL DISTINCT CASE WHEN THEN ELSE END LIKE BETWEEN ASC DESC TRUE FALSE INTEGER TEXT REAL BLOB VARCHAR BOOLEAN TIMESTAMP RETURNING",
  ),
  ci: true,
};

const BASH: Spec = {
  line: ["#"],
  block: [],
  quotes: ['"', "'"],
  spanning: new Set(['"', "'"]),
  keywords: words(
    "if then else elif fi for while until do done case esac in function return exit export local readonly set unset source alias echo cd ls rm cp mv mkdir test true false FROM RUN COPY ADD CMD ENTRYPOINT ENV ARG WORKDIR EXPOSE VOLUME USER LABEL",
  ),
  vars: true,
};

const PUNCT = "{}()[];,.:=<>+-*/%&|^!~?@";

function identStart(code: number): boolean {
  return (
    (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 95 || code === 36 || code > 127
  );
}

function identPart(code: number): boolean {
  return identStart(code) || (code >= 48 && code <= 57);
}

/** The scanner. One pass over the whole text; `emit` splits every token at
 *  its newlines so the output is per line by construction. */
function scan(text: string, spec: Spec): Token[][] {
  const lines: Token[][] = [[]];
  let current = lines[0]!;

  function emit(kind: TokenKind, chunk: string): void {
    const parts = chunk.split("\n");
    parts.forEach((part, i) => {
      if (i > 0) {
        current = [];
        lines.push(current);
      }
      if (part === "") return;
      const last = current[current.length - 1];
      if (last && last.kind === kind && (kind === "text" || kind === "punct")) last.text += part;
      else current.push({ kind, text: part });
    });
  }

  const n = text.length;
  let i = 0;
  while (i < n) {
    const ch = text[i]!;
    if (ch === "\n") {
      emit("text", "\n");
      i += 1;
      continue;
    }
    const block = spec.block.find(([open]) => text.startsWith(open, i));
    if (block) {
      const close = text.indexOf(block[1], i + block[0].length);
      const end = close < 0 ? n : close + block[1].length;
      emit("comment", text.slice(i, end));
      i = end;
      continue;
    }
    if (spec.line.some((open) => text.startsWith(open, i))) {
      let end = text.indexOf("\n", i);
      if (end < 0) end = n;
      emit("comment", text.slice(i, end));
      i = end;
      continue;
    }
    const quote = spec.quotes.find((q) => text.startsWith(q, i));
    if (quote) {
      const spans = spec.spanning.has(quote);
      let j = i + quote.length;
      while (j < n) {
        if (text[j] === "\\") {
          j += 2;
          continue;
        }
        if (text.startsWith(quote, j)) {
          j += quote.length;
          break;
        }
        if (text[j] === "\n" && !spans) break;
        j += 1;
      }
      emit("string", text.slice(i, Math.min(j, n)));
      i = Math.min(j, n);
      continue;
    }
    const code = ch.charCodeAt(0);
    if ((code >= 48 && code <= 57) || (ch === "." && /[0-9]/.test(text[i + 1] ?? ""))) {
      const found = /^(0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?|\.\d+)/.exec(
        text.slice(i, i + 64),
      );
      const number = found ? found[0] : ch;
      emit("number", number);
      i += number.length;
      continue;
    }
    // Before the identifier rule: `$` opens an identifier in the script
    // family, and bash's `$HOME` would otherwise scan as one plain word.
    if (spec.vars && ch === "$") {
      const found = /^\$(?:\{[^}\n]*\}|\w+|[@*#?$!-])/.exec(text.slice(i, i + 80));
      if (found) {
        emit("attr", found[0]);
        i += found[0].length;
        continue;
      }
    }
    if (identStart(code)) {
      let j = i + 1;
      while (j < n && identPart(text.charCodeAt(j))) j += 1;
      const word = text.slice(i, j);
      const known = spec.keywords.has(spec.ci ? word.toUpperCase() : word);
      emit(known ? "keyword" : "text", word);
      i = j;
      continue;
    }
    emit(PUNCT.includes(ch) ? "punct" : "text", ch);
    i += 1;
  }
  return lines;
}

/* ── the line-shaped languages ───────────────────────────────────────────── */

type Rule = readonly [RegExp, TokenKind];

/** One line through an ordered list of sticky rules; what no rule claims is
 *  text, one character at a time, coalesced. */
function byRules(line: string, rules: readonly Rule[]): Token[] {
  const out: Token[] = [];
  let i = 0;
  while (i < line.length) {
    let matched = false;
    for (const [re, kind] of rules) {
      re.lastIndex = i;
      const found = re.exec(line);
      if (found && found[0] !== "") {
        out.push({ kind, text: found[0] });
        i += found[0].length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      const last = out[out.length - 1];
      if (last && last.kind === "text") last.text += line[i];
      else out.push({ kind: "text", text: line[i]! });
      i += 1;
    }
  }
  return out;
}

const YAML_RULES: readonly Rule[] = [
  [/(?:^|(?<=\s))#.*$/y, "comment"],
  [/^\s*-(?=\s|$)/y, "punct"],
  [/^\s*(?:- )?[\w.\-/"']+(?=\s*:(?:\s|$))/y, "attr"],
  [/"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'/y, "string"],
  [/(?<![\w-])(?:true|false|null|yes|no|on|off|~)(?![\w-])/y, "keyword"],
  [/(?<![\w-])-?\d[\d_]*(?:\.\d+)?(?![\w-])/y, "number"],
  [/[&*][\w-]+/y, "tag"],
  [/[:|>\[\]{},]/y, "punct"],
];

const MARKDOWN_RULES: readonly Rule[] = [
  [/^#{1,6}\s.*$/y, "keyword"],
  [/^>.*$/y, "comment"],
  [/^\s*(?:[-*+]|\d+\.)\s/y, "punct"],
  [/`[^`]*`/y, "string"],
  [/\*\*[^*]+\*\*|__[^_]+__/y, "attr"],
  [/\[[^\]]*\]\([^)]*\)/y, "tag"],
];

const FENCE = /^\s*(```|~~~)/;

function byLines(text: string, rules: readonly Rule[], fenced: boolean): Token[][] {
  let inFence = false;
  return text.split("\n").map((line) => {
    if (fenced && FENCE.test(line)) {
      inFence = !inFence;
      return line ? [{ kind: "comment" as const, text: line }] : [];
    }
    if (inFence) return line ? [{ kind: "text" as const, text: line }] : [];
    return byRules(line, rules);
  });
}

/* ── html: two alphabets ─────────────────────────────────────────────────── */

const HTML_TEXT: readonly Rule[] = [
  [/<!--[\s\S]*?-->/y, "comment"],
  [/<!--[\s\S]*$/y, "comment"],
  [/<\/?[A-Za-z][\w:.-]*/y, "tag"],
];

const HTML_TAG: readonly Rule[] = [
  [/\/?>/y, "punct"],
  [/"[^"]*"|'[^']*'/y, "string"],
  [/=/y, "punct"],
  [/[^\s=/>"']+/y, "attr"],
];

function html(text: string): Token[][] {
  const lines: Token[][] = [];
  let inTag = false;
  for (const line of text.split("\n")) {
    const out: Token[] = [];
    let i = 0;
    while (i < line.length) {
      const rules = inTag ? HTML_TAG : HTML_TEXT;
      let matched: Token | null = null;
      for (const [re, kind] of rules) {
        re.lastIndex = i;
        const found = re.exec(line);
        if (found && found[0] !== "") {
          matched = { kind, text: found[0] };
          break;
        }
      }
      if (matched) {
        out.push(matched);
        i += matched.text.length;
        if (matched.kind === "tag") inTag = true;
        if (inTag && matched.kind === "punct" && matched.text.endsWith(">")) inTag = false;
        continue;
      }
      const last = out[out.length - 1];
      if (last && last.kind === "text") last.text += line[i];
      else out.push({ kind: "text", text: line[i]! });
      i += 1;
    }
    lines.push(out);
  }
  return lines;
}

/* ── css: selectors outside the braces, properties inside ────────────────── */

const CSS: Spec = {
  line: [],
  block: [["/*", "*/"]],
  quotes: ['"', "'"],
  spanning: new Set(),
  keywords: words("!important important"),
};

/** The scanner does the comments, strings and numbers; this pass turns the
 *  words into a selector (`tag`) outside braces and a property (`attr`)
 *  before the colon inside them — one state bit, carried across lines. */
const SELECTOR_PUNCT = ".#*>+~[]=";

function css(text: string): Token[][] {
  let depth = 0;
  let inValue = false;
  return scan(text, CSS).map((line) => {
    const out: Token[] = [];
    const push = (kind: TokenKind, piece: string): void => {
      const last = out[out.length - 1];
      if (last && last.kind === kind) last.text += piece;
      else out.push({ kind, text: piece });
    };
    for (const token of line) {
      if (token.kind !== "text" && token.kind !== "punct") {
        push(token.kind, token.text);
        continue;
      }
      // punctuation and text both arrive coalesced; decide per character or
      // per word, then let `push` merge what belongs together again
      const pieces = token.kind === "punct" ? [...token.text] : (token.text.match(/\s+|\S+/g) ?? []);
      for (const piece of pieces) {
        if (token.kind === "punct") {
          if (piece === "{") depth += 1;
          if (piece === "}") {
            depth = Math.max(0, depth - 1);
            inValue = false;
          }
          if (piece === ":" && depth > 0) inValue = true;
          if (piece === ";") inValue = false;
          push(depth === 0 && SELECTOR_PUNCT.includes(piece) ? "tag" : "punct", piece);
        } else if (piece.trim() === "") {
          push("text", piece);
        } else if (depth === 0) {
          push("tag", piece);
        } else {
          push(inValue ? "text" : "attr", piece);
        }
      }
    }
    return out;
  });
}

/* ── the door ────────────────────────────────────────────────────────────── */

export function tokenize(text: string, lang: Language): Token[][] {
  switch (lang) {
    case "python":
      return scan(text, PYTHON);
    case "script":
      return scan(text, SCRIPT);
    case "json":
      return scan(text, JSON_SPEC);
    case "toml":
      return scan(text, TOML);
    case "sql":
      return scan(text, SQL);
    case "bash":
      return scan(text, BASH);
    case "css":
      return css(text);
    case "yaml":
      return byLines(text, YAML_RULES, false);
    case "markdown":
      return byLines(text, MARKDOWN_RULES, true);
    case "html":
      return html(text);
    default:
      return text.split("\n").map((line) => (line ? [{ kind: "text", text: line }] : []));
  }
}
