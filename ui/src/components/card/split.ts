/* A unified patch, folded into two columns — the whole of the thinking, with no
 * DOM in it.
 *
 * WHY A MODULE AND NOT A COMPONENT. Side-by-side is the one part of this screen
 * that can be WRONG rather than ugly: a line paired with the wrong line, a
 * counter that drifts, a hunk header misread. That is a function of a string,
 * so it is written as one — `react-dom/server` fires no effects and needs no
 * fixture to exercise this, and the harness asserts on the returned shape
 * instead of on markup (`ui/smoke/main.tsx`, and `Patch.tsx` only draws what
 * this returns).
 *
 * THE GRAMMAR IS `Patch.tsx::tone`'S AND NOTHING MORE. `@@ -a,b +c,d @@` opens a
 * hunk and gives both starting line numbers; ` ` is context (both sides, both
 * counters advance); `-` is left only; `+` is right only; `+++`/`---`/`diff `/
 * `index `/`new file`/`deleted file` are file headers and belong to no hunk.
 * Deliberately no second parser, no per-language anything: this file must agree
 * with `tone()` about what a line IS, and the way to guarantee that is to read
 * the same six prefixes.
 *
 * PAIRING IS POSITIONAL, NOT SEMANTIC. A run of `-` followed by a run of `+`
 * pairs first-with-first, and whichever run is longer leaves `null` opposite its
 * tail. That is what git's own side-by-side does, and the alternative — matching
 * by similarity — is a diff algorithm inside a diff viewer, i.e. a second
 * opinion about a patch git already computed.
 *
 * THE FALLBACK IS THE WHOLE SAFETY OF THIS FEATURE. Anything unparseable — a
 * hunk header that does not match, a body with no `@@` in it at all (a binary
 * note, a mode change, the cascade's own sentence) — returns `[]`, and the
 * caller draws the unified view it already had. An empty two-column table is
 * the one outcome this must never produce: it looks like "no changes" and means
 * "I did not understand". */

/** One side of a row: the line number in THAT file, and the text with its
 *  `+`/`-`/` ` marker removed — the column the line sits in carries the sign, so
 *  repeating it costs a character of width per line and says nothing new. */
export interface Side {
  n: number;
  text: string;
}

/** A row of the two-column table. `null` on a side means that side has no line
 *  here — a pure deletion, a pure addition, or the tail of the longer run of a
 *  replacement. Never `{text: ""}`: an empty string is a real blank line. */
export interface Row {
  left: Side | null;
  right: Side | null;
}

/** One `@@` hunk: its header verbatim (it is the reader's only anchor into the
 *  file's real line numbers) and its rows. */
export interface Hunk {
  header: string;
  rows: Row[];
}

/** The six prefixes that are FILE structure rather than content. Tested before
 *  `+`/`-`, exactly as `tone()` does, or `+++ b/x` reads as a one-line addition
 *  and `--- a/x` as a deletion — and both would then advance a counter. */
function isFileHeader(line: string): boolean {
  return (
    line.startsWith("+++") ||
    line.startsWith("---") ||
    line.startsWith("diff ") ||
    line.startsWith("index ") ||
    line.startsWith("new file") ||
    line.startsWith("deleted file")
  );
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

/** A run of deletions and the run of additions after it, laid side by side.
 *
 *  Positional: the first deletion beside the first addition, and the longer run
 *  keeps going with `null` opposite. A run of one kind only is the same code
 *  path with the other array empty, which is why there is no special case for
 *  "pure addition" anywhere below. */
function pair(dels: Side[], adds: Side[]): Row[] {
  const rows: Row[] = [];
  for (let i = 0; i < Math.max(dels.length, adds.length); i++) {
    rows.push({ left: dels[i] ?? null, right: adds[i] ?? null });
  }
  return rows;
}

/** Fold a unified patch into hunks of aligned rows, or `[]` if it is not one.
 *
 *  Pure, total, and it never throws: every branch either consumes a line or
 *  ignores it, and the only two answers are "hunks" and "I could not read
 *  this". */
export function split(patch: string): Hunk[] {
  const hunks: Hunk[] = [];
  let current: Hunk | null = null;
  let leftN = 0;
  let rightN = 0;
  let dels: Side[] = [];
  let adds: Side[] = [];

  /* A run ends at the first line that is neither `-` nor `+`, and at the end of
   * the hunk. Flushing is the ONLY place rows are appended for those two
   * prefixes, so a deletion can never be emitted before the addition that might
   * pair with it has been seen. */
  function flush(): void {
    if (!current || (dels.length === 0 && adds.length === 0)) return;
    current.rows.push(...pair(dels, adds));
    dels = [];
    adds = [];
  }

  for (const line of patch.split("\n")) {
    if (line.startsWith("@@")) {
      const at = HUNK.exec(line);
      // A `@@` this cannot read is a patch this cannot read. Not "skip the
      // hunk": the counters after it would be invented, and a table of invented
      // line numbers is worse than no table.
      if (!at) return [];
      flush();
      current = { header: line, rows: [] };
      hunks.push(current);
      leftN = Number(at[1]);
      rightN = Number(at[2]);
      continue;
    }
    if (isFileHeader(line)) {
      // Belongs to no hunk — and it ends the run before it, because the next
      // file's `@@` starts fresh counters.
      flush();
      continue;
    }
    // Before the first `@@` there is nothing to attach a line to. Reached by
    // every preamble git writes and by the empty string.
    if (!current) continue;
    // The empty string is not a line of the patch: git writes a blank context
    // line as `" "`, so `""` is only ever the tail `split("\n")` leaves after
    // the final newline. Counting it would push every hunk after it by one.
    if (line === "") continue;
    if (line.startsWith("-")) {
      dels.push({ n: leftN++, text: line.slice(1) });
      continue;
    }
    if (line.startsWith("+")) {
      adds.push({ n: rightN++, text: line.slice(1) });
      continue;
    }
    if (line.startsWith("\\")) {
      // `\ No newline at end of file` — a note about the line above, on
      // whichever side it followed. It is not a line of either file, so it
      // advances no counter and opens no row.
      continue;
    }
    // Context: ` ` in a real patch. Anything else unrecognised is read as
    // context rather than as a failure — being lenient here costs one row's
    // alignment, while returning `[]` would drop the whole file to unified.
    flush();
    current.rows.push({
      left: { n: leftN++, text: line.slice(1) },
      right: { n: rightN++, text: line.slice(1) },
    });
  }
  flush();
  // A hunk-less patch is not an empty diff, it is a body with no `@@` in it:
  // a binary note, a mode change, or one of the cascade's own sentences.
  return hunks.some((h) => h.rows.length > 0) ? hunks : [];
}
