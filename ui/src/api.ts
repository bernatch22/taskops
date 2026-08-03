/* Every call to the server, in one place.
 *
 * One module so that a change to how errors are shaped, or how the token travels, is one edit
 * rather than a hunt through components. Components never call `fetch`. */

import type {
  Activity, AgentEntry, Board, Config, ContextSlice, ContextView, DigestStarted, Event,
  Milestone, ReportEntry, ReportFile, Task, TaskView, WireMessage,
} from "./contracts";

/* What `GET /api/milestones` answers: EVERY chapter this board has had, whatever its state, plus
 * the per-chapter card counts. An object and not a bare array, like every other payload here —
 * the rpc decoder on the Python side drops a non-object silently, and a route that answered a list
 * would be a second shape for the same idea.
 *
 * Declared HERE rather than in `contracts.ts` because it is not a shape the Python side has a
 * TypedDict for: it is this route's envelope, and the things inside it are already mirrored. */
export interface MilestoneList {
  milestones: Milestone[];
  counts: Record<string, Record<string, number>>;
}

/* The token arrives in the URL (`taskops ui` prints a link that carries it) and is kept in
 * localStorage so a reload does not lose it. Read once at module load: it cannot change without
 * a navigation, and re-reading storage per request would be a syscall on every poll. */
/* Where this board is MOUNTED. `/` under `taskops ui`, `/<project>/` under `taskops serve`,
 * which rewrites the `<base>` tag in index.html on the way out.
 *
 * Read from `document.baseURI` rather than from `location.pathname`, and that is the whole
 * point: the SPA routes in the browser, so on `/axion/task/tk-1` the path alone cannot say
 * where the mount ends and the client-side route begins. The base tag was put there by the
 * server, which is the only party that knows.
 *
 * Every request below is therefore a RELATIVE path resolved against it — including the
 * websocket, which is the one that would otherwise be forgotten and 404 under a prefix. */
const BASE = document.baseURI;

/* The leading slash is STRIPPED, and that is the load-bearing line: `new URL("/api/board", base)`
 * throws the base away — an absolute path is absolute — so a route written the obvious way would
 * work perfectly on `taskops ui` and silently escape the mount on `taskops serve`. Stripping here
 * rather than at eleven call sites means a new endpoint cannot reintroduce it. */
function url(path: string): string {
  return new URL(path.replace(/^\//, ""), BASE).toString();
}

/* The token is scoped to the mount for the same reason as everything else here: on a server
 * with several projects, one localStorage key would mean opening board B logs you out of A. */
const TOKEN = (() => {
  const key = `taskops-token:${new URL(BASE).pathname}`;
  const fromUrl = new URL(location.href).searchParams.get("token");
  if (fromUrl) localStorage.setItem(key, fromUrl);
  return fromUrl ?? localStorage.getItem(key) ?? "";
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
  const response = await fetch(url(path), { ...init, headers: headers(Boolean(init?.body)) });
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
  /* Its own call, not folded into the board: the history is the expensive read here, and the board
   * refetches on every event. Only the activity view pays for it, and only while it is open. */
  /* The standing facts and settings. Cheap and rarely changing, so the panel that shows it can
   * stay open all day — it refetches only when a `context` or `policy` event says to. */
  context: () => call<ContextView>("/api/context"),
  /* ONE card's slice — what the project has settled that reaches THAT card, which is exactly what
   * the worker holding it was injected with. Read once when a drawer opens, and never on a socket
   * event: a standing fact changes about once a week and the card is on screen for a minute. */
  taskContext: (id: string) => call<ContextSlice>(`/api/task/context?id=${encodeURIComponent(id)}`),
  /* Every chapter, including the CLOSED ones — which is the only thing this adds over
   * `/api/context`, whose slice carries the active ones and the planned titles because a reader
   * deciding something needs those and nothing else. So it is read when somebody asks to see the
   * ones that ended, not on load: a reached milestone changes never. */
  milestones: () => call<MilestoneList>("/api/milestones"),
  activity: (since: string) => call<Activity>(`/api/activity?since=${encodeURIComponent(since)}`),
  /* A CLOSED range, in epoch seconds. Separate from `activity` because a lookback cannot express
   * "last month" — it needs both ends — and because where a month starts is the CLIENT's fact: the
   * 1st at 00:00 in the timezone of whoever is looking, which the server's clock cannot know. */
  activityBetween: (from: number, to: number) =>
    call<Activity>(`/api/activity?from=${Math.floor(from)}&to=${Math.floor(to)}`),
  task: (id: string) => call<TaskView>(`/api/task?id=${encodeURIComponent(id)}`),
  reports: () => call<ReportEntry[]>("/api/reports"),
  report: (label: string) => call<ReportFile>(`/api/report?date=${encodeURIComponent(label)}`),
  /* The one call that costs money — it shells out to `claude` — and it returns IMMEDIATELY.
   *
   * It used to hold the connection open for the whole model call, which is where "aprieto
   * Generate y no hace nada" came from: minutes of a mute spinner, and a dropped request took
   * the only feedback there was with it. Now it answers "narrating" and the prose arrives on
   * the live socket. A 409 means one is already running for that report; anything else is the
   * server's own sentence, shown verbatim, because `claude` missing or logged out is a thing
   * the person can fix in a minute if they are told. */
  digest: (label: string, force: boolean) =>
    call<DigestStarted>("/api/report/digest", {
      method: "POST",
      body: JSON.stringify({ date: label, force }),
    }),
  search: (q: string) => call<Task[]>(`/api/search?q=${encodeURIComponent(q)}`),
  comment: (task: string, text: string, mentions: string[]) =>
    call<unknown>("/api/comment", {
      method: "POST",
      body: JSON.stringify({ task, text, mentions }),
    }),
  agents: () => call<AgentEntry[]>("/api/agents"),
  /* A registry NAME (the server mints `agent:<you>/<name>` from it) or a full actor id. The
   * server refuses a bare name it does not know, and its sentence names the ones it does. */
  assign: (task: string, assignee: string) =>
    call<{ task: string; assignee?: string; requested?: string }>("/api/assign", {
      method: "POST",
      body: JSON.stringify({ task, assignee }),
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
 * replaying events into a copy of it.
 *
 * `onNarration` is the exception to that rule, and deliberately so: a narration delta is NOT
 * stored anywhere, so there is nothing to refetch and the frame IS the payload. It rides this
 * socket rather than a second one because a second stream is a second subscription and a second
 * lifetime to leak, for a panel on one screen. */
export function subscribe(onChange: (event: Event) => void, onOpen: () => void,
                          onNarration: (message: WireMessage) => void = () => {}): () => void {
  const query = TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : "";
  let closed = false;
  let stop = () => {};

  const useSse = () => {
    if (closed) return;
    const source = new EventSource(url(`/api/live${query}`));
    source.addEventListener("hello", () => onOpen());
    source.addEventListener("change", (message) => {
      onChange(JSON.parse((message as MessageEvent<string>).data) as Event);
    });
    source.addEventListener("narration", (message) => {
      onNarration(JSON.parse((message as MessageEvent<string>).data) as WireMessage);
    });
    /* No manual reconnect: EventSource retries on its own, and `onOpen` refetching on every open is
     * what closes the gap a disconnection left. Our own loop on top would race with it. */
    stop = () => source.close();
  };

  const useWs = () => {
    if (closed) return;
    /* Built from the same `url()` and then switched to ws:, rather than assembled from
     * `location.host` by hand — that hand-assembled form was absolute-pathed, so it was the one
     * call in the app that would have missed the mount prefix and taken the live board with it. */
    const socket = new WebSocket(
      url(`/api/live${query}`).replace(/^http/, "ws"));
    let everOpened = false;

    socket.onmessage = (message: MessageEvent<string>) => {
      const frame = JSON.parse(message.data) as
        { type: string; event?: Event; message?: WireMessage };
      if (frame.type === "hello") onOpen();
      else if (frame.type === "change" && frame.event) onChange(frame.event);
      else if (frame.type === "narration" && frame.message) onNarration(frame.message);
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
