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
  /** The frame the PLAY waits for, and the way to take it back. Method syntax
   *  so `window` satisfies it as it is; absent (a harness with no frames), the
   *  PLAY runs at once and nothing is ever left hidden. */
  requestAnimationFrame?(fn: () => void): number;
  cancelAnimationFrame?(id: number): void;
}

export const REDUCED = "(prefers-reduced-motion: reduce)";

/** Consulted before every play. An environment with no `matchMedia` — the
 *  headless render, an ancient browser — animates: absent is not a preference,
 *  and defaulting to "reduce" would silently delete the feature for everyone
 *  the query cannot answer for. */
export function prefersReducedMotion(env: MotionEnv | undefined): boolean {
  return env?.matchMedia?.(REDUCED).matches === true;
}

/** What FLIP needs of a TILE: where its BOX is, and the three style properties
 *  it writes. A plain object satisfies it in the smoke harness — which is how
 *  the rules in `commit` below are pinned without a DOM, a rAF or a window —
 *  and `useFlip.ts::layout` wraps a real element into one.
 *
 *  `getBoundingClientRect` here means the LAYOUT rect: where the box is with
 *  every transform peeled off. The DOM's own method includes transforms, and
 *  writing transforms is FLIP's whole business — so measured raw, a tile that
 *  entered at `translateY(-6px)` read 6px short on the very next commit,
 *  `shifts` called that a move, the "mover" was put back by +6px, read 12px
 *  off on the commit after that, and so on down the cascade
 *  (2026-09-06: `translate(0, 6px)`, `translate(0, -12px)`, `-6.66px` mid-
 *  transition, `12.99px` …). The tile that entered hidden was thereafter
 *  played as a MOVER — transform cleared, opacity never — and the column
 *  said "Ready 7" over nothing. `peel` is the whole correction, and the
 *  element wrapper applies it before the pure half ever sees a number. */
export interface Tile {
  getBoundingClientRect(): Point;
  style: { transition: string; transform: string; opacity: string };
}

/** A browser rect, minus the translation of the transform currently on the
 *  element — the computed one, so a transition caught mid-flight is peeled
 *  by exactly as far as it has got. `matrix(a, b, c, d, e, f)` carries the
 *  translation in `e, f`; `matrix3d(…)` in its 13th and 14th numbers; `none`
 *  (and anything this cannot read) leaves the rect alone: the raw number is
 *  the honest fallback, never a guess at a shift. */
export function peel(rect: Point, transform: string): Point {
  const open = transform.indexOf("(");
  if (open < 0) return rect;
  const nums = transform
    .slice(open + 1, transform.lastIndexOf(")"))
    .split(",")
    .map((n) => Number(n.trim()));
  if (nums.some((n) => Number.isNaN(n))) return rect;
  let dx = 0;
  let dy = 0;
  if (transform.startsWith("matrix3d(") && nums.length === 16) {
    dx = nums[12] ?? 0;
    dy = nums[13] ?? 0;
  } else if (transform.startsWith("matrix(") && nums.length === 6) {
    dx = nums[4] ?? 0;
    dy = nums[5] ?? 0;
  } else {
    return rect;
  }
  return { left: rect.left - dx, top: rect.top - dy };
}

/** FIRST / LAST: where every tile is, by card id, as of this commit. */
export function measure(nodes: ReadonlyMap<string, Tile>): Map<string, Point> {
  const out = new Map<string, Point>();
  for (const [id, el] of nodes) {
    const box = el.getBoundingClientRect();
    out.set(id, { left: box.left, top: box.top });
  }
  return out;
}

/** INVERT: a mover is put back with a transform, a newcomer is hidden. Written
 *  with `transition: none` so the browser never animates the tile INTO its
 *  starting place; the caller writes these inside a layout effect, before the
 *  paint that would otherwise show the tile at its destination for a frame. */
export function invert(
  moved: readonly Shift[],
  fresh: readonly string[],
  nodes: ReadonlyMap<string, Tile>,
): void {
  for (const { id, dx, dy } of moved) {
    const el = nodes.get(id);
    if (!el) continue;
    el.style.transition = "none";
    el.style.transform = `translate(${dx}px, ${dy}px)`;
  }
  for (const id of fresh) {
    const el = nodes.get(id);
    if (!el) continue;
    el.style.transition = "none";
    el.style.opacity = "0";
    el.style.transform = "translateY(-6px)";
  }
}

/** PLAY: release everything INVERT wrote, under a transition. Idempotent, and
 *  it MUST be — `commit`'s cleanup calls it for a frame that will never fire
 *  and the frame, if it does fire, calls it again. No timer clears the
 *  transition afterwards: the next INVERT overwrites it, and a tile nobody
 *  moves keeps a transition it never fires. */
export function play(
  moved: readonly Shift[],
  fresh: readonly string[],
  nodes: ReadonlyMap<string, Tile>,
): void {
  for (const { id } of moved) {
    const el = nodes.get(id);
    if (!el) continue;
    el.style.transition = `transform ${DURATION}ms ${EASE}`;
    el.style.transform = "";
  }
  for (const id of fresh) {
    const el = nodes.get(id);
    if (!el) continue;
    el.style.transition = `opacity ${DURATION}ms ${EASE}, transform ${DURATION}ms ${EASE}`;
    el.style.opacity = "";
    el.style.transform = "";
  }
}

/** What one commit of the page leaves behind: the rects the NEXT commit
 *  compares against, and — when a play was scheduled — the cleanup React runs
 *  before that next commit. */
export interface Commit {
  after: Map<string, Point>;
  release?: () => void;
}

/** ONE COMMIT, start to finish: measure, compare with the last paint, INVERT
 *  now and PLAY on the next frame. `useFlip.ts` calls this from its layout
 *  effect and does nothing else, so everything the effect decides is decided
 *  here, over structural tiles, where the smoke harness can run it.
 *
 *  ABANDONED PLAYS ARE PLAYED, NOT DROPPED (2026-09-06). INVERT hides an
 *  entering tile at `opacity: 0` and PLAY, one frame later, lets it fade in.
 *  Between the two, React commits again: `useEvents.ts`'s effect answers every
 *  new board object with `setLoading(true)` before its fetch is even sent, and
 *  a passive effect runs in the task right after the paint — a whole frame
 *  before `requestAnimationFrame` fires. The old cleanup cancelled the frame
 *  and kept the styles, and the next commit's INVERT had nothing to say about
 *  those tiles: by then they were in `before`, so neither moved nor fresh. So
 *  every tile that entered with a chapter switch stayed at `opacity: 0` — the
 *  column's count said 7 and the column drew nothing — until a reload. The
 *  cleanup now RELEASES what it cancels: a frame that will not come is played
 *  synchronously, and the worst case is a tile that appears instead of fading.
 *  `ui/smoke/sections/board-flip-abandoned-play.tsx` pins it. */
export function commit(
  nodes: ReadonlyMap<string, Tile>,
  before: ReadonlyMap<string, Point>,
  env: MotionEnv | undefined,
): Commit {
  const after = measure(nodes);
  /* The FIRST commit has no "before", so nothing moved and nothing is new — a
   * whole board fading in on load is a page that looks broken, not alive. */
  if (before.size === 0) return { after };
  if (prefersReducedMotion(env)) return { after };
  const moved = shifts(before, after);
  const fresh = entering(before, after);
  if (moved.length === 0 && fresh.length === 0) return { after };

  invert(moved, fresh, nodes);
  /* The PLAY runs over the tiles AS THEY ARE NOW, not over `nodes` at the time
   * it fires: by the time React runs a layout effect's cleanup, the children's
   * refs are already detached — `ref(null)` comes off in the mutation phase,
   * before the parent's cleanup — so a release that looked the ids up in the
   * live map found nothing, and played nothing. The first fix of 2026-09-06
   * did exactly that, and the column stayed empty with the fix in. */
  const held = new Map(nodes);
  const release = (): void => play(moved, fresh, held);
  if (!env?.requestAnimationFrame) {
    release(); // no frame to wait for: nothing may stay hidden on its account
    return { after };
  }
  const frame = env.requestAnimationFrame(release);
  return {
    after,
    release: () => {
      env.cancelAnimationFrame?.(frame);
      release();
    },
  };
}
