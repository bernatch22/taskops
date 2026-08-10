import { renderToStaticMarkup } from "react-dom/server";

import { Header } from "../../src/components/chrome/Header";
import type { BoardPayload } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

/** The header, drawn with everything but the forge held constant — so the only
 *  thing the two renders below can differ by is the one fact under test. */
function header(board: BoardPayload): string {
  return renderToStaticMarkup(
    <Header
      milestone={board.pulse.milestone}
      milestones={board.milestones}
      selected=""
      onSelect={() => {}}
      live={true}
      forge={board.forge}
      team={board.team}
      theme="dark"
      onToggleTheme={() => {}}
    />,
  );
}

export async function run(fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* ── A board SAYS what opens it (tk-5c64d5) ───────────────────────────
   *
   * Declaring a forge wrote an event and nothing else, and nobody but the owner
   * could see it: an agent with full board access could not tell that this board
   * is one somebody could join with `--github`, and this dashboard could not draw
   * it. Discovery was by getting refused at the door.
   *
   * The fact now rides on the board payload, derived per read exactly as
   * `visibility` is (`verbs/pulse.py`), and lands HERE — one line under the
   * board's own identity, where a reader already looks to know what they are
   * reading. */

  const forge = fixture.board.forge;
  check(
    "the fixture board declares a forge, from the server's own answer",
    forge !== undefined && forge.repo.includes("/"),
    JSON.stringify(forge),
  );
  if (!forge) return;

  const opened = header(fixture.board);
  check(
    "the header says which repo opens this board, and with what access",
    opened.includes('data-testid="board-forge"') &&
      opened.includes(`${forge.host}/${forge.repo}`) &&
      opened.includes(forge.need),
    opened,
  );
  // The line is a way IN, so it carries the command — a reader who has the board
  // should not have to be refused to learn how somebody else gets on it.
  check(
    "…and how somebody who is not here yet would join",
    opened.includes("taskops join &lt;board&gt; --github"),
    opened,
  );

  /* And the board that declared nothing: NO line, not an empty one. Absent is
   * the state every board is born in (`core/forge.py`), so this is the common
   * render and it must be the header that was always there. The payload for it
   * is the same one with the key REMOVED — never a `null`, which is the shape
   * `pulse.py` deliberately does not send. */
  const invited = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  delete invited.forge;
  const quiet = header(invited);
  check(
    "an invite-only board draws no forge line at all",
    !quiet.includes('data-testid="board-forge"') && !quiet.includes("--github"),
    quiet,
  );
  check(
    "…and the rest of the header is byte for byte what it always was",
    quiet === opened.replace(/<div class="mono" data-testid="board-forge".*?<\/div>/, ""),
    quiet,
  );
}
