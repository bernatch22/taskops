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
import { LiveLeases } from "../src/components/monitor/LiveLeases";
import { KpiRail } from "../src/components/chrome/KpiRail";
import { Worktrees } from "../src/pages/Worktrees";
import { LEASE_TTL } from "../src/components/monitor/panels";
import type { BoardPayload, CardPayload, ReviewingRow } from "../src/types";

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

  /* ── 2b. The reviewing row's version-skew fallback ─────────────────────
   *
   * `LiveLeases.leaseStart` counts a reviewing row down from `review_since` —
   * the REVIEW lease's own acquisition — and falls back to `since`, the WORK
   * lease's, for a board that predates the key. That fallback was correct by
   * construction and had NO test: the branch that wrote it was cut before this
   * harness existed (tk-17d463).
   *
   * The row is assembled HERE rather than taken from the fixture, and that is
   * not the shortcut this file otherwise forbids: the case under test is a
   * payload NO board at this version can produce — `pulse.py::run` always sends
   * the key. There is nowhere else it could come from. What can still be the
   * server's own shape is the row itself, so it is a real `doing` row from the
   * fixture with only the two keys under test set on top of it.
   *
   * `since` is deliberately older than the TTL, which is what makes the two
   * cases distinguishable at all: the floor reads 0s (the payload cannot say
   * more) while the real key reads minutes. Asserting they DIFFER is what
   * would fail if somebody "simplified" `leaseStart` back to `row.since`. */

  const base = fixture.board.groups.doing[0] ?? fixture.board.groups.take[0];
  if (base === undefined) {
    check("a row to build the reviewing case from", false, "the fixture has no open card");
  } else {
    const standing = { ready: 0, blocked: 0, closed: 0 };
    const draw = (row: ReviewingRow): string =>
      renderToStaticMarkup(
        <LiveLeases
          doing={[]}
          reviewing={[row]}
          stalled={[]}
          now={now}
          onOpen={() => {}}
          standing={standing}
        />,
      );

    // The review lease was claimed 60s ago; the work lease, three TTLs ago.
    const withKey = draw({ ...base, since: now - LEASE_TTL * 3, review_since: now - 60 });
    const withoutKey = draw({ ...base, since: now - LEASE_TTL * 3 });

    check("a reviewing row draws with review_since", withKey.includes('data-testid="pane-leases"'));
    check("it counts the REVIEW lease down, not the work lease", withKey.includes("14m"));
    check(
      "a board with no review_since neither crashes nor drops the row",
      withoutKey.includes('data-testid="pane-leases"') && withoutKey.includes(base.id),
    );
    // The floor, verbatim: `TTL - (now - since)` clamped at 0. Never a NaN, and
    // never the 14m it has no way of knowing.
    check(
      "without the key it shows the floor and not a wrong figure",
      withoutKey.includes(">0s<") && !withoutKey.includes("14m") && !withoutKey.includes("NaN"),
    );
    check("the two payloads do not render the same countdown", withKey !== withoutKey);
  }

  /* ── 2c. A board older than the `done` group ───────────────────────────
   *
   * `done_total` and `groups.done` arrived in ONE commit (a1d1005), so a board
   * that predates it sends nine groups and no total — and every consumer of
   * either now reads `?? 0` / `?? []`. Same reasoning as 2b for why the payload
   * is built here: no board at this version can produce it. This one is made by
   * DELETING keys from the server's own answer rather than by writing a shape,
   * so it stays a real payload minus exactly what an older one lacks. */

  const older = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  delete older.done_total;
  delete older.groups.done;

  // All THREE consumers, and getting here took a correction worth recording:
  // rendering Monitor + Board alone left two of the three `?? 0` sites dead.
  // Monitor's standing is drawn only when NOBODY holds a lease (LiveLeases'
  // empty branch), and the fixture has a live card — so the leases are emptied
  // on this copy to reach it. `KpiRail` is not on either page at all; it is
  // App's chrome, so it is rendered directly. Mutating each site one at a time
  // is what showed this: with only the two pages, breaking Monitor or KpiRail
  // alone still passed.
  const quiet = JSON.parse(JSON.stringify(older)) as BoardPayload;
  quiet.groups.doing = [];
  quiet.groups.reviewing = [];
  quiet.groups.stalled = [];

  const olderMarkup = renderToStaticMarkup(
    <>
      <Monitor board={older} openCard={() => {}} now={now} />
      <Monitor board={quiet} openCard={() => {}} now={now} />
      <Board board={older} openCard={() => {}} />
      <Worktrees groups={older.groups} onOpen={() => {}} />
      <KpiRail board={older} />
    </>,
  );

  // Every assertion below is POSITIVE — it names the figure that must be on
  // screen — and that is a correction, not a style. The first version asserted
  // `!markup.includes("undefined")`, which can never fail: TypeScript's `!`
  // erases at runtime and React renders `undefined` as NOTHING, so a broken
  // fallback leaves an EMPTY element, not the word. Mutating each of the five
  // `?? 0` / `?? []` sites one at a time is what exposed it — four stayed green.
  check(
    "the standing is actually on screen (else the figure check proves nothing)",
    olderMarkup.includes('data-testid="standing"'),
  );
  check("the KPI rail is on screen too", olderMarkup.includes('data-testid="kpis"'));
  check("the worktrees table is on screen too", olderMarkup.includes('data-testid="worktrees"'));
  check(
    "a board with no done_total still draws every page",
    olderMarkup.includes('data-testid="monitor"') && olderMarkup.includes('data-testid="board"'),
  );
  check(
    "the standing's closed figure reads 0",
    /<div class="num"[^>]*>0<\/div><div[^>]*>closed this chapter</.test(olderMarkup),
  );
  check(
    "the rail's closed tile reads 0",
    /data-kpi="closed".*?class="num"[^>]*>0<\/span>/s.test(olderMarkup),
  );
  // The header collapses to the plain word: there is no "n of m" to state.
  check("the Done column keeps its plain header", olderMarkup.includes(">Done<"));
  check("nothing rendered NaN", !olderMarkup.includes("NaN"));

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

  /* ── 7. The board points at the code — and only when it can ───────────────
   *
   * `BoardPayload.repo` is the whole switch (`links.tsx`). The fixture is a
   * REAL board with no `origin` recorded, so the no-slug case is the payload
   * above, unmodified — the case that must change NOTHING. The with-slug case
   * is built here for the same reason as 2b and 2c: this board cannot produce
   * one, and the copy is the server's own answer with the key set on top.
   *
   * The gitlab pass is not a duplicate. It is the assertion that a non-GitHub
   * host is a VALUE and not a second code path: same components, same props,
   * a different row of `BY_HOST`, and `/-/commit/` instead of `/commit/`.
   * Delete that row and this is the check that goes red. */

  const drawAll = (payload: BoardPayload, dossierCard: CardPayload): string =>
    renderToStaticMarkup(
      <>
        <Monitor board={payload} openCard={() => {}} now={now} />
        <Worktrees
          groups={payload.groups}
          onOpen={() => {}}
          repo={payload.repo}
          milestoneBranch={payload.milestone?.branch ?? ""}
        />
        <Dossier
          dossier={dossierCard}
          openId={dossierCard.card.id}
          team={payload.team}
          now={now}
          onClose={() => {}}
          onComment={async () => {}}
          repo={payload.repo}
        />
      </>,
    );

  const REPO = {
    host: "github.com",
    slug: "owner/repo",
    url: "https://github.com/owner/repo",
  };

  const linkable = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  linkable.repo = REPO;
  const onGitlab = JSON.parse(JSON.stringify(fixture.board)) as BoardPayload;
  onGitlab.repo = { host: "gitlab.com", slug: "g/sub/p", url: "https://gitlab.com/g/sub/p" };

  // A commit with counts, on the dossier's commit list AND on its thread — the
  // two places a sha is drawn, and the two `numstat` readers (a typed field and
  // `readNumstat` over an open event body) that must agree.
  const counted = JSON.parse(JSON.stringify(fixture.card)) as CardPayload;
  const sha = counted.commits[0]?.sha ?? "0".repeat(40);
  const numstat = { "src/a.py": [12, 3], "ui/logo.png": null };
  counted.commits[0] = { sha, subject: "a commit with counts", numstat: { "src/a.py": [12, 3], "ui/logo.png": null } };
  counted.history = [
    ...counted.history,
    {
      id: "smoke-commit",
      ts: now - 60,
      actor: "agent:berna/e3",
      kind: "commit",
      scope: "task",
      subject: counted.card.id,
      body: { sha, subject: "a commit with counts", numstat },
    } as unknown as (typeof counted.history)[number],
  ];

  const noSlug = drawAll(fixture.board, counted);
  const slug = drawAll(linkable, counted);
  const gitlab = drawAll(onGitlab, counted);

  // NO SLUG → NO LINKS, and no layout shift. Not "no href" — no ANCHOR: a
  // disabled-looking link is the dead anchor the chapter's rule forbids.
  check("no slug: not one anchor is rendered", !noSlug.includes("<a "));
  check(
    "no slug: no compare offered anywhere",
    !noSlug.includes("card-compare") &&
      !noSlug.includes("chapter-compare") &&
      !noSlug.includes("worktree-compare"),
  );
  check(
    "no slug: the worktrees table keeps its five columns",
    noSlug.includes("130px minmax(0,1fr) 240px 92px 124px;") && !noSlug.includes("124px 46px"),
  );

  check("a sha links to the commit page", slug.includes(`https://github.com/owner/repo/commit/${sha}`));
  check("the thread's sha is a link too", slug.includes('data-testid="thread-commit-link"'));
  check(
    "the card offers its PR-diff view against the chapter branch",
    slug.includes('data-testid="card-compare"') && /compare\/ms[^"]*\.\.\.tk-/.test(slug),
  );
  check("the chapter compares against the trunk", slug.includes('data-testid="chapter-compare"'));
  check("a worktree row compares too", slug.includes('data-testid="worktree-compare"'));
  check("the table reserved a column for it", slug.includes("124px 46px"));
  check(
    "every outward anchor is a new tab with rel=noopener",
    (slug.match(/<a /g) ?? []).length === (slug.match(/rel="noopener noreferrer"/g) ?? []).length,
  );
  check("no anchor has an empty href", !slug.includes('href=""'));

  check("the numstat draws +12", slug.includes(">+12<"));
  check("and −3, with a minus sign", slug.includes(">−3<"));
  // The honest half: git prints `-` for a binary and the payload stores null.
  // A "0" here would be the UI claiming a measurement nobody made.
  check("a binary is counted as binary, never as a zero", slug.includes("1 binary"));
  check(
    "both numstat readers agree — the commit list and the thread",
    (slug.match(/data-testid="numstat"/g) ?? []).length >= 2,
  );

  check(
    "a non-github host is a VALUE: /-/commit and /-/compare",
    gitlab.includes(`https://gitlab.com/g/sub/p/-/commit/${sha}`) && gitlab.includes("/-/compare/"),
  );
  check("nothing rendered NaN or an undefined path", !slug.includes("NaN") && !slug.includes("/undefined"));

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
