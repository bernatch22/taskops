# taskops channel — the board talking inside your session

A [Claude Code channel](https://code.claude.com/docs/en/channels-reference) is an MCP server
that **pushes** events into an open session instead of waiting to be asked. This one bridges
the taskops board: when somebody mentions your agent, hands it a card, moves something to
review, or a dead worker's card comes back, it says so **in the session you are already in** —
and Claude can answer on the card without leaving it.

```
  a board write                 the UI                    this channel            your session
  ────────────────────────────────────────────────────────────────────────────────────────────
  comment / @mention  ─┐
  handoff (assign)     ├─▶  taskops ui  ──ws──▶  server.ts  ──filter──▶  notifications/
  review|blocked|done  │    /api/live             events.ts               claude/channel
  recovery             ─┘                                                      │
                                                                               ▼
                                                                        <channel source="taskops"
                                                                          card="tk-90bd23" …>
                                                                               │
  the card's thread  ◀── POST /api/comment ◀────  `reply` tool  ◀───────────────┘
```

## Run it

The channel is a plugin artifact, not part of the Python wheel — it needs [Bun](https://bun.sh)
and it installs its own dependency (`@modelcontextprotocol/sdk`). Nothing about the wheel's
zero-dependency rule changes.

```sh
cd plugin/channel && bun install
```

Register it as an MCP server. Either a project-level `.mcp.json`:

```json
{
  "mcpServers": {
    "taskops-channel": { "command": "bun", "args": ["./plugin/channel/server.ts"] }
  }
}
```

…and then start Claude Code naming that server, **exactly** like this:

```sh
claude --dangerously-load-development-channels server:taskops-channel
```

Or, if you loaded it through the taskops plugin (it must be an entry in the plugin's
`.mcp.json`), name the plugin instead:

```sh
claude --dangerously-load-development-channels plugin:taskops@<your-marketplace>
```

Claude Code shows a full-screen warning listing the development channels; choose **I am using
this for local development**. A dim line under the banner confirms it:
`Channels (experimental) messages from server:taskops-channel inject directly in this session`.

### The UI starts with it

On startup the channel asks `http://127.0.0.1:$TASKOPS_UI_PORT/api/config` whether a board is
already listening.

* **Something answers** — it attaches, and never kills a server it did not start.
* **Nothing answers** — it spawns `taskops ui --port <port> --repo <repo>` as a child and
  **kills it on exit**. The UI and the channel are one lifecycle.

So: *does the web server start with the plugin?* With the channel, yes.

### Configuration

| variable                  | default          | what it does                                       |
| ------------------------- | ---------------- | -------------------------------------------------- |
| `TASKOPS_UI_PORT`         | `2140`           | the board's port — the same default as `taskops ui` |
| `TASKOPS_REPO`            | the cwd          | which repository the spawned UI serves              |
| `TASKOPS_API_TOKEN`       | none             | sent as `Bearer` on writes and `?token=` on the feed |
| `TASKOPS_CHANNEL_EVENTS`  | all four         | csv of `mention,assignment,status,recovery`         |
| `TASKOPS_BIN`             | `taskops`        | how to invoke the CLI (a venv path, say)            |

## What crosses, and what never does

The filter is the point of this thing. A channel that relays everything trains you to ignore
it, so the default set is small and stated in a person's terms, not the log's:

| category     | the board event                                          |
| ------------ | -------------------------------------------------------- |
| `mention`    | a comment that names somebody (`message` with `mentions`, or an `@handle` in a plain comment) |
| `assignment` | `handoff` — a card became yours                           |
| `status`     | a move to **review**, **blocked** or **done**             |
| `recovery`   | `released` with `recovered_from` — a dead worker's card came back |

**Never, at any setting:** `activity` (the per-keystroke heartbeat), narration deltas, socket
keepalives, `claimed`/`in_progress` moves, commits, and every kind this channel has not been
taught. An unknown kind stays quiet rather than defaulting to loud — a newer taskops writing a
new kind will not start shouting at an older channel.

Narrow it with `TASKOPS_CHANNEL_EVENTS=mention,recovery`. An unknown name in that list is
dropped rather than fatal, and an empty result falls back to the curated set: a typo must not
take the channel down or silence it.

## The tools

| tool     | what it does                                                                    |
| -------- | ------------------------------------------------------------------------------- |
| `reply`  | `POST /api/comment` — a comment on a card, with optional `mentions`. **The only way to answer**: transcript output never reaches the board. |
| `board`  | the compact board snapshot: columns, cards, and who holds each one.              |

Neither spends money. There is no tool here that calls a model.

## Honest limits

* **Channels are a research preview.** Custom channels are not on Anthropic's curated
  allowlist, so this needs `--dangerously-load-development-channels` every time. Publishing it
  to a marketplace does not change that.
* **No permission relay.** `claude/channel/permission` is deliberately *not* declared. Anyone
  who can approve a tool call through a channel is only as trustworthy as that channel's
  inbound path — and this one's inbound path is "anybody who can write to the board". Declaring
  it would turn a comment into a way to approve a `Bash` call in your session.
  `test_the_channel_declares_no_permission_relay` fails if it ever appears.
* **Loopback only.** The channel talks to `127.0.0.1`. It does not open a port of its own; the
  only listener involved is the board's.
* **One session, one channel.** Events queue into the session and arrive together on the next
  turn. Two independent streams want two sessions.
* **Restart to load.** Claude Code spawns channel servers at startup, so a change to
  `server.ts` needs a restarted session. The `events.ts` logic does not — it is tested
  standalone.

## Tests

```sh
cd plugin/channel && bun test          # the filter, the payload, the snapshot — no socket
python -m pytest tests/transports/test_channel_contract.py   # the Python side it consumes
```

The split is deliberate. `events.ts` holds every judgement this channel makes and is exercised
with literals, so the interesting behaviour needs no websocket to test. What that cannot catch
is a **rename on the Python side** — `body["to"]` becoming `body["status"]`, the websocket
envelope losing its `type` — which would make the channel go quiet rather than fail. That is
what the contract test pins, from the side that would do the renaming.
