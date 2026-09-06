/* The right pane: one file, read-only, as an editor draws it — line numbers,
 * syntax ink, a gutter mark on every line that moved since the base, and the
 * lines the disk just changed lit for a moment.
 *
 * READ-ONLY, absolutely. This page exists to watch a worker's tree move, and a
 * second writer into that directory would be the collision the board's whole
 * worktree design prevents. There is no `contentEditable` and no key handler.
 *
 * WRAPPING OFF. A line of code is arbitrarily long and folding it destroys
 * the indentation that makes it readable, so the pane scrolls on its own X
 * axis (`overflow: auto` over `white-space: pre`) and `min-width: 0` on every
 * ancestor keeps it inside the page — the same rule `card/Patch.tsx` states.
 * Scroll position survives a re-read because the rows are re-rendered in
 * place, never remounted: the container's key is the file's path.
 *
 * THE FLASH keys a row on the change's timestamp, so a second change restarts
 * the animation; `prefers-reduced-motion` skips it and keeps the content.
 *
 * DIFF VS BASE reuses `PatchText` — the very renderer the Worktrees page draws
 * a file's patch with — on the patch the door answers for the working copy.
 * One renderer, one vocabulary (`truncated` + `cap`), nothing new to read. */
import { useMemo } from "react";

import { TONE_FG } from "../board/CardTile";
import { prefersReducedMotion } from "../board/flip";
import { PatchText } from "../card/Patch";
import type { EditorDiff, EditorFile, MarkKind } from "../../types";
import { tokenize, type Language, type TokenKind } from "./highlight";
import { markMap } from "./tree";

export interface Flash {
  from: number;
  to: number;
  /** when it happened — the row's key, so a later change lights again */
  at: number;
}

export interface DiffState {
  on: boolean;
  patch: EditorDiff | null;
  loading: boolean;
  refusal: string | null;
}

export interface CodeViewProps {
  file: EditorFile;
  lang: Language;
  flash: Flash | null;
  diff: DiffState;
}

/** Syntax ink by token kind — the six `--code-*` tokens and the hairline for
 *  punctuation; plain text inherits the pane's ink and gets no span. */
export const TOKEN_INK: Record<TokenKind, string | null> = {
  keyword: "var(--code-keyword)",
  string: "var(--code-string)",
  comment: "var(--code-comment)",
  number: "var(--code-number)",
  tag: "var(--code-tag)",
  attr: "var(--code-attr)",
  punct: "var(--text-3)",
  text: null,
};

/** The gutter's status pair, `links.tsx`'s rule: added and changed are
 *  `--ok`/`--warn`, and a deletion after a line is `--danger`. */
export const MARK_INK: Record<MarkKind, string> = {
  added: TONE_FG.ok,
  modified: TONE_FG.warn,
  deleted: TONE_FG.danger,
};

const pane: React.CSSProperties = {
  // basis 0, not auto: the pane is the one thing in its column that absorbs
  // the height, so the strip and the meta line above it keep theirs whole.
  flex: "1 1 0px",
  minHeight: 0,
  minWidth: 0,
  overflow: "auto",
  whiteSpace: "pre",
  fontSize: "12.5px",
  lineHeight: 1.6,
  background: "var(--term)",
  color: "var(--term-text)",
  padding: "8px 0 24px",
};

const note: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--text-3)",
  padding: "10px 14px",
  lineHeight: 1.55,
};

const number: React.CSSProperties = {
  display: "inline-block",
  width: "3.2em",
  paddingRight: "12px",
  textAlign: "right",
  color: "var(--term-dim)",
  userSelect: "none",
  flex: "none",
};

export function CodeView({ file, lang, flash, diff }: CodeViewProps): React.JSX.Element {
  if (file.binary) {
    return (
      <div data-testid="editor-binary" style={note}>
        binary, {file.size.toLocaleString()} bytes — nothing here to read as text
      </div>
    );
  }
  return (
    <>
      {file.truncated ? (
        <div data-testid="editor-capped" style={{ ...note, color: "var(--warn)" }}>
          cut at {file.cap.toLocaleString()} bytes — this is the head of the file, not all of
          it ({file.size.toLocaleString()} bytes on disk)
        </div>
      ) : null}
      {diff.on ? <Diff diff={diff} file={file} /> : <Code file={file} lang={lang} flash={flash} />}
    </>
  );
}

function Diff({ diff, file }: { diff: DiffState; file: EditorFile }): React.JSX.Element {
  if (diff.loading && !diff.patch) {
    return (
      <div data-testid="editor-diff-loading" style={note}>
        reading the diff from this host…
      </div>
    );
  }
  if (diff.refusal) {
    return (
      <div data-testid="editor-diff-none" style={note}>
        {diff.refusal}
      </div>
    );
  }
  if (!diff.patch || !diff.patch.patch.trim()) {
    return (
      <div data-testid="editor-diff-empty" style={note}>
        no difference against {file.base?.ref ?? "the base"} — this file reads exactly as the
        base has it
      </div>
    );
  }
  return (
    <div data-testid="editor-diff" style={{ flex: "1 1 0px", minHeight: 0, overflow: "auto", padding: "0 0 24px" }}>
      {diff.patch.truncated ? (
        <div data-testid="editor-diff-truncated" style={{ ...note, color: "var(--warn)" }}>
          truncated at {diff.patch.cap.toLocaleString()} bytes — this is the head of the diff,
          not all of it
        </div>
      ) : null}
      <PatchText text={diff.patch.patch} view={{ size: "page", mode: "unified" }} />
    </div>
  );
}

function Code({ file, lang, flash }: { file: EditorFile; lang: Language; flash: Flash | null }): React.JSX.Element {
  const lines = useMemo(() => tokenize(file.text, lang), [file.text, lang]);
  const marks = useMemo(() => markMap(file.marks), [file.marks]);
  // A file ending in a newline has no empty last line, as git counts it.
  const drawn = lines.length > 1 && lines[lines.length - 1]!.length === 0 ? lines.slice(0, -1) : lines;
  const still = prefersReducedMotion(typeof window === "undefined" ? undefined : window);
  return (
    <div data-testid="editor-code" data-lang={lang} className="mono" style={pane}>
      {drawn.map((tokens, i) => {
        const n = i + 1;
        const mark = marks.get(n);
        const lit = flash !== null && n >= flash.from && n <= flash.to;
        return (
          <div
            key={lit ? `${n}@${flash.at}` : n}
            data-testid="editor-line"
            data-n={n}
            data-mark={mark}
            data-flash={lit ? "true" : undefined}
            style={{
              display: "flex",
              alignItems: "stretch",
              minWidth: "max-content",
              paddingRight: "24px",
              animation: lit && !still ? "tk-flash 1600ms ease-out" : undefined,
            }}
          >
            <span
              data-testid="editor-mark"
              aria-label={mark}
              style={{ width: "3px", flex: "none", background: mark ? MARK_INK[mark] : "transparent" }}
            />
            <span style={number}>{n}</span>
            <span>
              {tokens.map((t, k) => {
                const ink = TOKEN_INK[t.kind];
                return ink ? (
                  <span key={k} data-tok={t.kind} style={{ color: ink }}>
                    {t.text}
                  </span>
                ) : (
                  t.text
                );
              })}
            </span>
          </div>
        );
      })}
    </div>
  );
}
