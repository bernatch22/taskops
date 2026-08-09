import { renderToStaticMarkup } from "react-dom/server";

import { Monitor } from "../../src/pages/Monitor";
import { EventStream, FIXTURE_EVENTS } from "../../src/components/monitor/EventStream";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, opened } = h;

  const monitor = renderToStaticMarkup(
    <Monitor board={fixture.board} openCard={(id) => opened.push(id)} now={now} />,
  );

  /* ── The Event stream: rows when it has them, honesty when it does not ─
   *
   * The pane pages the `events` verb itself, so under this harness — which
   * renders once, fires no effect and has no wire — `Monitor` draws it with
   * `client={undefined}` and it must say so rather than claim an empty log.
   * That is the same rule as before: a "0" there is a statement the board never
   * made. What is new is the other half — the pane HAS a populated shape now,
   * and the split that makes it reachable here is `EventStream` staying pure
   * beside its container (`EventStreamPane`), exactly as `Dossier` sits beside
   * `Drawer`. Rendering it with `FIXTURE_EVENTS` is what proves the entry
   * markup a real fetch draws: the kind pill, the actor, the card id, the body.
   */

  check(
    "event stream with no client says nothing asked for the log",
    monitor.includes("has not been handed a client") &&
      monitor.includes('data-testid="pane-empty"'),
  );
  check("event stream counter is — and not 0", monitor.includes("—"));

  const stream = renderToStaticMarkup(
    <EventStream
      events={FIXTURE_EVENTS}
      total={1284}
      now={now}
      more={true}
      loading={false}
      onMore={() => {}}
    />,
  );
  check(
    "event rows draw kind, actor, card and body",
    stream.includes('data-kind="commit"') &&
      stream.includes("berna/m6") &&
      stream.includes("tk-4b37dd") &&
      stream.includes("the pane is drawn before the verb exists"),
  );
  // task="project" is board history — the stream shows it or it is not the log.
  check("the stream draws board-level history", stream.includes(">project<"));
  check("the counter is the log's total", stream.includes("1,284"));
  // The honest-binary rule: a file git could not count is a binary, never +0−0.
  check("a commit shows its numstat", stream.includes("2 files · +3 −1 · 1 binary"));
  check("an older page can be asked for", stream.includes('data-testid="event-more"'));
}
