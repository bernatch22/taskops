/* The wire, and nothing else: one POST, one socket, one token.
 *
 * Everything the outside world provides arrives as a PARAMETER. v1's `api.ts`
 * read `document`, `location` and `localStorage` at module scope, so importing
 * it had side effects and its smoke test had to fake three globals before the
 * first line of the file could run (teardown hack #18). Here `createClient` is
 * handed its base and its storage, and the browser globals it cannot avoid
 * (fetch, WebSocket, EventSource, origin) are an optional `Env` resolved AT USE,
 * never at import. The consequence that matters: this file runs under node with
 * two small fakes and no globals patched at all.
 *
 * The socket is a SIGNAL. Every frame means "something changed, ask again" —
 * the caller refetches. Nothing here ever hands a frame's body to a renderer,
 * because then a dropped or duplicated frame could leave the page showing
 * something the board never said (http/feed.py says the same from its end). */

import type { RpcVerb } from "./types";

/** The error codes `_errors.py` puts on the wire. `error` is the root type. */
export type ErrorCode = "refused" | "not_found" | "unreachable" | "bad_request" | "error";

/** A refusal from the board, carrying the server's own code and words. A
 *  `Refused` message NAMES the call that fixes it, so it is shown verbatim. */
export class RpcError extends Error {
  readonly code: ErrorCode;

  constructor(code: ErrorCode, message: string) {
    super(message);
    this.name = "RpcError";
    this.code = code;
  }
}

/** The envelope, both halves — http/rpc.py. Always an object, never a bare array. */
type Envelope =
  | { ok: true; seq: number; data: unknown }
  | { ok: false; error?: { code?: string; message?: string } };

/** A feed frame. Only `type` is ever read; the rest is deliberately ignored. */
interface Frame {
  type?: string;
}

/** The globals this client would otherwise reach for. Injectable, all optional. */
export interface Env {
  fetch?: typeof globalThis.fetch;
  WebSocket?: typeof globalThis.WebSocket;
  EventSource?: typeof globalThis.EventSource;
  /** Where the board lives, e.g. "https://host". Defaults to location.origin. */
  origin?: string;
  setTimeout?: (fn: () => void, ms: number) => unknown;
  clearTimeout?: (id: unknown) => void;
}

export interface Client {
  /** Run a verb. Resolves with `data`; rejects with RpcError on `ok:false`. */
  rpc<T>(verb: RpcVerb, args?: Record<string, unknown>): Promise<T>;
  /** Read the /git door — the ONE GET this client makes.
   *
   *  It is a sibling of `rpc` and not a second client: same base, same token,
   *  same envelope, same `RpcError`. It is a GET because it is a READ of a path
   *  that names its own subject (`http/gitdoor.py` routes on the path and
   *  nothing else), and because a diff is cacheable by the browser the way a
   *  verb call is not.
   *
   *  `route` comes from `links.tsx::gitRoute` — the caller never spells a path
   *  here, so the one place that knows the door's shape is the one place that
   *  knows the cascade it feeds. A refusal (no repo on this host, an unknown
   *  ref, no credential) rejects with the server's own words, which is what
   *  lets `links.tsx` tell "this host has no clone" from "that ref is gone". */
  git<T>(route: string): Promise<T>;
  /** Open the feed. `onSignal` fires per frame, `onLive` on every state change.
   *  Returns the stop function; calling it closes and stops reconnecting. */
  subscribe(onSignal: () => void, onLive: (live: boolean) => void): () => void;
  /** The token in use, "" when there is none — the page asks for one then. */
  token(): string;
  /** Remember a token the human pasted. */
  setToken(token: string): void;
}

const RECONNECT_MS = 500;
/* The backoff cap. Doubling forever would leave a laptop that slept through
 * the night waiting minutes for its first retry after the lid opens; ~8s keeps
 * "forever" polite to the server AND means the header heals within seconds of
 * the network actually returning. */
const RECONNECT_CAP_MS = 8_000;

/** The envelope, read once for both doors. `ok:false` becomes an `RpcError`
 *  carrying the server's own code and words — /rpc and /git answer the same
 *  shape (`http/rpc.py`, `http/gitdoor.py`), so they are unwrapped by the same
 *  four lines rather than by two that could drift apart. */
function unwrap<T>(body: unknown): T {
  const envelope = body as Envelope;
  if (!envelope.ok) {
    const code = envelope.error?.code ?? "error";
    throw new RpcError(code as ErrorCode, envelope.error?.message ?? "refused");
  }
  return envelope.data as T;
}

/** The board's base, from where the page IS — the one client for three mounts.
 *
 *  A window (`taskops ui`) serves the page at `/` and mounts its single board
 *  under `/board`; a board host serves it at `/<board>/` — the address a human
 *  pastes — and kept 0.5.0's `/<board>/ui/` because links were already pasted.
 *  Stripping a trailing `/ui` and THEN every trailing slash is what makes all
 *  three collapse to a clean base: 0.5.0 stripped only the `/ui` tail, so at
 *  `/<board>/` the base kept its slash and every call carried `//` — which is
 *  also why no token is orphaned by the change: the bases this yields are the
 *  ones the two WORKING mounts already used (`tokenKey` is keyed by base), and
 *  the only key that moves ("taskops:/<board>/") belonged to a page that never
 *  managed a single call. */
export function baseOf(pathname: string): string {
  const mounted = pathname.replace(/\/ui\/?$/, "").replace(/\/+$/, "");
  return mounted === "" ? "/board" : mounted;
}

/** Where a board's token lives. Per base, so two boards in one browser do not
 *  overwrite each other's credential. Same key the vanilla page used, so an
 *  existing tab keeps working across the rewrite. */
export function tokenKey(base: string): string {
  return "taskops:" + base;
}

/** `?token=…` → storage, then the URL is cleaned so the credential does not sit
 *  in history or in a screenshot. Both the location and the history are
 *  parameters: this is the one piece of bootstrap that must be testable.
 *
 * Returns true when a token was adopted. */
export function bootstrapToken(
  base: string,
  storage: Storage,
  search: string,
  here: string,
  clean: (url: string) => void,
): boolean {
  const token = new URLSearchParams(search).get("token");
  if (!token) return false;
  storage.setItem(tokenKey(base), token);
  // WHERE the page is, not where `base` says the board is: a window serves the
  // page at `/` and mounts its board at `/board`, so deriving one from the
  // other sent the address bar to a path the human never asked for.
  clean(here);
  return true;
}

export function createClient(base: string, storage: Storage, env: Env = {}): Client {
  const key = tokenKey(base);

  function token(): string {
    try {
      return storage.getItem(key) ?? "";
    } catch {
      return ""; // storage denied: the page falls back to asking for a token
    }
  }

  async function rpc<T>(verb: RpcVerb, args: Record<string, unknown> = {}): Promise<T> {
    const send = env.fetch ?? globalThis.fetch;
    // /api/rpc, the address the server grew when the page took the board root
    // (http/routes.py). The bare 0.5.0 spelling still answers there, but this
    // page ships WITH its server, so it speaks the current address only — a
    // fallback would be dead code wearing a retry.
    const response = await send(base + "/api/rpc", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token(),
      },
      // No actor: the credential's own subject is the identity (http/rpc.py
      // ::rest_of). A browser that could name its actor could impersonate one.
      body: JSON.stringify({ verb, args }),
    });
    return unwrap<T>(await response.json());
  }

  async function git<T>(route: string): Promise<T> {
    const send = env.fetch ?? globalThis.fetch;
    const response = await send(base + "/api/" + route, {
      headers: { Authorization: "Bearer " + token() },
    });
    return unwrap<T>(await response.json());
  }

  function feedUrl(scheme: "ws" | "http"): string {
    const origin = env.origin ?? globalThis.location?.origin ?? "";
    const url = new URL(base + "/api/feed", origin || "http://localhost");
    if (scheme === "ws") url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.searchParams.set("token", token());
    return url.toString();
  }

  function subscribe(onSignal: () => void, onLive: (live: boolean) => void): () => void {
    const later = env.setTimeout ?? globalThis.setTimeout;
    const cancel = env.clearTimeout ?? (globalThis.clearTimeout as (id: unknown) => void);
    let stopped = false;
    let close: () => void = () => {};
    let timer: unknown = undefined;
    let attempt = 0;

    /** The one way back into the loop. Capped exponential backoff, forever —
     *  the loop has no terminal state except stop(). Every failure path ends
     *  here or in a transport that will: that is the whole fix. The header
     *  used to stick on "offline" because a dropped WS retried exactly once
     *  and a fatally-closed EventSource retried never. */
    function retry(): void {
      if (stopped) return;
      const wait = Math.min(RECONNECT_MS * 2 ** attempt, RECONNECT_CAP_MS);
      attempt += 1;
      timer = later(connect, wait);
    }

    /** A frame is a poke. `hello` counts: it is the first one, and the board may
     *  have moved between the last fetch and the socket coming up. */
    function frame(raw: string): void {
      let message: Frame = {};
      try {
        message = JSON.parse(raw) as Frame;
      } catch {
        return; // a frame we cannot parse is not a reason to stop listening
      }
      if (message.type === "change" || message.type === "hello") onSignal();
    }

    function connect(): void {
      if (stopped) return;
      const Socket = env.WebSocket ?? globalThis.WebSocket;
      if (!Socket) return events();
      const socket = new Socket(feedUrl("ws"));
      let opened = false;
      close = () => socket.close();
      socket.addEventListener("open", () => {
        opened = true;
        attempt = 0; // the transport works again: the next failure starts small
        onLive(true);
        // No poke here: the server's `hello` frame follows and frame() counts
        // it as one — a second signal would be a double refetch per recovery.
      });
      socket.addEventListener("message", (e) => frame(String((e as MessageEvent).data)));
      socket.addEventListener("close", () => {
        onLive(false);
        if (stopped) return;
        // A socket that OPENED is a working transport that dropped: come back to
        // it, with backoff. One that never opened is a proxy eating the upgrade
        // (or a server mid-restart) — try SSE, which hands back to retry() if it
        // dies too, so neither branch is a dead end any more.
        if (opened) retry();
        else events();
      });
      socket.addEventListener("error", () => {
        if (!opened) onLive(false); // `close` follows and decides what happens next
      });
    }

    function events(): void {
      if (stopped) return;
      const Stream = env.EventSource ?? globalThis.EventSource;
      if (!Stream) return retry(); // no SSE either: back to WS, later
      const source = new Stream(feedUrl("http"));
      close = () => source.close();
      source.addEventListener("open", () => {
        attempt = 0;
        onLive(true);
        // No poke here, for the same reason WS open has none: the SSE door
        // sends its own `hello` frame first (http/feed.py::_sse), and frame()
        // counts it — a signal here would be a double refetch per recovery.
      });
      source.addEventListener("message", (e) => frame(String((e as MessageEvent).data)));
      source.addEventListener("error", () => {
        onLive(false);
        if (stopped) return;
        // CONNECTING means the browser is retrying this stream itself: leave
        // it. CLOSED means it gave up for good (a non-200 while the server
        // restarts) — the old code assumed "EventSource retries itself" and
        // stayed offline forever. Close it and re-enter the outer loop.
        if (source.readyState === 2 /* EventSource.CLOSED */) {
          source.close();
          retry();
        }
      });
    }

    connect();
    return () => {
      stopped = true;
      if (timer !== undefined) cancel(timer);
      close();
      onLive(false);
    };
  }

  return {
    rpc,
    git,
    subscribe,
    token,
    setToken(value: string) {
      try {
        storage.setItem(key, value);
      } catch {
        // nothing to do: the call below will refuse and the page will say so
      }
    },
  };
}
