import { renderToStaticMarkup } from "react-dom/server";

import { CommentBox, submit, watching } from "../../src/components/card/CommentBox";
import { RpcError, createClient } from "../../src/client";
import { LEASE_TTL } from "../../src/components/monitor/panels";
import type {
  TeamMember
} from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

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
    }
  } as Storage;
}

export async function run(fixture: Fixture, check: Check, _h: Harness): Promise<void> {

  /* ── The one write: the comment box posts `update` ──────────────────── */

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

  /* The picker offers who is LIVE, not everybody seen today. The clock is the
     board's own lease TTL, so a member last seen three TTLs ago is not somebody
     you reach by writing to them and is not drawn. */
  const chipsOf = (markup: string): number => markup.split('data-testid="mention-pick"').length - 1;
  const member = (actor: string, ago: number): TeamMember => ({ actor, seen: 0, ago });
  const noSend = async (): Promise<void> => undefined;

  const mixed = renderToStaticMarkup(
    <CommentBox
      team={[member("agent:berna/live", LEASE_TTL - 60), member("agent:berna/gone", LEASE_TTL * 3)]}
      onSend={noSend}
    />,
  );
  check("only the live member is offered", chipsOf(mixed) === 1, mixed);
  check("the stale member is not offered", !mixed.includes("agent:berna/gone"));
  check("with somebody live there is no sentence", !mixed.includes('data-testid="nobody-live"'));

  const allStale = renderToStaticMarkup(
    <CommentBox
      team={[member("agent:berna/gone", LEASE_TTL + 1), member("dev:berna", LEASE_TTL * 90)]}
      onSend={noSend}
    />,
  );
  check("nobody live draws no chips", chipsOf(allStale) === 0, allStale);
  check(
    "and one honest sentence instead",
    allStale.includes('data-testid="nobody-live"') &&
      allStale.includes("a comment with no address still lands on the card"),
  );

  /* A window WATCHING a public board: the box says so instead of offering a
     form whose every send is a 409. `watching()` is the whole rule and it reads
     the SERVER's answer — an older payload with no `actor` is not anonymous. */
  check("anon is watching", watching({ actor: "anon" }));
  check("a named reader is not", !watching({ actor: "dev:berna" }));
  check("and neither is a payload that predates the key", !watching({}) && !watching(undefined));

  const window_ = renderToStaticMarkup(
    <CommentBox team={[member("agent:berna/live", 10)]} onSend={noSend} readOnly />,
  );
  check("a watcher gets no textarea and no send", !window_.includes('data-testid="send"'), window_);
  check("no mention picker either", chipsOf(window_) === 0);
  check(
    "and the refusal names how a key gets registered",
    window_.includes('data-testid="read-only"') && window_.includes("--key ~/.ssh/id_ed25519"),
  );
  check(
    "a reader WITH a credential still gets the form",
    renderToStaticMarkup(<CommentBox team={[member("agent:berna/live", 10)]} onSend={noSend} />)
      .includes('data-testid="send"'),
  );
}
