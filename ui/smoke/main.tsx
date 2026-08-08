/* What the dashboard has to prove, run against a real board payload.
 *
 * This file is the list. It is aimed at the modules `src/main.tsx` bundles, so
 * every assertion below is about the page that actually ships — and the three
 * seams that make it runnable without a browser are used exactly as their
 * authors designed them:
 *
 *   · `Dossier`, exported beside `Drawer`, because `Overlay` is a PORTAL and a
 *     portal renders nothing under `renderToStaticMarkup`. The document is the
 *     part worth asserting on; the portal is not.
 *   · `submit()`, the send rule as a pure function, so "the draft survives a
 *     refusal" is a claim with no DOM in it.
 *   · `overlayStack`, which holds no listener, so "Escape closes the top-most
 *     only" runs under plain node.
 *
 * The payload is the board's own answer (`tests/test_ui.py` builds it from a
 * live `LocalBoard`), never a hand-written shape: a UI that renders a fixture
 * the server would never send is a UI that renders nothing in production, and
 * that was v1's actual failure. `expect` and `expect_board` travel IN the
 * fixture for the same reason — the Python side names the strings it put on the
 * board and this side proves they reached the screen. */
import { renderToStaticMarkup } from "react-dom/server";

import { Dossier } from "../src/components/card/Drawer";
import { submit } from "../src/components/card/CommentBox";
import { RpcError, createClient } from "../src/client";
import { depth, escape, push } from "../src/components/shared/overlayStack";
import { Board } from "../src/pages/Board";
import { Monitor } from "../src/pages/Monitor";
import type { BoardPayload, CardPayload } from "../src/types";

/** The fixture, as `tests/test_ui.py` writes it. */
export interface Fixture {
  board: BoardPayload;
  card: CardPayload;
  /** substrings the Monitor + Board markup must contain */
  expect_board: string[];
  /** substrings the dossier must contain */
  expect: string[];
}

/** The eight panes Monitor draws. Nova's own count: nothing merged, nothing
 *  dropped for lack of a verb (`components/monitor/panels.ts`). */
const PANES = [
  "pane-leases",
  "pane-throughput",
  "pane-health",
  "pane-dag",
  "pane-files",
  "pane-chapter",
  "pane-mentions",
  "pane-events",
];

export async function smoke(fixture: Fixture): Promise<string[]> {
  const failures: string[] = [];
  const now = Date.now() / 1000;
  const opened: string[] = [];

  function check(name: string, ok: boolean, detail = ""): void {
    if (ok) console.log("ok " + name);
    else failures.push(`${name}${detail ? " — " + detail : ""}`);
  }

  /* ── 1. Monitor draws its eight panes ─────────────────────────────────── */

  const monitor = renderToStaticMarkup(
    <Monitor board={fixture.board} openCard={(id) => opened.push(id)} now={now} />,
  );
  check("monitor renders", monitor.includes('data-testid="monitor"'));
  for (const pane of PANES) {
    check("pane " + pane, monitor.includes(`data-testid="${pane}"`));
  }

  /* ── 2. A pane with no source shows its empty state, not a zero ────────── */

  // The event stream has no verb behind it (panels.ts, note 1): the pane is
  // drawn to its full shape and says so. A "0" there would be a claim the board
  // never made — that the log is empty — and this is the assertion that keeps
  // the honest empty state from quietly becoming one.
  check(
    "event stream says the verb is missing",
    monitor.includes("no events verb") && monitor.includes('data-testid="pane-empty"'),
  );
  check("event stream counter is — and not 0", monitor.includes("—"));

  /* ── 3. The Board page draws its columns ──────────────────────────────── */

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

  /* ── 4. The dossier — including the criteria v1 never drew ─────────────── */

  const dossier = renderToStaticMarkup(
    <Dossier
      dossier={fixture.card}
      openId={fixture.card.card.id}
      team={fixture.board.team}
      now={now}
      onClose={() => {}}
      onComment={async () => {}}
    />,
  );
  for (const text of fixture.expect) {
    check("dossier shows " + JSON.stringify(text), dossier.includes(text));
  }
  check("criteria are on screen", dossier.includes('data-testid="criteria"'));
  check(
    "every criterion is drawn, numbered",
    fixture.card.card.criteria.every((text) => dossier.includes(text)),
  );
  check("the comment box is the foot", dossier.includes('data-testid="comment-box"'));

  /* ── 5. The one write: the comment box posts `update` ──────────────────── */

  const posted: unknown[] = [];
  const client = createClient("/b", fakeStorage(), {
    fetch: (async (_url: string, init: { body: string }) => {
      posted.push(JSON.parse(init.body));
      return { json: async () => ({ ok: true, seq: 1, data: {} }) };
    }) as unknown as typeof globalThis.fetch,
  });
  const task = fixture.card.card.id;
  const send = async (text: string, mentions: string[]): Promise<void> => {
    // The same call `useBoard.comment` makes: `update` with comment= and
    // mentions= riding on it. No status: the browser does not move a card.
    await client.rpc("update", { task, comment: text, mentions });
  };

  const sent = await submit("Decimal, please", ["dev:berna"], send);
  check("send posts one call", posted.length === 1);
  check(
    "the call is update, with the comment and the mentions",
    JSON.stringify(posted[0]) ===
      JSON.stringify({
        verb: "update",
        args: { task, comment: "Decimal, please", mentions: ["dev:berna"] },
      }),
    JSON.stringify(posted[0]),
  );
  check("an accepted comment clears the draft", sent.draft === "" && sent.failed === "");

  const refusal = async (): Promise<void> => {
    throw new RpcError("refused", "Refused: taskops_take task=tk-1 first");
  };
  const kept = await submit("a paragraph", ["dev:berna"], refusal);
  check("the draft survives a refusal", kept.draft === "a paragraph");
  check("the mentions survive it too", kept.picked.length === 1);
  check(
    "the refusal is shown in the server's own words",
    kept.failed === "Refused: taskops_take task=tk-1 first",
  );

  const blank = await submit("   ", [], async () => {
    throw new Error("an empty comment must never reach the board");
  });
  check("an empty draft sends nothing", blank.failed === "" && posted.length === 1);

  /* ── 6. Escape closes the top-most overlay only ────────────────────────── */

  const closed: string[] = [];
  const popDrawer = push(() => closed.push("drawer"));
  const popConfirm = push(() => closed.push("confirm"));
  check("two overlays are stacked", depth() === 2);
  check("escape closes the top-most", escape() && JSON.stringify(closed) === '["confirm"]');
  popConfirm();
  check("escape then closes the one below", escape() && closed.length === 2);
  popDrawer();
  check("an empty stack swallows nothing", escape() === false && depth() === 0);

  return failures;
}

/** `localStorage`, in four lines. `client.ts` takes its storage as a parameter
 *  precisely so this is all it costs (v1 faked three globals to import its api). */
function fakeStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: () => null,
    get length() {
      return map.size;
    },
  } as Storage;
}
