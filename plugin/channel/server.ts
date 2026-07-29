#!/usr/bin/env bun
/**
 * The taskops CHANNEL — the board talking inside an open Claude Code session.
 *
 *     board write (comment / assign / status / recovery)
 *         -> taskops ui  ws://127.0.0.1:<port>/api/live
 *             -> this server  -> notifications/claude/channel  -> the session
 *     the session -> `reply` tool -> POST /api/comment -> the card's thread
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

import { changeOf, describe, parseFrame, parseKinds, selects, summarize } from './events.ts'

const PORT = Number(process.env.TASKOPS_UI_PORT ?? 2140)
const HOST = '127.0.0.1'
const REPO = process.env.TASKOPS_REPO ?? process.cwd()
const TOKEN = process.env.TASKOPS_API_TOKEN ?? ''
const BIN = process.env.TASKOPS_BIN ?? 'taskops'
const KINDS = parseKinds(process.env.TASKOPS_CHANNEL_EVENTS)

const BASE = `http://${HOST}:${PORT}`
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
      + ' They are things a person or another agent did on the shared board: a mention, an assignment,'
      + ' a move to review/blocked/done, or a recovered card.'
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
          card: { type: 'string', description: 'The task id, e.g. tk-90bd23 (the `card` tag attribute)' },
          text: { type: 'string', description: 'What to say on the card' },
          mentions: {
            type: 'array',
            items: { type: 'string' },
            description: 'Actors to notify: agent:<dev>/<name> or dev:<name>',
          },
        },
        required: ['card', 'text'],
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
        const text = String(args.text ?? '').trim()
        if (!card || !text) throw new Error('`card` and `text` are required')
        const mentions = Array.isArray(args.mentions) ? args.mentions.map(String) : []
        const response = await fetch(`${BASE}/api/comment`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', ...auth },
          body: JSON.stringify({ task: card, text, mentions }),
        })
        const payload = await response.text()
        if (!response.ok) throw new Error(`${response.status}: ${payload}`)
        return { content: [{ type: 'text', text: `posted on ${card}` }] }
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
      announce()
      openBoard()
      return
    }
    await Bun.sleep(250)
  }
  log(`the UI did not come up on ${BASE} within 10s — events will not flow`)
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
function tail(): void {
  const url = `ws://${HOST}:${PORT}/api/live` + (TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : '')
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
    const kind = selects(KINDS, change)
    if (!kind) return
    void mcp.notification({
      method: 'notifications/claude/channel',
      params: describe(change, kind),
    })
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

await ensureUi()
tail()
