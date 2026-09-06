/* How far along a card is, as its WORKER reports it — `taskops_update progress=`.
 *
 * The whole feature is one number that nothing derives, so what there is to pin
 * is where it is drawn and, more importantly, where it is NOT: a card nobody has
 * reported on must draw no track at all. "Absent is not 0" is the rule the board
 * itself keeps (`core/types.py::Card.progress` is NotRequired, `verbs/_rows.py`
 * sends null), and a tile that drew an empty bar would be the UI claiming a
 * worker said something it never said.
 *
 * The payload is the server's own — the fixture's real rows, with the number set
 * on a copy — so no shape is invented here. */
import { renderToStaticMarkup } from "react-dom/server";

import { Board } from "../../src/pages/Board";
import { Dossier } from "../../src/components/card/Drawer";
import type { BoardPayload, CardPayload } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const plain = renderToStaticMarkup(<Board board={fixture.board} openCard={() => {}} />);
  check(
    "a board nobody has reported progress on draws no track anywhere",
    !plain.includes('data-testid="progress"'),
  );

  /* One row, reported on — the server's own answer with the key the server's own
   * verb writes. Every other row in the same payload stays silent, which is what
   * makes this a test of the CONDITION and not of the markup. */
  const reported = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const row = reported.groups.take[0] ?? reported.groups.doing[0] ?? reported.groups.blocked[0];
  if (!row) throw new Error("the fixture has no open card to report on");
  row.progress = 35;
  const board = renderToStaticMarkup(<Board board={reported} openCard={() => {}} />);
  check("a reported card draws its track", board.includes('data-testid="progress"'));
  check("the track carries the number it was given", board.includes('data-progress="35"'));
  check("and says it in words beside the bar", board.includes("35%"));
  check(
    "exactly ONE tile draws it — the others said nothing",
    board.split('data-testid="progress"').length - 1 === 1,
    board,
  );

  /* The two ends, and the fill each draws. 0 is a REPORT ("I have started and
   * got nowhere"), which is why it draws a track at all — the state that draws
   * nothing is the absent key above, never a zero. */
  for (const [value, width] of [
    [0, "width:0%"],
    [100, "width:100%"],
  ] as const) {
    row.progress = value;
    const drawn = renderToStaticMarkup(<Board board={reported} openCard={() => {}} />);
    check(`${value}% draws a track filled ${width}`, drawn.includes(width), drawn);
  }

  /* A number outside the range cannot come from this server (`mcp/schema.py`
   * bounds it 0–100) and can come from a board one version ahead or behind. The
   * fill is clamped to the track either way: a bar wider than its own rail is
   * the one failure a reader would read as a rendering fault rather than data. */
  row.progress = 140;
  const over = renderToStaticMarkup(<Board board={reported} openCard={() => {}} />);
  check("a number past the range still fills exactly the track", over.includes("width:100%"), over);

  /* The DRAWER says the same number in words, once — the tile owns the bar. */
  const silent = renderToStaticMarkup(
    <Dossier
      dossier={fixture.card}
      openId={fixture.card.card.id}
      team={fixture.board.team}
      now={h.now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  check(
    "a card nobody reported on says nothing in the drawer either",
    !silent.includes('data-testid="card-progress"'),
  );

  const told = JSON.parse(JSON.stringify(fixture.card)) as CardPayload;
  told.card.progress = 60;
  const drawer = renderToStaticMarkup(
    <Dossier
      dossier={told}
      openId={told.card.id}
      team={fixture.board.team}
      now={h.now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  check("the drawer reads it back", drawer.includes("60% reported"));
  check(
    "and draws no second bar — one number, one drawing",
    !drawer.includes('data-testid="progress"'),
    drawer,
  );
}
