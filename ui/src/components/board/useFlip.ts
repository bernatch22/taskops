/* The React half of FLIP: hold a node per card id, and run `flip.ts::commit`
 * after every paint of the page. Nothing is decided here — measuring,
 * comparing, INVERT, PLAY and what to do with a play that is abandoned all
 * live in `flip.ts`, over structural tiles, where the smoke harness can run
 * them without a browser. What is left is the part that genuinely needs React:
 * the refs, and the layout effect that hands them over.
 *
 * Self-contained ON PURPOSE — `Column` and `CardTile` stay presentational and
 * know nothing about motion. A tile that animated itself could only see itself,
 * and the whole question ("did this card change column?") is about the page. */
import { useEffect, useLayoutEffect, useRef } from "react";

import { commit, peel } from "./flip";
import type { MotionEnv, Point, Tile } from "./flip";

/** An element, as the pure half is allowed to see it: its style, and its
 *  LAYOUT rect — the DOM rect with the element's current computed transform
 *  peeled off (`flip.ts::Tile` carries the post-mortem: measured raw, FLIP's
 *  own transforms read as moves, and a tile that entered hidden stayed so).
 *  `getComputedStyle` rather than `el.style.transform` on purpose: mid-
 *  transition the inline value is already the destination, and only the
 *  computed one says where the box is being drawn right now. */
function layout(el: HTMLElement): Tile {
  return {
    style: el.style,
    getBoundingClientRect() {
      const box = el.getBoundingClientRect();
      return peel({ left: box.left, top: box.top }, getComputedStyle(el).transform);
    },
  };
}

/** `useLayoutEffect` warns loudly under `react-dom/server`, and the smoke suite
 *  renders every page there. The effect is a no-op without a DOM anyway. */
const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export interface Flip {
  /** ref callback for a tile — `ref={flip.register(row.id)}` */
  register: (id: string) => (el: HTMLElement | null) => void;
}

/** Animate the tiles between two paints of this page.
 *
 *  `env` exists so the reduced-motion query and the frame are injectable
 *  exactly as `client.ts::subscribe`'s Env is; the default is the real window,
 *  and `undefined` under `react-dom/server`. */
export function useFlip(
  env: MotionEnv | undefined = typeof window === "undefined" ? undefined : window,
): Flip {
  const nodes = useRef(new Map<string, Tile>());
  const previous = useRef(new Map<string, Point>());

  const register = (id: string) => (el: HTMLElement | null) => {
    if (el) nodes.current.set(id, layout(el));
    else nodes.current.delete(id);
  };

  /* No dependency list: the rects are taken at the END of every commit, which
   * is the same numbers as "before the next one" a moment earlier, and costs
   * nothing when nothing moved (`flip.ts` argues why they are cached rather
   * than measured on the way in). The cleanup React runs before the next
   * commit is `commit`'s own `release` — which is what keeps a play that the
   * next commit interrupts from leaving a tile hidden. */
  useIsomorphicLayoutEffect(() => {
    const step = commit(nodes.current, previous.current, env);
    previous.current = step.after;
    return step.release;
  });

  return { register };
}
