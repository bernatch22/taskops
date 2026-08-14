/* The DOM half of FLIP. Everything that can be decided without a browser is in
 * `flip.ts` beside this and is tested there; what is left here is the part that
 * genuinely needs elements: hold a node per card id, measure, write two style
 * properties, and undo them.
 *
 * Self-contained ON PURPOSE — `Column` and `CardTile` stay presentational and
 * know nothing about motion. A tile that animated itself could only see itself,
 * and the whole question ("did this card change column?") is about the page. */
import { useEffect, useLayoutEffect, useRef } from "react";

import { DURATION, EASE, entering, prefersReducedMotion, shifts } from "./flip";
import type { MotionEnv, Point } from "./flip";

/** `useLayoutEffect` warns loudly under `react-dom/server`, and the smoke suite
 *  renders every page there. The effect is a no-op without a DOM anyway. */
const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export interface Flip {
  /** ref callback for a tile — `ref={flip.register(row.id)}` */
  register: (id: string) => (el: HTMLElement | null) => void;
}

/** Animate the tiles between two paints of this page.
 *
 *  `env` exists so the reduced-motion query is injectable exactly as
 *  `client.ts::subscribe`'s Env is; the default is the real window, and
 *  `undefined` under `react-dom/server`. */
export function useFlip(
  env: MotionEnv | undefined = typeof window === "undefined" ? undefined : window,
): Flip {
  const nodes = useRef(new Map<string, HTMLElement>());
  const previous = useRef(new Map<string, Point>());

  const register = (id: string) => (el: HTMLElement | null) => {
    if (el) nodes.current.set(id, el);
    else nodes.current.delete(id);
  };

  useIsomorphicLayoutEffect(() => {
    const after = new Map<string, Point>();
    for (const [id, el] of nodes.current) {
      const box = el.getBoundingClientRect();
      after.set(id, { left: box.left, top: box.top });
    }
    const before = previous.current;
    previous.current = after;

    /* The FIRST commit has no "before", so nothing moved and nothing is new —
     * a whole board fading in on load is a page that looks broken, not alive. */
    if (before.size === 0) return;
    if (prefersReducedMotion(env)) return;

    const moved = shifts(before, after);
    const fresh = entering(before, after);
    if (moved.length === 0 && fresh.length === 0) return;

    /* INVERT — written synchronously, inside the layout effect, so the browser
     * never paints the tile at its new place first. A transform written in the
     * rAF below would be one frame of teleport, which is the bug. */
    for (const { id, dx, dy } of moved) {
      const el = nodes.current.get(id);
      if (!el) continue;
      el.style.transition = "none";
      el.style.transform = `translate(${dx}px, ${dy}px)`;
    }
    for (const id of fresh) {
      const el = nodes.current.get(id);
      if (!el) continue;
      el.style.transition = "none";
      el.style.opacity = "0";
      el.style.transform = "translateY(-6px)";
    }

    /* PLAY — one frame later, the only scheduling in this file. No timer clears
     * the transition afterwards: the next commit's INVERT overwrites it, and a
     * tile nobody moves keeps a transition it never fires. */
    const frame = requestAnimationFrame(() => {
      for (const { id } of moved) {
        const el = nodes.current.get(id);
        if (!el) continue;
        el.style.transition = `transform ${DURATION}ms ${EASE}`;
        el.style.transform = "";
      }
      for (const id of fresh) {
        const el = nodes.current.get(id);
        if (!el) continue;
        el.style.transition = `opacity ${DURATION}ms ${EASE}, transform ${DURATION}ms ${EASE}`;
        el.style.opacity = "";
        el.style.transform = "";
      }
    });
    return () => cancelAnimationFrame(frame);
  });

  return { register };
}
