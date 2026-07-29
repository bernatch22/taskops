/**
 * The PURE half of the channel: what crosses into the session, and how it reads.
 *
 * Everything here is a function of its arguments — no socket, no process, no clock.
 * That is deliberate: the interesting decision this channel makes is *what not to
 * forward*, and a decision that can only be exercised by opening a websocket is a
 * decision nobody tests. `server.ts` owns the plumbing; this file owns the judgement,
 * and `events.test.ts` runs it with literals.
 */

/** One stored fact, exactly as `contracts/event.py` puts it on the wire. */
export type BoardEvent = {
  id: string
  task: string
  actor: string
  kind: string
  body: Record<string, unknown>
  ts: number
}

/** A frame off `/api/live`. The websocket envelope carries `type` — SSE's `event:` line
 *  has no equivalent on a socket, which is why the server wraps it. */
export type Frame =
  | { type: 'change'; event: BoardEvent }
  | { type: 'narration'; message: unknown }
  | { type: 'hello' }
  | { type: string; [key: string]: unknown }

/**
 * The channel's own vocabulary — NOT the board's `EventKind`.
 *
 * A person does not want to be interrupted by "a status event"; they want to be
 * interrupted by *a card that needs review*. So the selector is stated in those terms
 * and `classify` maps the log's kinds onto it. It also means `TASKOPS_CHANNEL_EVENTS`
 * stays readable, and a new board kind that belongs to an existing category needs no
 * new configuration name.
 */
export const KINDS = ['mention', 'assignment', 'status', 'recovery'] as const
export type Kind = (typeof KINDS)[number]

/** The curated default: all four. The set is small because the whole point is that it
 *  is small — a channel that relays everything trains its reader to ignore it. */
export const DEFAULT_KINDS: readonly Kind[] = KINDS

/**
 * Status transitions worth an interruption.
 *
 * `review` and `blocked` are requests for a human; `done` closes something somebody was
 * waiting on. `claimed`/`in_progress` are a worker talking to itself — real facts, and
 * exactly the kind of traffic that makes a notification channel worthless.
 */
export const LOUD_STATUSES: ReadonlySet<string> = new Set(['review', 'blocked', 'done'])

/**
 * Kinds that MUST NEVER cross, whatever the configuration says.
 *
 * `activity` is a per-keystroke heartbeat (`_types.LOCAL_ONLY_KINDS` says so on the Python
 * side). Forwarding it would put a line in the session for every tool call every agent makes.
 * It is denied here rather than merely left out of `classify`, so that a future kind added to
 * one of the four categories cannot drag it in by accident.
 */
export const NEVER: ReadonlySet<string> = new Set(['activity'])

/** A frame, or `null` if it was not JSON we understand. A channel that throws on a
 *  malformed frame drops the socket for the rest of the session. */
export function parseFrame(raw: string): Frame | null {
  try {
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object') return null
    const frame = value as Record<string, unknown>
    if (typeof frame.type !== 'string') return null
    return frame as Frame
  } catch {
    return null
  }
}

/** The event out of a frame, or `null` for anything that is not a board change —
 *  `hello`, a PING's absence of payload, and narration deltas all land here. */
export function changeOf(frame: Frame | null): BoardEvent | null {
  if (!frame || frame.type !== 'change') return null
  const event = (frame as { event?: unknown }).event
  if (!event || typeof event !== 'object') return null
  const candidate = event as Partial<BoardEvent>
  if (typeof candidate.kind !== 'string' || typeof candidate.task !== 'string') return null
  return {
    id: String(candidate.id ?? ''),
    task: candidate.task,
    actor: String(candidate.actor ?? ''),
    kind: candidate.kind,
    body: (candidate.body ?? {}) as Record<string, unknown>,
    ts: Number(candidate.ts ?? 0),
  }
}

/** The list of strings under `body[key]`, tolerating the two shapes a client produces
 *  (a list, or one comma-separated field) exactly as `api.strings` does in Python. */
export function strings(body: Record<string, unknown>, key: string): string[] {
  const raw = body[key]
  if (typeof raw === 'string') return raw.split(',').map(s => s.trim()).filter(Boolean)
  if (Array.isArray(raw)) return raw.map(v => String(v).trim()).filter(Boolean)
  return []
}

/**
 * Which category this event belongs to, or `null` for "do not interrupt anybody".
 *
 * The default answer is `null`. Every kind that crosses is named here on purpose: a
 * board that starts writing a kind this channel has never heard of stays quiet until
 * somebody decides it is worth a person's attention.
 */
export function classify(event: BoardEvent): Kind | null {
  if (NEVER.has(event.kind)) return null
  switch (event.kind) {
    case 'message':
      // A comment WITH mentions. The board makes it a `message` precisely so an inbox
      // can select on the kind — the same distinction a channel wants.
      return strings(event.body, 'mentions').length ? 'mention' : null
    case 'comment':
      // A plain comment reaches nobody's inbox; only an explicit @handle in the prose
      // makes it addressed at someone.
      return /(^|\s)@[\w:/-]+/.test(String(event.body.text ?? '')) ? 'mention' : null
    case 'handoff':
      return String(event.body.assigned_to ?? '') ? 'assignment' : null
    case 'status':
      return LOUD_STATUSES.has(String(event.body.to ?? '')) ? 'status' : null
    case 'done':
      return 'status'
    case 'released':
      // `_freeing` writes `recovered_from` on both recovery paths — a lease that went
      // quiet and a dispatch nobody spawned. A release without it is a worker handing a
      // card back on purpose, which is not an emergency.
      return String(event.body.recovered_from ?? '') ? 'recovery' : null
    default:
      return null
  }
}

/** The configured selector. Unknown names are DROPPED rather than fatal — a typo in an
 *  env var must not take the channel down — and an empty result falls back to the
 *  curated set, because "nothing selected" is never what somebody meant to type. */
export function parseKinds(csv: string | undefined): Kind[] {
  const wanted = (csv ?? '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean)
  const known = wanted.filter((k): k is Kind => (KINDS as readonly string[]).includes(k))
  return known.length ? [...new Set(known)] : [...DEFAULT_KINDS]
}

/** The decision, in one call: forward this event, or drop it. */
export function selects(kinds: readonly Kind[], event: BoardEvent): Kind | null {
  const kind = classify(event)
  return kind && kinds.includes(kind) ? kind : null
}

/**
 * The notification payload: what Claude reads, and the tag attributes it routes on.
 *
 * Meta keys are identifiers only (letters, digits, underscore) — the client silently
 * drops anything with a hyphen, so a key that looked fine would simply vanish.
 */
export function describe(event: BoardEvent, kind: Kind): {
  content: string
  meta: Record<string, string>
} {
  return {
    content: line(event, kind),
    meta: {
      card: event.task,
      event_kind: kind,
      board_kind: event.kind,
      actor: event.actor,
      event_id: event.id,
    },
  }
}

function line(event: BoardEvent, kind: Kind): string {
  const who = event.actor || 'someone'
  const text = String(event.body.text ?? '').trim()
  switch (kind) {
    case 'mention': {
      const to = strings(event.body, 'mentions')
      return `${who} mentioned ${to.join(', ') || 'you'} on ${event.task}: ${text}`
    }
    case 'assignment': {
      const to = String(event.body.assigned_to)
      const specialist = to.includes('/') ? to.slice(to.indexOf('/') + 1) : ''
      // The delegation instruction rides on the MESSAGE, not only on the server's connect-time
      // instructions: this arrives mid-session, possibly after a compaction, and an
      // orchestrator that has forgotten the rule will cheerfully do the work itself. Observed
      // exactly once, which was enough.
      return `${event.task} was assigned to ${to} by ${who}.`
        + (specialist
          ? ` Spawn a \`${specialist}\` sub-agent and TELL IT ITS IDENTITY: it must call`
            + ` taskops_next task=${event.task} actor=${to} — passing the actor is not optional,`
            + ` a sub-agent that omits it resolves to the developer's own id, is refused the`
            + ` card that was assigned to it, and wanders off into the pool. Do not do the work`
            + ` in this session.`
          : ' No registered specialist in that id — handle it or dispatch as you see fit.')
    }
    case 'status': {
      const to = event.kind === 'done' ? 'done' : String(event.body.to ?? 'done')
      const from = String(event.body.from ?? '')
      return `${event.task} moved ${from ? `${from} → ` : 'to '}${to} (${who}).`
        + (text ? ` ${text}` : '')
    }
    case 'recovery':
      return `${event.task} was recovered from ${String(event.body.recovered_from)}`
        + ` and is back in the pool.${text ? ` ${text}` : ''}`
  }
}

/** The board, compressed to what fits in a reply. The full `/api/board` payload carries
 *  every card's spec and file list; this is the shape somebody asked "where are we" about. */
export function summarize(board: unknown): string {
  const value = (board ?? {}) as {
    repo?: string
    ready?: number
    total?: number
    columns?: { status?: string; cards?: { task?: { id?: string; title?: string }; lease?: { actor?: string } | null }[] }[]
  }
  const lines = [`board ${value.repo ?? '?'} — ${value.ready ?? 0} ready of ${value.total ?? 0}`]
  for (const column of value.columns ?? []) {
    const cards = column.cards ?? []
    if (!cards.length) continue
    lines.push(`${column.status ?? '?'} (${cards.length}):`)
    for (const card of cards) {
      const held = card.lease?.actor ? ` [${card.lease.actor}]` : ''
      lines.push(`  ${card.task?.id ?? '?'}  ${card.task?.title ?? ''}${held}`)
    }
  }
  return lines.join('\n')
}
