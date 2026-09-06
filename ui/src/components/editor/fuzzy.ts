/* Fuzzy matching over paths, VS Code's shape and no dependency: a query is a
 * SUBSEQUENCE of the path, and the score says how good a subsequence it is —
 * consecutive characters, characters that open a path segment (after `/`,
 * `.`, `_`, `-`), characters inside the basename, all bonuses; a gap between
 * two matched characters, a penalty. Ties go to the shorter path.
 *
 * ONE definition of "matches" for the whole Editor: the quick-open palette
 * and the tree's inline filter both call `search()`, so a path that the
 * palette finds is a path the filter shows. Pure, no React, no clock —
 * `ui/smoke/sections/editor-page.tsx` pins the ORDER on hand-picked cases.
 *
 * FAST ENOUGH BY CONSTRUCTION. A path is short and a query shorter, so a
 * match is a few dozen character comparisons; four thousand paths is a
 * millisecond. The one thing that is NOT done is sorting everything: the
 * top N are kept in a bounded array as the listing is walked, so the cost is
 * O(paths × N) with N ≈ 50 and no allocation per miss. */

export interface Match {
  path: string;
  score: number;
  /** the matched characters' indexes into `path`, ascending */
  positions: number[];
}

const OPENS = "/._-";

const CONSECUTIVE = 8;
const SEGMENT = 6;
const BASENAME = 4;
const PREFIX = 10;
const GAP = 0.5;
const GAP_CAP = 5;

function opens(lower: string, at: number): boolean {
  return at === 0 || OPENS.includes(lower[at - 1]!);
}

/** The best subsequence of `query` in `path`, or null. Every occurrence of
 *  the first character is tried as a start — that is what finds `scan` inside
 *  `src/scan.py` as one run rather than `s`, `c` in `src` and the rest far
 *  away; from the start the walk is greedy and prefers, at each character, a
 *  consecutive position, else one that opens a segment, else the nearest. */
export function match(query: string, path: string): Match | null {
  const q = query.toLowerCase();
  if (!q) return { path, score: 0, positions: [] };
  const lower = path.toLowerCase();
  const base = path.lastIndexOf("/") + 1;
  let best: Match | null = null;
  for (let start = lower.indexOf(q[0]!); start >= 0; start = lower.indexOf(q[0]!, start + 1)) {
    const found = walk(q, lower, start, base);
    if (found && (!best || found.score > best.score)) best = { path, ...found };
  }
  if (best && lower.slice(base).startsWith(q)) best.score += PREFIX;
  return best;
}

function walk(q: string, lower: string, start: number, base: number): { score: number; positions: number[] } | null {
  const positions = [start];
  let score = gain(lower, start, -2, base);
  let prev = start;
  for (let i = 1; i < q.length; i += 1) {
    const c = q[i]!;
    let at = lower.indexOf(c, prev + 1);
    if (at < 0) return null;
    if (at !== prev + 1) {
      // not consecutive: a segment-opening occurrence beats the nearest one
      for (let k = at; k >= 0; k = lower.indexOf(c, k + 1)) {
        if (opens(lower, k)) {
          at = k;
          break;
        }
      }
    }
    score += gain(lower, at, prev, base);
    positions.push(at);
    prev = at;
  }
  return { score, positions };
}

function gain(lower: string, at: number, prev: number, base: number): number {
  let g = 1;
  if (at === prev + 1) g += CONSECUTIVE;
  if (opens(lower, at)) g += SEGMENT;
  if (at >= base) g += BASENAME;
  if (prev >= 0 && at > prev + 1) g -= Math.min(at - prev - 1, GAP_CAP) * GAP;
  return g;
}

/** Better first: score, then the shorter path, then the alphabet. */
export function before(a: Match, b: Match): boolean {
  if (a.score !== b.score) return a.score > b.score;
  if (a.path.length !== b.path.length) return a.path.length < b.path.length;
  return a.path < b.path;
}

/** The top `limit` matches of `query` over `paths`, in order. An empty query
 *  is the first `limit` paths as they come: the palette opened on nothing
 *  typed shows the tree, not a blank. */
export function search(paths: readonly string[], query: string, limit = 50): Match[] {
  if (!query.trim()) return paths.slice(0, limit).map((path) => ({ path, score: 0, positions: [] }));
  const top: Match[] = [];
  for (const path of paths) {
    const found = match(query.trim(), path);
    if (!found) continue;
    if (top.length === limit && !before(found, top[limit - 1]!)) continue;
    let i = top.length;
    while (i > 0 && before(found, top[i - 1]!)) i -= 1;
    top.splice(i, 0, found);
    if (top.length > limit) top.pop();
  }
  return top;
}
