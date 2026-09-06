/* FLIP releases a play it abandons — the chapter switch that drew "Ready 7"
 * over an empty column.
 *
 * `react-dom/server` runs no layout effect and has no frame, so the hook
 * itself is out of reach here; what is reachable is the WHOLE step the hook's
 * effect runs (`flip.ts::commit`), over tiles that are plain objects and a
 * frame that is an array. The scenario below is the one that shipped broken
 * (2026-09-06): a chapter switch enters every tile at once, and a second
 * commit — `useEvents.ts` setting `loading` on the new board — lands before
 * the frame the PLAY was waiting for. React runs the first commit's cleanup,
 * then the second commit, which sees nothing fresh. Whatever the cleanup
 * leaves on the tiles is what the reader sees until a reload. */
import { commit, invert, peel, play, shifts } from "../../src/components/board/flip";
import type { MotionEnv, Point, Tile } from "../../src/components/board/flip";
import type { Check, Fixture, Harness } from "./section";

interface Fake extends Tile {
  at: Point;
}

function tile(left: number, top: number): Fake {
  return {
    at: { left, top },
    getBoundingClientRect() {
      return this.at;
    },
    style: { transition: "", transform: "", opacity: "" },
  };
}

/** A frame that fires only when the test says so — `pending` holds every
 *  scheduled play by handle, a cancelled one is blanked rather than removed so
 *  the handles stay stable exactly as a browser's do, and `cancelled` counts
 *  the take-backs. */
function frames(): {
  env: MotionEnv;
  pending: Array<() => void>;
  cancelled: number[];
  fire: () => void;
} {
  const pending: Array<() => void> = [];
  const cancelled: number[] = [];
  return {
    pending,
    cancelled,
    fire: () => {
      const due = pending.splice(0);
      for (const fn of due) fn();
    },
    env: {
      matchMedia: () => ({ matches: false }),
      requestAnimationFrame: (fn) => pending.push(fn),
      cancelAnimationFrame: (id) => {
        cancelled.push(id);
        pending[id - 1] = () => {};
      },
    },
  };
}

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* ── The primitives, on their own ────────────────────────────────────── */

  const a = tile(0, 0);
  const b = tile(0, 100);
  const nodes = new Map<string, Tile>([
    ["tk-a", a],
    ["tk-b", b],
  ]);
  const moved = shifts(new Map([["tk-a", { left: 300, top: 40 }]]), new Map([["tk-a", a.at]]));
  invert(moved, ["tk-b"], nodes);
  check(
    "INVERT puts a mover back and hides a newcomer, both without a transition",
    a.style.transform === "translate(300px, 40px)" &&
      a.style.transition === "none" &&
      b.style.opacity === "0" &&
      b.style.transition === "none",
    JSON.stringify([a.style, b.style]),
  );
  play(moved, ["tk-b"], nodes);
  check(
    "PLAY releases both under a transition — nothing INVERT wrote survives it",
    a.style.transform === "" &&
      b.style.opacity === "" &&
      b.style.transform === "" &&
      a.style.transition.startsWith("transform ") &&
      b.style.transition.startsWith("opacity "),
    JSON.stringify([a.style, b.style]),
  );
  play(moved, ["tk-b"], nodes);
  check(
    "PLAY is idempotent — the cleanup and the frame may both run it",
    a.style.transform === "" && b.style.opacity === "",
  );

  /* ── The commit that shipped broken ──────────────────────────────────── */

  const clock = frames();
  const old = new Map<string, Tile>([
    ["tk-old1", tile(0, 0)],
    ["tk-old2", tile(0, 100)],
  ]);
  const first = commit(old, new Map(), clock.env);
  check(
    "the first paint schedules no play — a whole board fading in on load looks broken",
    first.release === undefined && clock.pending.length === 0 && first.after.size === 2,
  );

  // The chapter switch: every tile on screen is new.
  const c = tile(0, 0);
  const d = tile(0, 100);
  const switched = new Map<string, Tile>([
    ["tk-c", c],
    ["tk-d", d],
  ]);
  const second = commit(switched, first.after, clock.env);
  check(
    "a switch enters every tile hidden, with one play waiting for the frame",
    c.style.opacity === "0" && d.style.opacity === "0" && clock.pending.length === 1,
    JSON.stringify([c.style, d.style, clock.pending.length]),
  );

  // `useEvents` commits again BEFORE the frame. React's order, exactly: the
  // children's refs come off (`ref(null)`, mutation phase) — the map is EMPTY
  // — then the parent's cleanup runs, then the refs go back on and the next
  // step runs, finding nothing moved and nothing fresh.
  const detached = new Map(switched);
  switched.clear();
  second.release?.();
  for (const [id, el] of detached) switched.set(id, el);
  const third = commit(switched, second.after, clock.env);
  check(
    "a play the next commit interrupts is RELEASED, not dropped — no tile stays at opacity 0",
    c.style.opacity === "" && d.style.opacity === "" && c.style.transform === "",
    JSON.stringify([c.style, d.style]),
  );
  check(
    "the interrupted frame was cancelled, and the quiet commit scheduled none of its own",
    third.release === undefined && clock.cancelled.length === 1 && clock.pending.length === 1,
    JSON.stringify({ cancelled: clock.cancelled, pending: clock.pending.length }),
  );
  clock.fire();
  check(
    "firing whatever the browser still holds changes nothing",
    c.style.opacity === "" && d.style.opacity === "",
  );

  /* ── A mover, interrupted the same way ────────────────────────────────── */

  const m = tile(0, 0);
  const one = new Map<string, Tile>([["tk-m", m]]);
  const settled = commit(one, new Map(), clock.env);
  m.at = { left: 300, top: 40 };
  const jumped = commit(one, settled.after, clock.env);
  const heldBack = m.style.transform;
  jumped.release?.();
  check(
    "a mover interrupted mid-play lands where the payload put it, not where it was",
    heldBack === "translate(-300px, -40px)" && m.style.transform === "",
    JSON.stringify({ heldBack, now: m.style }),
  );

  /* ── The rect the pure half is handed is the LAYOUT rect ──────────────── */

  check(
    "peel takes a 2D matrix's translation off a rect",
    JSON.stringify(peel({ left: 100, top: 50 }, "matrix(1, 0, 0, 1, 0, -6)")) ===
      JSON.stringify({ left: 100, top: 56 }),
  );
  check(
    "and a 3D matrix's",
    JSON.stringify(peel({ left: 100, top: 50 }, "matrix3d(1,0,0,0, 0,1,0,0, 0,0,1,0, 300,40,0,1)")) ===
      JSON.stringify({ left: -200, top: 10 }),
  );
  check(
    "`none`, and anything it cannot read, leaves the rect alone — a raw number, never a guessed shift",
    JSON.stringify(peel({ left: 7, top: 9 }, "none")) === JSON.stringify({ left: 7, top: 9 }) &&
      JSON.stringify(peel({ left: 7, top: 9 }, "matrix(1, x)")) === JSON.stringify({ left: 7, top: 9 }) &&
      JSON.stringify(peel({ left: 7, top: 9 }, "rotate(3deg)")) === JSON.stringify({ left: 7, top: 9 }),
  );

  /* The cascade, reproduced with a tile that reports its rect the way the DOM
   * does — transform INCLUDED — and the same tile reporting its layout rect the
   * way `useFlip.ts::layout` makes it. Same commits, opposite outcomes. */
  const translated = (s: string): Point => {
    const got = /translate(?:Y)?\(([^)]*)\)/.exec(s);
    if (!got?.[1]) return { left: 0, top: 0 };
    const parts = got[1].split(",").map((n) => parseFloat(n));
    return s.startsWith("translateY")
      ? { left: 0, top: parts[0] ?? 0 }
      : { left: parts[0] ?? 0, top: parts[1] ?? 0 };
  };
  function domLike(left: number, top: number): Fake {
    const it = tile(left, top);
    it.getBoundingClientRect = function () {
      const t = translated(this.style.transform);
      return { left: this.at.left + t.left, top: this.at.top + t.top };
    };
    return it;
  }
  const raw = domLike(0, 0);
  const rawNodes = new Map<string, Tile>([["tk-raw", raw]]);
  const rawFirst = commit(rawNodes, new Map([["tk-was", { left: 0, top: 0 }]]), clock.env);
  const rawSecond = commit(rawNodes, rawFirst.after, clock.env); // before the frame: no release yet
  check(
    "measured WITH its own invert, an entering tile reads as a mover on the next commit — the cascade",
    raw.style.transform === "translate(0px, 6px)",
    JSON.stringify(raw.style),
  );
  rawFirst.release?.();
  rawSecond.release?.();
  const peeled = domLike(0, 0);
  const rawRect = peeled.getBoundingClientRect.bind(peeled);
  peeled.getBoundingClientRect = function () {
    const t = translated(this.style.transform);
    return peel(rawRect(), `matrix(1, 0, 0, 1, ${t.left}, ${t.top})`);
  };
  const peeledNodes = new Map<string, Tile>([["tk-peeled", peeled]]);
  const peeledFirst = commit(peeledNodes, new Map([["tk-was", { left: 0, top: 0 }]]), clock.env);
  const peeledSecond = commit(peeledNodes, peeledFirst.after, clock.env);
  check(
    "measured on its LAYOUT rect, the same tile is not a mover — the next commit leaves it alone",
    peeled.style.transform === "translateY(-6px)" && peeledSecond.release === undefined,
    JSON.stringify(peeled.style),
  );
  peeledFirst.release?.();
  check(
    "and when its play is released it is visible",
    peeled.style.opacity === "" && peeled.style.transform === "",
  );

  /* ── Environments with nothing to wait for ────────────────────────────── */

  const n = tile(0, 0);
  const only = new Map<string, Tile>([["tk-n", n]]);
  const noFrames = commit(only, new Map([["tk-was", { left: 0, top: 0 }]]), {
    matchMedia: () => ({ matches: false }),
  });
  check(
    "with no frame to wait for the play runs at once — a tile is never left hidden on its account",
    n.style.opacity === "" && noFrames.release === undefined,
    JSON.stringify(n.style),
  );
  const r = tile(0, 0);
  commit(new Map([["tk-r", r]]), new Map([["tk-was", { left: 0, top: 0 }]]), {
    matchMedia: () => ({ matches: true }),
  });
  check(
    "reduced motion writes nothing at all — the tile lands, instantly, untouched",
    r.style.opacity === "" && r.style.transform === "" && r.style.transition === "",
  );
}
