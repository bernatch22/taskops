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

## On startup

It prints the board's address on its own lines, and — only when it started the UI itself —
opens it in your browser. Adopting a server you already had running and then stealing your
focus with a new tab is the kind of helpfulness people disable, so it does not.

```
  taskops board → http://127.0.0.1:2140
```

`TASKOPS_CHANNEL_OPEN=0` turns the browser off and keeps the line.

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
claude --dangerously-load-development-channels plugin:taskops@<marketplace>   # only once published
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
| `TASKOPS_CHANNEL_EVENTS`  | `mention,assignment` | csv of `mention,assignment,status,recovery` — the last two are the firehose, off by default |
| `TASKOPS_BIN`             | `taskops`        | how to invoke the CLI (a venv path, say)            |

## What crosses, and what never does

**Only what somebody addressed at YOU.** Three refusals, in `forwards`:

1. **your own dev** — `dev:ana` and `agent:ana/w1` are one person, so a session hearing what
   its own agents just did is hearing an echo of its own return values. Measured on a live
   afternoon: five of every six events;
2. **an id already delivered** — the feed ends itself every five minutes by design and this
   client reconnects, so a replayed event is ordinary traffic and a line said twice reads as
   two things happening;
3. **an audience you are not in** — an event that names people and does not name you is
   somebody else's work. There is no exemption for naming nobody any more: the board's chat
   sidebar was exactly that, and it went because "whoever is listening" stops being one session
   the moment a board is shared. Everything that crosses is ADDRESSED.

A status change crosses **nothing** by default, and that is the correction, not an oversight.
A card entering review used to be news for everybody connected, so two free developers both
started reviewing it and one of them worked for nothing. It is now an assignment: the server
picks one connected dev (`engine/routereview.py`) and that dev gets one directed message. Every
other status move is *derivable from state* — `taskops attention` reaches the same conclusion
whenever a session looks — and forwarding a derivable fact is what makes a feed unreadable.

The categories, stated in a person's terms rather than the log's:

| category     | the board event                                          |
| ------------ | -------------------------------------------------------- |
| `mention`    | a comment that names somebody (`message` with `mentions`, or an `@handle` in a plain comment) |
| `assignment` | `handoff` — a card became yours                           |
| `status`     | a move to **review**, **blocked** or **done** — OFF by default; opt in for a firehose |
| `recovery`   | `released` with `recovered_from` — a dead worker's card came back. OFF by default; the sweep reports it |

**Never, at any setting:** `activity` (the per-keystroke heartbeat), narration deltas, socket
keepalives, `claimed` moves, commits, and every kind this channel has not been
taught. An unknown kind stays quiet rather than defaulting to loud — a newer taskops writing a
new kind will not start shouting at an older channel.

Widen or narrow it with `TASKOPS_CHANNEL_EVENTS=mention,recovery`. An unknown name in that
list is dropped rather than fatal, and an empty result falls back to the curated set: a typo
must not take the channel down or silence it. The audience and duplicate rules apply at every
setting — turning `status` on makes the channel louder, never repetitive.

## A line that ROUTES

Forwarding a fact is not the same as asking for something. Watched live: a specialist
implemented a card, ran its tests 4/4, committed, and moved it to `review` — the channel said
`tk-x moved claimed → review` and the card sat in the column, because nothing in that sentence
was an instruction. Two lines therefore carry one:

* **an assignment** names the specialist to spawn and the `actor=` it must pass on *every*
  `taskops_*` call;
* **a move into `review`**, when somebody has opted `status` back on, reads the card's
  `reviewer` field and says what to do about it. In the default set that move does not cross at
  all — the routed mention carries the same instruction, to one person.

The reviewer is a field on the CARD, not on the event, so a review — and only a review — costs
one `GET /api/task`. Three answers:

| `reviewer`                      | the line says                                                     |
| ------------------------------- | ----------------------------------------------------------------- |
| a specialist (`tester`, `agent:me/tester`) | spawn a `tester` sub-agent on this card with `actor=agent:<dev>/tester`: read the criteria and the diff on the branch, run the tests, close with evidence or send it back |
| a person (`human`, `dev:ana`)   | **NEEDS A HUMAN REVIEW** — do not close it, do not review it yourself; commit, branch, criteria count, and the board link. The session is expected to stop there. |
| empty                           | today's default, stated: anyone but the agent that asked for the review may close it |

`human` and any `dev:` id are read as a person by the same test `engine/_review.py` makes when
it refuses `done` from every agent — the message and the enforcement cannot disagree.

If that read fails (a 404, a timeout, a token problem) the line degrades to exactly the move it
always was. A channel that dropped notifications because a read timed out would be silent in
precisely the moment somebody is waiting on it. Every other status move — `blocked`, `done` —
is unchanged and costs no read.

## The tools

| tool     | what it does                                                                    |
| -------- | ------------------------------------------------------------------------------- |
| `reply`  | `POST /api/comment` — a comment on a card, with optional `mentions`. **`card` is required**: every event that reaches a session names one, and the cardless destination (the board's chat sidebar) is gone. **The only way to answer**: transcript output never reaches the board. |
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
