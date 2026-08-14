/* FLIP — the board moves instead of teleporting.
 *
 * The feed delivers a change within a second and the page re-renders with the
 * card in another column, which is correct and reads as a SNAPSHOT: nothing on
 * screen connects where the tile was to where it is, so the eye has to re-find
 * it. The four letters are the whole technique and there is no library here:
 *
 *   First   the rects of every tile, by card id, as of the last paint
 *   Last    the rects after React committed the new payload
 *   Invert  put each moved tile back with a transform — visually nothing moved
 *   Play    one requestAnimationFrame later, drop the transform under a
 *           transition, and the browser animates the tile to where it now is
 *
 * WHY THE OLD RECTS ARE CACHED AND NOT MEASURED ON THE WAY IN. The obvious
 * shape — measure, then swap the payload — needs the swap to be something this
 * hook can sit in front of, and it is not: the payload arrives through
 * `useBoard`, several components up, and a refetch is not the only thing that
 * re-lays this page out. So the measurement is taken at the END of every commit
 * instead, which is the same numbers one moment later and costs nothing when
 * nothing moved. Layout between two commits does not change on its own.
 *
 * EXITS ARE NOT CHOREOGRAPHED. A card that left the payload is gone from the
 * DOM before this hook runs, and animating it out would mean keeping a tile
 * alive that the board no longer says exists — a second source of truth about
 * what is on the board, for a quarter of a second of decoration. It just goes.
 *
 * `prefers-reduced-motion` skips the PLAY, never the layout: the tile lands
 * where the payload puts it, instantly, which is exactly today's behaviour. */

/** What FLIP needs of a tile — the two numbers, so the pure half can be
 *  asserted on without a DOM. A `DOMRect` satisfies it structurally. */
export interface Point {
  left: number;
  top: number;
}

/** One tile that has to be put back before it can be played forward. */
export interface Shift {
  id: string;
  dx: number;
  dy: number;
}

/** Sub-pixel noise is not a move. A column's scrollbar appearing shifts every
 *  tile by a fraction; animating that is a board that twitches. */
export const EPSILON = 0.5;

/** THE INVERT, pure: given where the tiles were and where they now are, the
 *  transform each moved one needs to appear un-moved.
 *
 *  Only ids in BOTH maps are here. An id missing from `before` is a new card
 *  (it enters, and that is the tile's own business, not a displacement); one
 *  missing from `after` has left the DOM and there is nothing to transform. */
export function shifts(
  before: ReadonlyMap<string, Point>,
  after: ReadonlyMap<string, Point>,
  epsilon: number = EPSILON,
): Shift[] {
  const out: Shift[] = [];
  for (const [id, was] of before) {
    const now = after.get(id);
    if (!now) continue;
    const dx = was.left - now.left;
    const dy = was.top - now.top;
    if (Math.abs(dx) < epsilon && Math.abs(dy) < epsilon) continue;
    out.push({ id, dx, dy });
  }
  return out;
}

/** Which ids are on screen now and were not before — the tiles that ENTER.
 *  Pure for the same reason `shifts` is, and separate because the two answers
 *  are drawn differently: a mover is put back, a newcomer is faded up. */
export function entering(
  before: ReadonlyMap<string, Point>,
  after: ReadonlyMap<string, Point>,
): string[] {
  return [...after.keys()].filter((id) => !before.has(id));
}

/** How long a tile takes to cross, and on which curve — the tile's own hover
 *  easing (`CardTile.tsx`), because a board with two motion vocabularies reads
 *  as two boards. 220ms is long enough to follow across a 278px column gap and
 *  short enough that a burst of feed events does not queue up behind it. */
export const DURATION = 220;
export const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";

/** The one thing this hook asks of the environment, so a test can answer it.
 *
 *  `matchMedia` is the whole of it: the reduced-motion answer is a live media
 *  query and not a boolean read once at import: a reader who turns motion off
 *  mid-session must be obeyed on the very next refetch, not after a reload. */
export interface MotionEnv {
  matchMedia?: (query: string) => { matches: boolean };
}

export const REDUCED = "(prefers-reduced-motion: reduce)";

/** Consulted before every play. An environment with no `matchMedia` — the
 *  headless render, an ancient browser — animates: absent is not a preference,
 *  and defaulting to "reduce" would silently delete the feature for everyone
 *  the query cannot answer for. */
export function prefersReducedMotion(env: MotionEnv | undefined): boolean {
  return env?.matchMedia?.(REDUCED).matches === true;
}
