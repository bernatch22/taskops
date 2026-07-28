# The exchange API — remote sync over HTTP

The wire contract between two taskops installations. Written down because a client codes
against it from another repository: the shapes below are frozen, and a rename here is a break
nobody in this repository can see.

Served by `taskops ui` / `taskops serve` under the same `Policy` as the board — the token
applies, and `--readonly` refuses `POST /api/sync` and `PUT /api/report/file` by METHOD, before
any handler runs.

Implementation: `transports/http/exchange.py` → `usecases/exchange.py` (events) and
`usecases/reportfile.py` (report files); `transports/http/agentapi.py` → `usecases/claim.py`
and `usecases/update.py` (agent writes). No transport touches storage or the engine.

## Events

```
POST /api/sync   {"events": [Event, ...]}
  → 200 {"accepted": <how many were NEW here>, "max_seq": <this server's cursor>}
  → 400 {"error": "events[7] is not an event — …", "code": "bad_request"}

GET  /api/sync?after=<seq>&limit=<n≤500>
  → 200 {"events": [Event, ...], "max_seq": <cursor>, "more": <bool>}
```

* **Ids are kept verbatim.** A pushed event is relayed through `engine.log.relay`, which does
  not recompute the id. The id IS the content hash, so recomputing it would fork history the
  moment a newer taskops serializes a body field this one does not. The trust boundary is the
  token, not the arithmetic.
* **`accepted` is the idempotency signal.** Pushing the same batch twice answers `0` the second
  time. That is what a client logs, and it is how a person tells a retry from a double import.
* **At most 500 events per push**, and a batch is coerced entirely before anything is written —
  a malformed event at index 40 leaves nothing stored and names its index in the 400.
* **`LOCAL_ONLY_KINDS` (`activity`) is filtered in BOTH directions.** Outbound because a
  per-tool-call heartbeat would add thousands of rows a day to something whose value is that a
  human can read it; inbound because a server does not trust a client to have remembered.
* **`after` is a cursor in THAT SERVER's sequence.** `seq` is local order, not identity — which
  is why no `seq` appears inside an event on the wire. A client keeps one cursor **per remote**
  and may never compare or mix two. `max_seq` is the last seq the page *scanned* (not the last
  returned), so filtered rows are not re-scanned forever. `more` means the page came back full.

## Agent writes — the claim, decided here

```
POST /api/next     {"actor", "session"?, "labels"?, "task"?}
  → 200 NextResult          {"claim": Claim | null, "reason", "ready", "working", "blocked"}
  → 400 {"error": "`actor` is required — …", "code": "bad_request"}

POST /api/update   {"task", "actor", "status"?, "comment"?, "mentions"?, "blocked_on"?,
                    "no_code"?}
  → 200 UpdateResult        {"task": Task, "unblocked": [Task], "notified": [actor]}
  → 4xx/409 the typed error, verbatim: {"error", "code"}
```

Both bodies are the `TypedDict` the use case returns, serialized as-is — there is no schema
layer, exactly as with the board's endpoints.

**Why these exist.** Replication makes two boards converge; it does not make a claim safe.
Between two syncs, two agents on two machines both see a card `ready` and both take it, because
each grants a lease in its own sqlite. The engine already wins that race *inside one database* —
two INSERTs on one primary key. So the fix is a PLACE, not an algorithm: when a project has a
remote, `next` and `update` execute in the server's store, and the race becomes the race the
engine already wins. `tests/e2e/test_agentwire.py` races two projects through one real server.

**The routing lives in the use cases**, not in a transport: the CLI, the MCP tools and the local
board all call `next_task`/`update`, and a client that claimed safely through one surface and
unsafely through another would be worse than no feature at all.

* **`actor` travels in the body and is ACCEPTED here** — unlike `POST /api/comment`, which
  resolves it server-side. This is a deliberate trust decision and not an oversight: the server
  has neither the calling machine's `$TASKOPS_ACTOR` nor its git config, so it *cannot* learn who
  is calling. **The project token is the trust boundary**: whoever holds it may act as any actor
  in the project — the same boundary git already draws, where whoever can push can author a
  commit under any name. What is still enforced is the SHAPE: a malformed id is a 400 from
  `engine.identity.parse`, so a typo cannot conjure a ghost identity to file work under.
* **The server never routes to itself.** These endpoints call the use cases with `local=True`,
  always. Without it, a `remote.json` sitting in the store a server happens to serve would make
  it POST its own claims to that address — to itself, forever. A test plants exactly that file.
* **The client pulls after every remote write, and a failed pull fails the call.** The commit
  guard, `brief` and every render read the LOCAL board, so a claim the server granted and the
  local board has never heard of is a lease the agent's own tooling then denies. A half-success
  is worse than an error naming the network.
* **Offline never falls back to a local claim.** A remote-configured project whose server is
  unreachable raises `unreachable` (502), naming the URL and saying that no local claim was made.
  That silent fallback *is* the collision these endpoints exist to prevent.
* **Writes, so `--readonly` refuses both by METHOD** before any handler runs.

Out of scope on purpose: `plan`, `dispatch` and `ask` stay local. `ask` reads a board that
already converges through `pull`, and remote planning is rare enough to wait for a real need.

## Report files

```
GET /api/report/file?label=<label>
  → 200 {"label", "content", "max_seq": <the stamp in line 1, or -1>}
  → 404 {"code": "no_such_report"}

PUT /api/report/file   {"label", "content", "force": <bool>}
  → 200 {"stored": true}
  → 409 {"code": "report_conflict", "ours": <seq>, "theirs": <seq>, "error": "<what is lost>"}
```

`label` is a filename in `.taskops/reports/` — `2026-07-28`, `2026-07-22..2026-07-28`, `all`.
Anything with a path separator in it is a 400.

### Why this one has a rule instead of a union

Events merge by union: they are facts about the past. A report does not. Its dossier is
regenerable — it is a rendering of the log — but its **narration is not**: prose a model wrote
once, or a person edited by hand, with no second copy anywhere. So the exchange is built to
fail loud rather than to be clever.

The PUT rule, in the order it is applied:

1. The server has no such file → **store**.
2. Byte-identical to what we have → **store** (a no-op, so a re-sync is quiet).
3. Both sides carry a stamp and theirs is **higher** → **store**. A higher `max_seq` means that
   copy was generated over more of the log: the later account of the same day.
4. Anything else → **409**, carrying both stamps. This covers theirs being older, the two being
   equal but different, and **either side being unstamped** — an unstamped file was written or
   edited outside taskops, which is exactly the copy nobody may clobber. "Unknown coverage" is
   not "less coverage".

`force: true` skips to storing. The 409's `error` says what would be lost, so the person
choosing has the sentence in front of them.

**The server never regenerates.** `GET` serves the bytes it holds and 404s when it holds none.
Regenerating belongs to the machine that owns the store: a regeneration here would replace
somebody's prose with a fresh dossier and report success. It is also why the 404 matters — a
client handed a freshly generated dossier would believe there is something here to lose.

### The honest limit of comparing stamps

`max_seq` is each sqlite's own numbering, so two machines' stamps are **not rigorously
comparable**. In the real flow they are close enough to be useful: a report is narrated against
ONE store, and after a sync the server's seqs dominate. Rule 3 is therefore a heuristic for
"who saw more of the log", not a proof.

The pathological case — two independent narrations of the same day, on two machines that never
synced — has no correct automatic answer, and it lands in rule 4 every time. That is the point:
the 409 is the honest result, and `force` is the valve for the human who knows which one
mattered.
