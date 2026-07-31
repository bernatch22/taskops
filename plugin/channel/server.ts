#!/usr/bin/env bun
/**
 * The taskops CHANNEL — the board talking inside an open Claude Code session.
 *
 *     board write (comment / assign / status / recovery)
 *         -> taskops ui  ws://127.0.0.1:<port>/api/live
 *             -> this server  -> notifications/claude/channel  -> the session
 *     the session -> `reply` tool -> POST /api/comment -> the card's thread
 *                              (or /api/chat, when there is no card to answer on)
 *
 * Three decisions are worth stating, because they are the ones a reader will question:
 *
 * **The UI and the channel are ONE lifecycle.** If nothing is listening on the port, this
 * spawns `taskops ui` as a child and kills it on the way out. The alternative — telling the
 * user to remember to start a server in another terminal — makes the channel silently dead
 * most of the time, and a notification channel that is dead half the time is worse than none.
 * If a UI is ALREADY listening, this attaches to it and never kills what it did not start.
 *
 * **Almost nothing crosses.** The filter lives in `events.ts` and is tested with literals.
 * Heartbeats and activity never cross at any setting.
 *
 * **No permission relay.** Anyone who can write to this channel could then approve tool use
 * in the session, and this channel's inbound side is "anybody who can write to the board".
 * `claude/channel/permission` is therefore NOT declared, and that is a security decision
 * rather than an omission.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js'

import {
  changeOf,
  describe,
  devOf,
  forwards,
  parseFrame,
  parseKinds,
  readCard,
  sanitize,
  summarize,
  wantsCard,
  type ReviewCard,
} from './events.ts'

const PORT = Number(process.env.TASKOPS_UI_PORT ?? 2140)
const HOST = '127.0.0.1'
const REPO = process.env.TASKOPS_REPO ?? process.cwd()
const BIN = process.env.TASKOPS_BIN ?? 'taskops'
const KINDS = parseKinds(process.env.TASKOPS_CHANNEL_EVENTS)

/**
 * REMOTE MODE — the shape this channel was always reaching for.
 *
 * With a remote, the board lives on a server and the interesting events are the ones OTHER
 * machines cause: the other developer's worker handing a card over, their verifier closing
 * one, a recovery freeing work at 3am. So the channel connects to the SERVER's live feed
 * (`remote.json` already carries the address and the bearer), spawns nothing, owns no port,
 * and drops every event caused by this machine's own dev — measured once at five echoes per
 * one piece of news. Local mode (spawn `taskops ui`, tail it) survives for boards with no
 * remote, where the only writers ARE local.
 */
function readRemote(repo: string): { url: string; token: string } | null {
  try {
    const parsed = JSON.parse(
      require('fs').readFileSync(`${repo}/.taskops/remote.json`, 'utf-8'))
    if (typeof parsed?.url === 'string' && parsed.url) {
      return { url: parsed.url.replace(/\/+$/, ''), token: String(parsed.token ?? '') }
    }
  } catch { /* no remote: local mode */ }
  return null
}

const REMOTE = readRemote(REPO)
const MY_DEV = devOf(process.env.TASKOPS_ACTOR ?? '')
const TOKEN = REMOTE?.token ?? process.env.TASKOPS_API_TOKEN ?? ''

const BASE = REMOTE ? REMOTE.url : `http://${HOST}:${PORT}`
const auth: Record<string, string> = TOKEN ? { authorization: `Bearer ${TOKEN}` } : {}

function log(message: string): void {
  // stderr, never stdout: stdout IS the MCP transport.
  process.stderr.write(`taskops-channel: ${message}\n`)
}

// ---------------------------------------------------------------- the MCP server

const mcp = new Server(
  { name: 'taskops', version: '0.2.0' },
  {
    capabilities: {
      experimental: { 'claude/channel': {} },
      tools: {},
      // NOT 'claude/channel/permission' — see this file's header.
    },
    instructions:
      'Board events arrive as <channel source="taskops" card="tk-..." event_kind="..." actor="...">.'
      + ' Every one of them is ADDRESSED AT YOU by somebody else: a mention, a review routed to'
      + ' your dev, a card assigned to one of your agents. Nothing else crosses — no echoes of'
      + ' your own moves, nothing twice, and no status changes, because those are derivable and'
      + ' `taskops attention` is where you read them. So an event here is never FYI: it is work'
      + ' chosen for you, and if you do not act on it nobody else will.'
      + ' YOU ARE THE ORCHESTRATOR, NOT THE WORKER. When a card is assigned to `agent:<dev>/<name>`'
      + ' and `<name>` is a specialist this project registered (an ordinary Claude Code subagent'
      + ' in `.claude/agents/`), DELEGATE: spawn a sub-agent of THAT type with the card id'
      + ' and let it claim the card itself with `taskops_next task=<id>`. Do not do the work in this'
      + ' session — that is the whole point of a project defining specialists. Only when no'
      + ' specialist matches, or the event is a question addressed to you, answer it yourself.'
      + ' To answer on the card, call the `reply` tool with the `card` from the tag — your transcript'
      + ' output never reaches the board. Call `board` for the current snapshot before deciding what'
      + ' to pick up. Routine heartbeats are filtered out, so anything that arrives here is worth reading.',
  },
)

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'reply',
      description:
        'Post a comment on a taskops card. This is the only way to answer a board event —'
        + ' text in the transcript never reaches the board. Pass `mentions` to put it in'
        + ' someone\'s inbox.',
      inputSchema: {
        type: 'object',
        properties: {
          card: { type: 'string', description: 'The task id, e.g. tk-90bd23 (the `card` tag attribute). OMIT it to answer in the board\'s chat sidebar, which is where a message that named no card came from' },
          text: { type: 'string', description: 'What to say on the card' },
          mentions: {
            type: 'array',
            items: { type: 'string' },
            description: 'Actors to notify: agent:<dev>/<name> or dev:<name>',
          },
        },
        required: ['text'],
      },
    },
    {
      name: 'board',
      description: 'The current board: every column, its cards, and who holds each one. Read-only.',
      inputSchema: { type: 'object', properties: {} },
    },
  ],
}))

mcp.setRequestHandler(CallToolRequestSchema, async req => {
  const args = (req.params.arguments ?? {}) as Record<string, unknown>
  try {
    switch (req.params.name) {
      case 'reply': {
        const card = String(args.card ?? '').trim()
        // Sanitised HERE, at the only door into the board. A leaked tool tag (see `sanitize`)
        // would otherwise be stored as a permanent fact on a card, and the board never forgets.
        const text = sanitize(String(args.text ?? '').trim()).trim()
        if (!text) throw new Error('`text` is required')
        // No card, no comment: a chat message named none, and answering it on whatever card
        // was last mentioned would file a conversation under work it is not about. The board's
        // sidebar is where that reply belongs, and it is the only place the asker is looking.
        const mentions = Array.isArray(args.mentions) ? args.mentions.map(String) : []
        const [route, body] = card
          ? ['/api/comment', { task: card, text, mentions }]
          : ['/api/chat', { text, source: 'session' }]
        const response = await fetch(`${BASE}${route}`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', ...auth },
          body: JSON.stringify(body),
        })
        const payload = await response.text()
        if (!response.ok) throw new Error(`${response.status}: ${payload}`)
        return { content: [{ type: 'text', text: card ? `posted on ${card}` : 'sent to the chat' }] }
      }
      case 'board': {
        const response = await fetch(`${BASE}/api/board`, { headers: auth })
        if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`)
        return { content: [{ type: 'text', text: summarize(await response.json()) }] }
      }
      default:
        return { content: [{ type: 'text', text: `unknown tool: ${req.params.name}` }], isError: true }
    }
  } catch (err) {
    return {
      content: [{ type: 'text', text: `${req.params.name}: ${err instanceof Error ? err.message : err}` }],
      isError: true,
    }
  }
})

await mcp.connect(new StdioServerTransport())

// ---------------------------------------------------------------- the UI, as a child

/** Is a taskops UI already answering on the port? `/api/config` is the cheapest read that
 *  exists and is the one endpoint that never touches the database. */
async function listening(): Promise<boolean> {
  try {
    const response = await fetch(`${BASE}/api/config`, {
      headers: auth,
      signal: AbortSignal.timeout(700),
    })
    // 401 still means "a taskops is there" — it is a token problem, not an absent server.
    return response.ok || response.status === 401
  } catch {
    return false
  }
}

let child: ReturnType<typeof Bun.spawn> | null = null

async function ensureUi(): Promise<void> {
  if (await listening()) {
    log(`attached to the UI already on ${BASE}`)
    await newConversation()
    announce()
    return
  }
  log(`starting ${BIN} ui --port ${PORT} (${REPO})`)
  child = Bun.spawn([BIN, 'ui', '--port', String(PORT), '--repo', REPO], {
    stdin: 'ignore',
    stdout: 'ignore',
    stderr: 'inherit',
    // Do NOT let the child outlive us: the UI we started is ours to stop.
    onExit(_proc, code) {
      child = null
      log(`the UI exited (${code})`)
    },
  })
  for (let attempt = 0; attempt < 40; attempt++) {
    if (await listening()) {
      await newConversation()
      announce()
      openBoard()
      return
    }
    await Bun.sleep(250)
  }
  log(`the UI did not come up on ${BASE} within 10s — events will not flow`)
}

async function newConversation(): Promise<void> {
  // A session opening onto the last one's conversation is a session reading somebody else's
  // argument. This channel IS the session's MCP server — born with it, dead with it — so its
  // startup is exactly when a new conversation begins, and nothing else has to know.
  // Nothing is deleted: the previous conversation stays in the log, it stops being shown.
  try {
    await fetch(`${BASE}/api/conversation`, {method: 'POST', headers: auth})
  } catch {
    // A board that would not open one is a board that shows a longer history. Never fatal.
  }
}

function announce(): void {
  // Loud on purpose, and on its own lines. This is the one thing somebody starting a session
  // actually wants from us — an address they can click — and a URL buried in a log line among
  // startup chatter is a URL nobody sees.
  process.stderr.write(`\n  taskops board → ${BASE}\n\n`)
}

function openBoard(): void {
  // Only when WE started the UI. Adopting a server somebody already had running and then
  // stealing their focus with a new tab is the kind of helpfulness people disable.
  // TASKOPS_CHANNEL_OPEN=0 turns it off for anyone who disagrees.
  if ((process.env.TASKOPS_CHANNEL_OPEN ?? '1') === '0') return
  const opener = process.platform === 'darwin' ? 'open'
    : process.platform === 'win32' ? 'explorer' : 'xdg-open'
  try {
    Bun.spawn([opener, BASE], {stdin: 'ignore', stdout: 'ignore', stderr: 'ignore'})
  } catch {
    // A machine with no browser is a machine that reads the line above. Never fatal.
  }
}

function stopUi(): void {
  if (!child) return
  const dying = child
  child = null
  try {
    dying.kill()
  } catch {
    /* already gone */
  }
}

for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP'] as const) {
  process.on(signal, () => {
    stopUi()
    process.exit(0)
  })
}
process.on('exit', stopUi)

// ---------------------------------------------------------------- the live feed

/**
 * Tail `/api/live` forever, forwarding what the filter keeps.
 *
 * The reconnect is not optional: the feed ENDS ITSELF every five minutes by design
 * (`live.MAX_TICKS` — a parked generator cannot notice a departed client, so the server
 * bounds the resource instead). A client that treated a close as fatal would go quiet after
 * five minutes and look like a filter that was working.
 */
/**
 * The one read a routed review costs: who may close this card, on what branch, at what commit.
 *
 * The reviewer is a field on the CARD and the event only says where it moved, so the line that
 * tells a session what to do about a review cannot be written from the event alone. `/api/task`
 * is the endpoint the board already serves for exactly this — the same base, the same token as
 * every other call in this file.
 *
 * A failure returns `null` and the line falls back to the plain move it always was. A channel
 * that dropped notifications because a read timed out would be silent in precisely the moment
 * somebody is waiting on it.
 */
async function cardOf(task: string): Promise<ReviewCard | null> {
  try {
    const response = await fetch(`${BASE}/api/task?id=${encodeURIComponent(task)}`, {
      headers: auth,
      signal: AbortSignal.timeout(2000),
    })
    if (!response.ok) return null
    return readCard(await response.json(), BASE)
  } catch {
    return null
  }
}

/** Every event id already delivered, so a reconnect cannot say the same thing twice.
 *  Session-lived, like the session it speaks into — there is nothing to bound. */
const delivered = new Set<string>()

function tail(): void {
  const wsBase = REMOTE ? REMOTE.url.replace(/^http/, 'ws') : `ws://${HOST}:${PORT}`
  const url = `${wsBase}/api/live` + (TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : '')
  let socket: WebSocket
  try {
    socket = new WebSocket(url)
  } catch {
    setTimeout(tail, 2000)
    return
  }
  socket.addEventListener('open', () => log(`following ${url} for [${KINDS.join(', ')}]`))
  socket.addEventListener('message', event => {
    const change = changeOf(parseFrame(String(event.data)))
    if (!change) return
    // Echo, duplicate and not-addressed-to-me all refused in one place — see `forwards`. The
    // echo check used to be here and to apply only in remote mode; a local board with two
    // clones has exactly the same echoes, and one of them is what a session's own agent did.
    const kind = forwards(KINDS, change, MY_DEV, delivered)
    if (!kind) return
    void (async () => {
      const card = wantsCard(change, kind) ? await cardOf(change.task) : null
      void mcp.notification({
        method: 'notifications/claude/channel',
        params: describe(change, kind, card),
      })
    })()
  })
  socket.addEventListener('close', () => setTimeout(tail, 1000))
  socket.addEventListener('error', () => {
    try {
      socket.close()
    } catch {
      /* the close handler reconnects */
    }
  })
}

if (REMOTE) {
  log(`remote mode: following ${BASE} as ${MY_DEV || 'an unfiltered reader'}`)
  process.stderr.write(`\n  taskops board → ${BASE}\n\n`)
} else {
  await ensureUi()
}
tail()
