import { renderToStaticMarkup } from "react-dom/server";

import { Dossier } from "../../src/components/card/Drawer";
import { EventStream  } from "../../src/components/monitor/EventStream";
import { Thread, detail, oneLine, prose } from "../../src/components/card/Thread";
import type {
  Event
  
  
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;

  /* ── The thread draws the prose an agent closed with ────────────────────
   *
   * The complaint was "the agents never leave comments when they close a card".
   * They do — measured on this repo's own log, 61 of 61 `status done` events
   * carry a `reason` — and `mcp/thread.py::detail` prints it. The DASHBOARD
   * dropped it, for two independent reasons: `detail()` tried `to` before it
   * would ever have reached `reason` (which was not in its list at all), so a
   * close resolved to the bare word "done"; and the render drew a text block
   * only for `kind === "comment"`, so even the right string had nowhere to go.
   *
   * Everything below comes from the board's OWN event bodies — `tests/test_ui.py`
   * closes two real cards through the verbs — because a hand-written history is
   * exactly what would have kept this bug green. */

  const [reviewed, noCode] = fixture.closed;
  if (reviewed === undefined || noCode === undefined) {
    check("the fixture carries two closed cards", false, "fixture.closed is short");
  } else {
    const closedThread = renderToStaticMarkup(<Thread history={reviewed.history} now={now} />);
    const at = (h: Event[], kind: string): Event | undefined => h.find((e) => e.kind === kind);

    // Criterion 1. The transition is still there — a reader must see at a glance
    // that this was a close and not a remark — and the note is there WITH it.
    check(
      "a close draws its transition AND the note the worker signed off with",
      closedThread.includes('data-testid="event-detail"') &&
        closedThread.includes('data-testid="event-prose"') &&
        closedThread.includes("closed after the pass — Decimal all the way") &&
        closedThread.includes(">done<"),
    );
    // …and the prose is what the log actually holds, not a string this file made up.
    check(
      "the note on screen is the one the server wrote into status.reason",
      at(reviewed.history, "status")?.body["reason"] ===
        "closed after the pass — Decimal all the way",
    );

    // Criterion 2. `submitted` and `reviewed` carry `body.note`; the verdict
    // rides beside its note rather than replacing it.
    check(
      "handing in draws its note",
      closedThread.includes("parsed with Decimal throughout") &&
        at(reviewed.history, "submitted")?.body["note"] === "parsed with Decimal throughout",
    );
    check(
      "a verdict draws BOTH its word and what the verifier wrote",
      closedThread.includes(">pass<") &&
        closedThread.includes("read every row, the rounding holds"),
    );
    // The card the rest of this file uses was RELEASED, so its note is the third
    // case and it is on the screen the drawer draws.
    check(
      "a release draws its note",
      renderToStaticMarkup(<Thread history={fixture.card.history} now={now} />).includes(
        "got to the rounding",
      ),
    );

    // Criterion 3. `no_code` means no commit was ever bound to the card. The
    // Python renderer prints `(no code)`; so does this one now.
    const noCodeThread = renderToStaticMarkup(<Thread history={noCode.history} now={now} />);
    check(
      "a close with no commit says so, in the Python renderer's own words",
      noCodeThread.includes("done (no code)") &&
        noCodeThread.includes("the README already said it, so there was nothing to write") &&
        at(noCode.history, "status")?.body["no_code"] === true,
    );

    // Criterion 4. The two renderers agree. `oneLine` is the join Python uses
    // (`: done — <reason>`), and it is what the Event stream — one line per row
    // — draws, so a close is not a bare word there either.
    const status = at(reviewed.history, "status");
    check(
      "phrase and prose join the way mcp/thread.py::detail joins them",
      status !== undefined &&
        oneLine(status) === "done — closed after the pass — Decimal all the way" &&
        oneLine(noCode.history.filter((e) => e.kind === "status")[0] as Event) ===
          "done (no code) — the README already said it, so there was nothing to write",
    );
    check(
      "the Event stream row carries the prose too, not just the transition",
      renderToStaticMarkup(
        <EventStream
          events={reviewed.history}
          total={reviewed.history.length}
          now={now}
          more={false}
          loading={false}
          onMore={() => {}}
        />,
      ).includes("done — closed after the pass"),
    );
    // The split itself: a phrase is never prose and prose is never a phrase, so
    // nothing is drawn twice. `released` is the one that used to arrive through
    // the fallback loop as a phrase.
    const released = at(fixture.card.history, "released");
    check(
      "no event draws its writing twice",
      released !== undefined &&
        detail(released) === "" &&
        prose(released) === "got to the rounding — see `src/tax.py::half_up`" &&
        // A commit's subject is a phrase, not prose — it stays on the one line
        // it was always on, exactly as `mcp/thread.py::detail` treats it.
        prose(at(reviewed.history, "commit") as Event) === "" &&
        detail(at(reviewed.history, "commit") as Event) === "feat: csv",
    );
    // And the whole of it reaches the DOSSIER, which is the screen the reader
    // complained about — not just the component in isolation.
    check(
      "the closing note is on the dossier a reader actually opens",
      renderToStaticMarkup(
        <Dossier
          dossier={reviewed}
          openId={reviewed.card.id}
          team={fixture.board.team}
          now={now}
          onClose={() => {}}
          onComment={async () => {}}
        />,
      ).includes("closed after the pass — Decimal all the way"),
    );
  }
}
