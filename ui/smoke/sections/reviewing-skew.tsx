import { renderToStaticMarkup } from "react-dom/server";

import { LiveLeases } from "../../src/components/monitor/LiveLeases";
import { LEASE_TTL } from "../../src/components/monitor/panels";
import type {
  ReviewingRow
  
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;

  /* ── The reviewing row's version-skew fallback ─────────────────────
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
}
