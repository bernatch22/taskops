/* The board is alive: tiles carry their agent, and they GLIDE between columns.
 *
 * `react-dom/server` has no layout and no `requestAnimationFrame`, so the play
 * itself is unreachable here — which is exactly why every decision the play
 * rests on was written as a pure function in `components/board/flip.ts`. This
 * section pins those, plus the half of the avatar that IS rendered markup:
 * which disc appears on which row, and in whose colour. */
import { renderToStaticMarkup } from "react-dom/server";

import { Board } from "../../src/pages/Board";
import { Avatar, HUES, discColors, hueOf } from "../../src/components/shared/Avatar";
import { AvatarStack } from "../../src/components/chrome/AvatarStack";
import { EPSILON, entering, prefersReducedMotion, shifts } from "../../src/components/board/flip";
import type { Point } from "../../src/components/board/flip";
import type { BoardPayload } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  /* ── The hue is DERIVED, and it is the actor that derives it ─────────── */

  check(
    "the same actor gets the same hue on every render — there is nowhere to store one",
    hueOf("agent:berna/w2") === hueOf("agent:berna/w2"),
  );
  check(
    "a hue is a hue: on the wheel, quantised, never off it",
    [0, 1, 2, 3].every((n) => {
      const hue = hueOf(`agent:berna/w${n}`);
      return hue >= 0 && hue < 360 && Number.isInteger(hue / (360 / HUES));
    }),
  );

  /* The failure this replaced: four token tones, and this project's own board
   * runs w1…w8 in one wave. Eight actors into four tones is a collision by
   * arithmetic, and a colour that collides names nobody. Distinctness is not
   * promised for ALL strings (a hash into 24 buckets cannot), it is checked on
   * the actors this board really has. */
  const wave = ["dev:berna", ...Array.from({ length: 8 }, (_, n) => `agent:berna/w${n + 1}`)];
  check(
    "a real wave of nine actors gets nine distinct hues",
    new Set(wave.map(hueOf)).size === wave.length,
    JSON.stringify(wave.map((a) => [a, hueOf(a)])),
  );

  /* Not a literal colour anywhere: the hue is computed, the rest is tokens, so
   * one disc follows the theme switch like everything else on the page. */
  const colors = discColors("agent:berna/w2");
  check(
    "saturation and lightness come from tokens.css, only the hue is computed",
    colors.background.includes("var(--disc-s)") &&
      colors.background.includes("var(--disc-bg-a)") &&
      colors.color.includes("var(--disc-fg-l)") &&
      !/#[0-9a-f]{3}/i.test(colors.background),
    JSON.stringify(colors),
  );

  /* ── The disc rides the tile, and says whether anybody is RUNNING it ──── */

  const live = renderToStaticMarkup(<Avatar actor="agent:berna/w2" live={true} />);
  const ghost = renderToStaticMarkup(<Avatar actor="agent:berna/w2" live={false} />);
  check("the disc bears the actor's initials, not one letter", live.includes(">w2<"), live);
  check(
    "the full actor is the tooltip — the short name is ambiguous across devs",
    live.includes('title="agent:berna/w2"'),
  );
  check(
    "live and assigned differ in STRENGTH, never in identity: one hue, two opacities",
    live.includes("opacity:1") &&
      ghost.includes("opacity:0.45") &&
      ghost.includes(`${hueOf("agent:berna/w2")}`),
    ghost,
  );

  /* Presence rules on the board's OWN rows. `holder` is the live lease and
   * `assignee` is who it was handed to (`verbs/_rows.py::row`); a ready row in
   * the open pool has neither, and draws no disc at all. */
  const payload = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const bare = payload.groups.take[0];
  /* The STALLED row is the fixture's own, and it is the honest source for both
   * halves: a real board wrote it, it carries an `assignee` and no `holder`,
   * and that pair is precisely the distinction under test. The doing row is
   * that same row with the lease put back — the ONE field that differs. */
  const stalled = payload.groups.stalled[0];
  if (bare && stalled && stalled.assignee) {
    bare.assignee = "";
    bare.holder = null;
    const doing = {
      ...stalled,
      id: "tk-live99",
      holder: stalled.assignee,
      quiet_for: null,
    };
    payload.groups.doing = [doing];

    const markup = renderToStaticMarkup(<Board board={payload} openCard={() => {}} />);
    const tile = (id: string): string => h.slice(markup, `data-card="${id}"`, "</button>");

    const who = stalled.assignee;
    check(
      "a card somebody is RUNNING shows that agent, at full strength",
      tile(doing.id).includes(`data-actor="${who}"`) && tile(doing.id).includes('data-live="1"'),
      tile(doing.id),
    );
    check(
      "a STALLED card still shows whose it is — ghosted, because nobody is on it",
      tile(stalled.id).includes(`data-actor="${who}"`) &&
        tile(stalled.id).includes('data-live="0"'),
      tile(stalled.id),
    );
    check(
      "a ready card in the open pool has nobody to show and shows nobody",
      !tile(bare.id).includes('data-testid="avatar"'),
      tile(bare.id),
    );
  } else {
    check(
      "fixture carries a ready row and an assigned stalled row",
      false,
      "cannot reach the presence rules",
    );
  }

  /* One actor, one colour, wherever they are drawn — the disagreement that
   * started this: the tile coloured by role and the header by a hash of its
   * own, so an agent was purple in one place and grey in the other. */
  const header = renderToStaticMarkup(<AvatarStack team={fixture.board.team} />);
  const someone = fixture.board.team[0];
  if (someone) {
    const owner = someone.actor.startsWith("agent:")
      ? `dev:${someone.actor.slice("agent:".length).split("/")[0]}`
      : someone.actor;
    check(
      "the header's row draws the SAME disc as a tile — one component, one hue",
      header.includes(`${hueOf(owner)} var(--disc-s)`),
      header,
    );
  }

  /* ── FLIP, the part that has no browser in it ─────────────────────────── */

  const rect = (left: number, top: number): Point => ({ left, top });
  const before = new Map<string, Point>([
    ["tk-a", rect(0, 0)],
    ["tk-b", rect(0, 100)],
    ["tk-gone", rect(0, 200)],
  ]);
  const after = new Map<string, Point>([
    ["tk-a", rect(300, 40)],
    ["tk-b", rect(0, 100)],
    ["tk-new", rect(300, 200)],
  ]);

  const moved = shifts(before, after);
  check(
    "a card that changed column is put BACK where it was — the invert, exactly",
    moved.length === 1 && moved[0]?.id === "tk-a" && moved[0].dx === -300 && moved[0].dy === -40,
    JSON.stringify(moved),
  );
  check(
    "a tile that did not move is not animated — a board that twitches is worse than one that jumps",
    !moved.some((s) => s.id === "tk-b"),
  );
  check(
    "a card that LEFT the payload is not in the list: it is gone from the DOM, and there is no exit",
    !moved.some((s) => s.id === "tk-gone"),
  );
  check(
    "sub-pixel drift is not a move — a scrollbar appearing must not animate the board",
    shifts(new Map([["tk-a", rect(0, 0)]]), new Map([["tk-a", rect(EPSILON / 2, 0)]])).length === 0,
  );
  check(
    "a card that was not there before ENTERS instead of being displaced",
    JSON.stringify(entering(before, after)) === JSON.stringify(["tk-new"]),
    JSON.stringify(entering(before, after)),
  );

  /* The guard is CONSULTED, live, per play — never read once at import: a
   * reader who turns motion off mid-session is obeyed on the next refetch. */
  const asked: string[] = [];
  const reduced = {
    matchMedia: (q: string) => (asked.push(q), { matches: true }),
  };
  check(
    "reduced motion is asked for by its own media query, and answered",
    prefersReducedMotion(reduced) && asked[0] === "(prefers-reduced-motion: reduce)",
    JSON.stringify(asked),
  );
  check(
    "a reader who has NOT asked for less motion gets the animation",
    !prefersReducedMotion({ matchMedia: () => ({ matches: false }) }),
  );
  check(
    "an environment that cannot answer animates — absent is not a preference",
    !prefersReducedMotion(undefined) && !prefersReducedMotion({}),
  );

  /* And the page still renders headlessly with the hook in it — no layout
   * effect warning, no rAF, nothing that needs a window. */
  check(
    "the Board renders under react-dom/server with the FLIP hook mounted",
    renderToStaticMarkup(<Board board={fixture.board} openCard={() => {}} />).includes(
      'data-testid="board"',
    ),
  );
}
