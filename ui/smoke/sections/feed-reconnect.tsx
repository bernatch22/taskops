/* The feed's reconnect loop has no dead ends — tk-7c9fc9.
 *
 * Two ways the header used to stick on "offline" until a manual refresh:
 * a WS that had opened retried exactly ONCE after its drop, and an
 * EventSource that died fatally (readyState CLOSED) was assumed to retry
 * itself and never did. This section drives `subscribe`'s state machine
 * through fake transports and a fake clock — all injected through `Env`,
 * which is the seam client.ts exists to provide — and pins:
 *   (a) open → drop → failed retries → success ends LIVE, backoff growing;
 *   (b) a WS that never opens falls to SSE;
 *   (c) SSE fatal → back into the WS loop → live — the exact old dead-end;
 *   (d) every recovery fires exactly one refetch signal;
 *   (e) unsubscribe mid-backoff leaves no pending timer and no transport. */
import { createClient } from "../../src/client";
import type { Env } from "../../src/client";
import type { Check, Fixture, Harness } from "./section";

/** Index into the fakes with a real error instead of `undefined` — strict TS. */
function nth<T>(arr: T[], i: number): T {
  const x = arr[i];
  if (x === undefined) throw new Error("no fake #" + i);
  return x;
}

interface Listener {
  (e: unknown): void;
}

class FakeSocket {
  listeners: Record<string, Listener[]> = {};
  closed = false;
  constructor(public url: string) {}
  addEventListener(type: string, fn: Listener): void {
    (this.listeners[type] ??= []).push(fn);
  }
  emit(type: string, e: unknown = {}): void {
    for (const fn of this.listeners[type] ?? []) fn(e);
  }
  open(): void {
    this.emit("open");
  }
  message(data: string): void {
    this.emit("message", { data });
  }
  close(): void {
    this.closed = true;
    this.emit("close"); // a real WebSocket fires `close` for a local close too
  }
  drop(): void {
    this.emit("close"); // the network's close, not ours
  }
}

class FakeStream extends FakeSocket {
  readyState = 0; // CONNECTING
  override close(): void {
    this.closed = true; // EventSource fires no event on a local close
  }
  fatal(): void {
    this.readyState = 2; // CLOSED — the browser gave up
    this.emit("error");
  }
}

interface Timer {
  fn: () => void;
  ms: number;
  cleared: boolean;
  fired: boolean;
}

/** One isolated run of the machine: fresh fakes, fresh clock, fresh client. */
function rig(withSse: boolean) {
  const sockets: FakeSocket[] = [];
  const streams: FakeStream[] = [];
  const timers: Timer[] = [];
  const live: boolean[] = [];
  let signals = 0;
  const env: Env = {
    origin: "http://board.test",
    WebSocket: class extends FakeSocket {
      constructor(url: string) {
        super(url);
        sockets.push(this);
      }
    } as unknown as typeof globalThis.WebSocket,
    // spread, not `EventSource: undefined` — exactOptionalPropertyTypes
    ...(withSse
      ? {
          EventSource: class extends FakeStream {
            constructor(url: string) {
              super(url);
              streams.push(this);
            }
          } as unknown as typeof globalThis.EventSource,
        }
      : {}),
    setTimeout: (fn, ms) => {
      const t: Timer = { fn, ms, cleared: false, fired: false };
      timers.push(t);
      return t;
    },
    clearTimeout: (id) => {
      (id as Timer).cleared = true;
    },
  };
  const storage = { getItem: () => "tok", setItem: () => {} } as unknown as Storage;
  const stop = createClient("/board", storage, env).subscribe(
    () => {
      signals += 1;
    },
    (isLive) => live.push(isLive),
  );
  const flush = (): void => {
    const t = timers.find((x) => !x.cleared && !x.fired);
    if (t) {
      t.fired = true;
      t.fn();
    }
  };
  const pending = (): Timer[] => timers.filter((x) => !x.cleared && !x.fired);
  return {
    sockets,
    streams,
    timers,
    live,
    signals: () => signals,
    stop,
    flush,
    pending,
  };
}

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* (a) + (d) — a working WS drops, retries fail, a later one succeeds. */
  {
    const r = rig(false); // no SSE in this env: the loop must survive on WS alone
    const ws1 = nth(r.sockets, 0);
    ws1.open();
    ws1.message('{"type":"hello"}');
    check("a: the first open goes live and hello pokes once", r.live.at(-1) === true && r.signals() === 1);
    ws1.drop();
    r.flush(); // retry 1: never opens
    nth(r.sockets, 1).drop();
    r.flush(); // retry 2: never opens
    nth(r.sockets, 2).drop();
    r.flush(); // retry 3: opens
    const ws4 = nth(r.sockets, 3);
    ws4.open();
    ws4.message('{"type":"hello"}');
    const waits = r.timers.map((t) => t.ms);
    check(
      "a: backoff grows across failed retries",
      waits.length === 3 && waits[0] === 500 && waits[1] === 1000 && waits[2] === 2000,
      JSON.stringify(waits),
    );
    check("a: a later attempt ends LIVE", r.live.at(-1) === true);
    check("d: that recovery poked exactly once (the hello)", r.signals() === 2);
    // opening reset the backoff: the NEXT drop starts the ladder over
    ws4.drop();
    check("a: success resets the backoff to 500ms", r.timers.at(-1)?.ms === 500);
    r.stop();
  }

  /* (b) — a WS that never opens is a proxy eating the upgrade: SSE, at once. */
  {
    const r = rig(true);
    nth(r.sockets, 0).drop();
    check("b: a never-opened WS falls to SSE with no timer", r.streams.length === 1 && r.pending().length === 0);
    nth(r.streams, 0).open();
    check("b: the SSE open goes live and pokes once", r.live.at(-1) === true && r.signals() === 1);
    r.stop();
  }

  /* (c) — the exact chain that used to dead-end:
   * open → drop → retry fails → SSE → SSE fatal → back to WS → live. */
  {
    const r = rig(true);
    nth(r.sockets, 0).open();
    nth(r.sockets, 0).message('{"type":"hello"}');
    nth(r.sockets, 0).drop();
    r.flush(); // retry: never opens → SSE
    nth(r.sockets, 1).drop();
    const sse = nth(r.streams, 0);
    sse.fatal(); // readyState CLOSED: the browser gave up for good
    check("c: a fatal SSE re-enters the loop instead of staying dead", r.pending().length === 1);
    check("c: the fatal stream was closed, not abandoned", sse.closed);
    r.flush(); // back to WS
    const ws3 = nth(r.sockets, 2);
    ws3.open();
    ws3.message('{"type":"hello"}');
    check("c: the loop ends LIVE after the old dead-end chain", r.live.at(-1) === true);
    check("d: exactly one poke per recovery — SSE never opened, hello counts", r.signals() === 2);
    r.stop();
  }

  /* still-CONNECTING SSE errors are the browser's own retry: hands off. */
  {
    const r = rig(true);
    nth(r.sockets, 0).drop(); // never opened → SSE
    nth(r.streams, 0).emit("error"); // readyState 0: EventSource retries itself
    check(
      "an SSE error while CONNECTING schedules nothing — the browser owns it",
      r.pending().length === 0 && r.streams.length === 1 && !nth(r.streams, 0).closed,
    );
    r.stop();
  }

  /* (e) — unsubscribe mid-backoff kills the timer and the transport. */
  {
    const r = rig(false);
    nth(r.sockets, 0).open();
    nth(r.sockets, 0).drop(); // a retry timer is now pending
    check("e: the drop left a timer pending", r.pending().length === 1);
    r.stop();
    check("e: stop cleared the pending timer", r.pending().length === 0);
    r.timers.forEach((t) => {
      if (!t.fired && !t.cleared) t.fn();
    });
    check("e: nothing reconnects after stop", r.sockets.length === 1);
    check("e: the transport is closed", nth(r.sockets, 0).closed);
    check("e: stop reports offline", r.live.at(-1) === false);
  }
}
