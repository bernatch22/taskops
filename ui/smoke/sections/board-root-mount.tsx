import { baseOf, bootstrapToken, createClient, tokenKey } from "../../src/client";
import type { Check, Fixture, Harness } from "./section";

/* THE BOARD'S OWN ADDRESS IS THE PAGE (tk-32d2ba).
 *
 * One page, three mounts, one base. 0.5.0 computed the base by stripping only
 * a trailing `/ui`, so at the new mount — `/<board>/`, the address a human
 * pastes — the base kept its trailing slash and every call the client made
 * carried a double slash (`/taskops-v2//rpc`). What this section pins is the
 * whole client-side half of the card: `baseOf` collapsing all THREE mounts to
 * a clean base, the machine doors under the /api prefix, and the token-key
 * consequence — the bases of the two mounts that WORKED in 0.5.0 are
 * unchanged, so no stored credential is orphaned by the rewrite.
 *
 * Pure functions plus two tiny fakes (a Map storage, a recording fetch): no
 * browser, no jsdom, exactly as client.ts was built to allow. */

function storageOf(map: Map<string, string>): Storage {
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: () => null,
    length: 0,
  } as Storage;
}

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* ── a · the base, from where the page IS, for all three mounts ────────── */
  check("the window's root still mounts its board under /board", baseOf("/") === "/board");
  check("…including a stray /index.html tail-less variant", baseOf("") === "/board");
  check(
    "the board's own address is a clean base — no trailing slash to double",
    baseOf("/taskops-v2/") === "/taskops-v2" && baseOf("/taskops-v2") === "/taskops-v2",
  );
  check(
    "0.5.0's /ui/ mount collapses to the same base, so both spellings share one page",
    baseOf("/taskops-v2/ui/") === "/taskops-v2" && baseOf("/taskops-v2/ui") === "/taskops-v2",
  );
  check(
    "the two mounts that WORKED in 0.5.0 keep their exact bases — tokenKey is keyed by base, so nothing stored is orphaned",
    tokenKey(baseOf("/")) === "taskops:/board" &&
      tokenKey(baseOf("/taskops-v2/ui/")) === "taskops:/taskops-v2",
  );

  /* ── b · every wire call goes through the /api prefix, no double slash ── */
  const asked: string[] = [];
  const fetchFake = (async (url: unknown) => {
    asked.push(String(url));
    return {
      json: async () => ({ ok: true, seq: 1, data: { fine: true } }),
    } as Response;
  }) as typeof globalThis.fetch;

  const store = new Map<string, string>();
  const base = baseOf("/taskops-v2/");
  const client = createClient(base, storageOf(store), { fetch: fetchFake });
  await client.rpc("board");
  await client.git("git/commit/HEAD");
  check("rpc posts to <base>/api/rpc", asked[0] === "/taskops-v2/api/rpc");
  check("git reads <base>/api/git/…", asked[1] === "/taskops-v2/api/git/commit/HEAD");
  check(
    "and no call carries a double slash — the 0.5.0 bug at this mount",
    asked.every((url) => !url.includes("//")),
  );

  /* ── c · a pasted ?token= lands under the SAME key the client reads ───── */
  const cleaned: string[] = [];
  const adopted = bootstrapToken(base, storageOf(store), "?token=tok-1", "/taskops-v2/", (u) =>
    cleaned.push(u),
  );
  check("a pasted token is adopted and the URL cleaned to where the page is", adopted && cleaned[0] === "/taskops-v2/");
  check("under the key createClient reads back", client.token() === "tok-1");
}
