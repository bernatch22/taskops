/* Every call to the server, in one place.
 *
 * One module so that a change to how errors are shaped, or how the token travels, is one edit
 * rather than a hunt through components. Components never call `fetch`. */

import type { Board, Config, Event, Fleet, Task, TaskView } from "./contracts";

/* The token arrives in the URL (the studio prints a link that carries it) and is kept in
 * localStorage so a reload does not lose it. Read once at module load: it cannot change without
 * a navigation, and re-reading storage per request would be a syscall on every poll. */
const TOKEN = (() => {
  const fromUrl = new URL(location.href).searchParams.get("token");
  if (fromUrl) localStorage.setItem("taskops-token", fromUrl);
  return fromUrl ?? localStorage.getItem("taskops-token") ?? "";
})();

export class ApiFailure extends Error {
  constructor(message: string, readonly code: string, readonly status: number) {
    super(message);
  }
}

function headers(json: boolean): HeadersInit {
  const out: Record<string, string> = {};
  if (json) out["Content-Type"] = "application/json";
  if (TOKEN) out["Authorization"] = `Bearer ${TOKEN}`;
  return out;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: headers(Boolean(init?.body)) });
  const text = await response.text();
  const parsed = text ? JSON.parse(text) : null;
  if (!response.ok) {
    /* The server's own message, never a generic one. Every error string in taskops names what to
     * DO about it, and replacing that with "Request failed" throws away the only useful part. */
    const failure = parsed as { error?: string; code?: string } | null;
    throw new ApiFailure(failure?.error ?? response.statusText,
                         failure?.code ?? "error", response.status);
  }
  return parsed as T;
}

export const api = {
  config: () => call<Config>("/api/config"),
  board: () => call<Board>("/api/board"),
  fleet: () => call<Fleet>("/api/fleet"),
  task: (id: string) => call<TaskView>(`/api/task?id=${encodeURIComponent(id)}`),
  search: (q: string) => call<Task[]>(`/api/search?q=${encodeURIComponent(q)}`),
  comment: (task: string, text: string, mentions: string[]) =>
    call<unknown>("/api/comment", {
      method: "POST",
      body: JSON.stringify({ task, text, mentions }),
    }),
  status: (task: string, status: string, comment: string) =>
    call<unknown>("/api/status", {
      method: "POST",
      body: JSON.stringify({ task, status, comment }),
    }),
};

/* The live feed: a WEBSOCKET, falling back to SSE.
 *
 * WS first because that is what the server prefers and what the protocol's own ping gives us — a
 * live-but-idle board is distinguishable from a dead socket, which an SSE comment cannot do. The
 * fallback is not defensive decoration: a proxy that mangles the upgrade is a real deployment, and
 * the same route serves both, so falling back costs one reconnect instead of a broken board.
 *
 * Returns the unsubscribe, so a component cannot hold a stream it has no handle to — the same reason
 * the Python bus returns its own cancel.
 *
 * `onChange` fires per event; the caller REFETCHES rather than patching state from the payload. The
 * board is a projection the server derives, so re-reading it is both simpler and more correct than
 * replaying events into a copy of it. */
export function subscribe(onChange: (event: Event) => void, onOpen: () => void): () => void {
  const query = TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : "";
  let closed = false;
  let stop = () => {};

  const useSse = () => {
    if (closed) return;
    const source = new EventSource(`/api/live${query}`);
    source.addEventListener("hello", () => onOpen());
    source.addEventListener("change", (message) => {
      onChange(JSON.parse((message as MessageEvent<string>).data) as Event);
    });
    /* No manual reconnect: EventSource retries on its own, and `onOpen` refetching on every open is
     * what closes the gap a disconnection left. Our own loop on top would race with it. */
    stop = () => source.close();
  };

  const useWs = () => {
    if (closed) return;
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${scheme}//${location.host}/api/live${query}`);
    let everOpened = false;

    socket.onmessage = (message: MessageEvent<string>) => {
      const frame = JSON.parse(message.data) as { type: string; event?: Event };
      if (frame.type === "hello") onOpen();
      else if (frame.type === "change" && frame.event) onChange(frame.event);
    };
    socket.onopen = () => { everOpened = true; };
    socket.onclose = () => {
      if (closed) return;
      /* Never opened at all → the upgrade is not getting through, so stop trying it and use SSE.
       * Opened and then closed → normal: the server recycles a stream every few minutes by design,
       * so reconnect on the same transport rather than downgrading a working one. */
      if (everOpened) window.setTimeout(useWs, 500);
      else useSse();
    };
    stop = () => socket.close();
  };

  if ("WebSocket" in window) useWs();
  else useSse();

  return () => { closed = true; stop(); };
}
