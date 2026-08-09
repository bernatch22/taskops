import { renderToStaticMarkup } from "react-dom/server";

import { Board } from "../../src/pages/Board";
import { Monitor } from "../../src/pages/Monitor";
import type {
  BoardPayload
  
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, opened } = h;

  const monitor = renderToStaticMarkup(
    <Monitor board={fixture.board} openCard={(id) => opened.push(id)} now={now} />,
  );

  /* ── The Board page draws its columns ──────────────────────────────── */

  const board = renderToStaticMarkup(
    <Board board={fixture.board} openCard={(id) => opened.push(id)} />,
  );
  check("board renders", board.includes('data-testid="board"'));
  for (const column of ["Ready", "In flight", "Review", "Blocked", "To merge", "Done"]) {
    check("column " + column, board.includes(column));
  }
  check(
    "every open card has a tile",
    fixture.board.groups.take.every((row) => board.includes(row.id)),
  );

  for (const text of fixture.expect_board) {
    check("board shows " + JSON.stringify(text), (monitor + board).includes(text));
  }

  /* ── A tile names its chapter only when the view holds more than one ──
   *
   * Three states, and all three are properties of the VIEW, not of a tile — so
   * all three are reached by rendering the whole Board, exactly as App does.
   * The spanning payload is the server's own answer with ONE row moved to the
   * chapter the fixture already landed: no shape is written here, and the
   * chapter that does the moving is a real `Milestone` the board sent. */

  const focused = renderToStaticMarkup(<Board board={fixture.board} openCard={() => {}} />);
  check(
    "with one chapter in view no tile repeats it — the header already said it",
    !focused.includes('data-testid="tile-chapter"'),
    focused,
  );

  /* A tile's NOTE — the submit note or the reviewer's words, "verbatim, never
   * summarised" — was the fourth screen printing prose raw (tk-382948). The
   * payload is the server's own with one open row moved into `review`, the
   * group `Board.tsx` reads `row.text` for; the text moved with it is a real
   * released note off the same board. */
  const handedBoard = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const handed = handedBoard.groups.take[0] ?? handedBoard.groups.doing[0];
  if (handed) {
    handedBoard.groups.review = [
      { ...handed, holder: null, text: "got to the rounding — see `src/tax.py::half_up`" },
    ];
    const withNote = renderToStaticMarkup(<Board board={handedBoard} openCard={() => {}} />);
    check(
      "a tile's note reads its markdown instead of printing the backticks",
      withNote.includes("<code") &&
        withNote.includes("src/tax.py::half_up") &&
        !withNote.includes("`src/tax.py"),
      withNote,
    );
  }

  const spanBoard = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  const other = fixture.board_landed.milestone;
  const here = spanBoard.milestone;
  const moved = spanBoard.groups.take[0];
  check(
    "the spanning fixture has the two chapters and a row to move",
    other !== null && here !== null && moved !== undefined,
  );
  if (other && here && moved) {
    spanBoard.milestones = [...spanBoard.milestones, other];
    moved.milestone = other.id;
    // A third row pointing at a chapter this payload cannot name — aged past
    // `milestones`' cap, or a board one version behind. It must draw NOTHING.
    const orphan = spanBoard.groups.blocked[0] ?? spanBoard.groups.take[1];
    if (orphan) orphan.milestone = "ms-doesnotexist";

    const spanning = renderToStaticMarkup(<Board board={spanBoard} openCard={() => {}} />);
    check(
      "with two chapters in view the moved tile names its own",
      spanning.includes(`⌗ ${other.title}`),
      spanning,
    );
    check(
      "and the rows that stayed name theirs",
      spanning.includes(`⌗ ${here.title}`),
      spanning,
    );
    check(
      "a chapter that does not resolve draws nothing, never the raw id",
      !spanning.includes("ms-doesnotexist"),
      spanning,
    );
  }
}
