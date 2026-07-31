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

/**
 * The default is the two categories that are ADDRESSED AT SOMEBODY: a mention and an
 * assignment. `status` and `recovery` remain selectable and stay off.
 *
 * They were on, and the night that proved they should not be is worth the paragraph. A card
 * entering review crossed to every connected session as news, so two free developers both
 * started reviewing it and one of them worked for nothing; meanwhile the author's own session
 * received the echo of every move its agents had just made — measured at five of every six
 * events — and a feed at that ratio is one nobody reads.
 *
 * The fix is not a better status line. It is that a status change is DERIVABLE FROM STATE:
 * `taskops attention` reaches the same conclusion whenever a session looks, which is the whole
 * argument of `engine/attention.py`. What a sweep cannot derive is that somebody chose YOU —
 * a routed review, a mention, an assignment — and that is precisely what still crosses.
 */
export const DEFAULT_KINDS: readonly Kind[] = ['mention', 'assignment']

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
/**
 * The person behind an actor id: `agent:ana/w1` and `dev:ana` are one person.
 *
 * This is what makes the remote channel QUIET. Connected to the server's feed, a session
 * receives everything — including the echo of every move its own agents just made, which on a
 * measured afternoon was five of every six events. Dropping events whose dev is our own turns
 * the feed into what a channel was always supposed to be: the things OTHER people did.
 */
export function devOf(actor: string): string {
  const matched = /^(?:dev|agent):([^/]+)/.exec(actor.trim())
  return matched ? matched[1] : ''
}

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
    case 'chat':
      // Somebody typing in the board's sidebar IS an interruption addressed at this session —
      // that is the entire reason the sidebar exists. It arrives with `task: "project"`, the
      // sentinel, so nothing downstream may assume the tag names a card.
      return 'mention'
    case 'handoff':
      // Only a handoff the ORCHESTRATOR wrote (through dispatch) reads as an assignment worth
      // acting on. A manual one used to arrive as an order to spawn, sideways, into a session
      // that already had its own queue — two deciders for one question. The UI no longer
      // writes those for agents, but a teammate's CLI still can, and their bookkeeping must
      // not drive this session's fleet.
      return String(event.body.assigned_to ?? '') && event.body.dispatched === true
        ? 'assignment' : null
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
 * The devs an event is FOR. Empty means "nobody in particular", which is not the same as
 * "everybody" — see `forwards`, where the difference decides whether anything crosses.
 */
export function audience(event: BoardEvent): string[] {
  const named = event.kind === 'handoff'
    ? [String(event.body.assigned_to ?? '')]
    : [...strings(event.body, 'mentions'),
       ...(String(event.body.text ?? '').match(/(?<=^|\s)@[\w:/-]+/g) ?? [])
         .map(handle => handle.slice(1))]
  return [...new Set(named.map(devOf).filter(Boolean))]
}

/**
 * The whole inbound decision, and the ONLY function `server.ts` should ask.
 *
 * Three refusals, in the order they cost least:
 *
 * 1. **My own dev.** `dev:ana` and `agent:ana/w1` are one person, so a session hearing about
 *    what its own agents just did is hearing an echo of its own return values.
 * 2. **Already delivered.** `/api/live` bounds itself every five minutes and this client
 *    reconnects, so a replayed id is normal traffic — and a notification delivered twice is
 *    read as two things happening.
 * 3. **Not addressed to me.** An event that names an audience and leaves me out of it is
 *    somebody else's work. A `chat` line names nobody and is addressed at whoever is listening
 *    by construction — that is what the board's sidebar IS — so it crosses.
 *
 * `seen` is mutated deliberately: the caller owns the memory, so a test can hand in a fresh
 * Set and a reconnect cannot forget what it already said.
 */
export function forwards(
  kinds: readonly Kind[], event: BoardEvent, myDev: string, seen: Set<string>,
): Kind | null {
  if (myDev && devOf(event.actor) === myDev) return null
  const kind = selects(kinds, event)
  if (!kind) return null
  const to = audience(event)
  if (myDev && to.length && !to.includes(myDev)) return null
  if (event.id && seen.has(event.id)) return null
  if (event.id) seen.add(event.id)
  return kind
}

// ---------------------------------------------------------------- the review branch

/**
 * What a `→ review` line needs that the EVENT does not carry.
 *
 * The event body says `from`/`to` and who moved it; who may CLOSE the card is a field ON the
 * card, so a routed review line costs exactly one read. The read happens in `server.ts`; this
 * shape is what it hands back, and every field degrades to a harmless empty rather than
 * throwing — a channel that goes silent because a payload changed shape is worse than a
 * channel that says a little less.
 */
export type ReviewCard = {
  reviewer: string
  branch: string
  commit: string
  criteria: number
  board: string
}

/**
 * Does this notification want the card read first?
 *
 * ONLY a move into `review`. Every other event is answerable from its own body, and a channel
 * that made an HTTP call per forwarded line would turn the board's own writes into load on the
 * board.
 */
export function wantsCard(event: BoardEvent, kind: Kind): boolean {
  return kind === 'status' && event.kind === 'status' && String(event.body.to ?? '') === 'review'
}

/**
 * The three answers a `reviewer` can give.
 *
 * `human` and any `dev:` id are a PERSON — the same test `engine/_review.py` makes when it
 * refuses `done` from every agent, stated here so the message and the enforcement cannot
 * disagree. `peer` is a POLICY about who may close, not a name anybody can spawn: routing it
 * as a specialist produced the line `Spawn a \`peer\` sub-agent`, which names an agent that
 * does not exist — so it routes as the default (the stock verifier), exactly like "". Anything
 * else non-empty names a real specialist.
 */
export function reviewRoute(reviewer: string): 'human' | 'agent' | 'default' {
  const who = reviewer.trim()
  if (!who || who === 'peer') return 'default'
  if (who === 'human' || who.startsWith('dev:')) return 'human'
  return 'agent'
}

/** The specialist to spawn out of a reviewer: the bare name, or the tail of an `agent:` id. */
function specialistOf(reviewer: string): string {
  const who = reviewer.trim()
  return who.includes('/') ? who.slice(who.lastIndexOf('/') + 1) : who
}

/**
 * Read `/api/task`'s payload down to the five facts a review line says.
 *
 * Pure, so the parsing of a wire shape is tested with literals instead of with a server. The
 * criteria live in the LATEST `acceptance` event (`contracts/acceptance.py` — the newest event
 * wins, it is a statement about the card now), the branch on the lease, the commit as the last
 * one bound to the card.
 */
export function readCard(view: unknown, board: string): ReviewCard {
  const value = (view ?? {}) as {
    task?: { reviewer?: unknown }
    lease?: { branch?: unknown } | null
    commits?: { sha?: unknown }[]
    history?: { kind?: unknown; body?: Record<string, unknown> }[]
  }
  const commits = Array.isArray(value.commits) ? value.commits : []
  const history = Array.isArray(value.history) ? value.history : []
  let criteria = 0
  for (const event of history) {
    if (event?.kind !== 'acceptance') continue
    criteria = countCriteria((event.body ?? {}).criteria)
  }
  return {
    reviewer: String(value.task?.reviewer ?? ''),
    branch: String(value.lease?.branch ?? ''),
    commit: String(commits.length ? commits[commits.length - 1]?.sha ?? '' : ''),
    criteria,
    board,
  }
}

/** Criteria arrive as a list, or as one blob of lines. Never split on commas: an EARS
 *  criterion ("When X, the system shall Y") is full of them. */
function countCriteria(raw: unknown): number {
  if (Array.isArray(raw)) return raw.filter(v => String(v).trim()).length
  if (typeof raw === 'string') return raw.split('\n').filter(s => s.trim()).length
  return 0
}

/**
 * What to DO about a card that just landed in review — the sentence that was missing.
 *
 * Watched live: a specialist implemented a card, ran its tests 4/4, committed, moved it to
 * `review`, and the channel said "tk-x moved claimed → review" and stopped. Nothing was wrong
 * with the line; it simply was not an instruction, so the session read it and did nothing, and
 * the card sat in the column. A status line about a review has to route the same way the
 * assignment line already routes.
 */
function reviewInstruction(event: BoardEvent, card: ReviewCard): string {
  const branch = card.branch || `the card's branch`
  switch (reviewRoute(card.reviewer)) {
    case 'agent': {
      const name = specialistOf(card.reviewer)
      return ` Reviewed by \`${name}\`. Spawn a \`${name}\` sub-agent on this card`
        + ` (actor=agent:<dev>/${name}): read its acceptance criteria and the diff on ${branch},`
        + ` run the tests, then close it with evidence or send it back with findings.`
        + ` Do not review it in this session.`
    }
    case 'human': {
      // Stated as a STOP, because the failure mode is an agent that reads "a person should look
      // at this" as advice and closes the card anyway. The engine refuses that `done`, but a
      // refusal at the end of a wasted review is not the same as not starting one.
      const facts = [card.commit ? `commit ${card.commit.slice(0, 12)}` : '',
                     card.branch ? `branch ${card.branch}` : '',
                     `${card.criteria} criteria`].filter(Boolean).join(' · ')
      return ` NEEDS A HUMAN REVIEW (${card.reviewer}). Do not close it and do not review it`
        + ` yourself. ${facts}. Open ${card.board}/#${event.task}. Stop here and say so.`
    }
    case 'default':
      // A card that reached review needs SOMEBODY, and the stock reviewer is the one taskops
      // ships. Stating the rule without naming who fulfils it is how a card sat in review for
      // an afternoon while everyone agreed, correctly, that they were not allowed to close it.
      return ` No reviewer named — spawn a \`taskops-verifier\` sub-agent on this card`
        + ` (actor=agent:<dev>/verifier): read its acceptance criteria and the diff on`
        + ` ${card.branch || 'its branch'}, run the tests, then close it with evidence or send`
        + ` it back with findings. Do not close it as the agent that asked for the review.`
  }
}


// ---------------------------------------------------------------- the payload

/**
 * The notification payload: what Claude reads, and the tag attributes it routes on.
 *
 * Meta keys are identifiers only (letters, digits, underscore) — the client silently
 * drops anything with a hyphen, so a key that looked fine would simply vanish.
 */
export function describe(event: BoardEvent, kind: Kind, card: ReviewCard | null = null): {
  content: string
  meta: Record<string, string>
} {
  return {
    content: line(event, kind, card),
    meta: {
      card: event.task,
      event_kind: kind,
      board_kind: event.kind,
      actor: event.actor,
      event_id: event.id,
    },
  }
}

function line(event: BoardEvent, kind: Kind, card: ReviewCard | null): string {
  const who = event.actor || 'someone'
  const text = String(event.body.text ?? '').trim()
  switch (kind) {
    case 'mention': {
      // A chat line is somebody TALKING TO THIS SESSION from the board's sidebar, and it needs
      // the orchestrator rule restated. The connect-time instructions say it once; this arrives
      // mid-session, after a compaction, and the session cheerfully did the work itself the
      // first time somebody asked it to assign a card and pick a reviewer. Naming the sentinel
      // task in the prose would leak `project` into a sentence about nothing of the sort.
      if (event.kind === 'chat') {
        const about = String(event.body.card ?? '')
        return `${who} says${about ? ` (looking at ${about})` : ''}: ${text}`
          + ` — you are the ORCHESTRATOR. If this is work, put it on the board and hand it to a`
          + ` specialist from .claude/agents/ (taskops_capture or taskops_plan, then assign and`
          + ` spawn that sub-agent with actor=agent:<dev>/<name>); do not implement it here.`
          + ` Answer with the \`reply\` tool and NO card — your transcript never reaches the board.`
      }
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
          ? ` Spawn a \`${specialist}\` sub-agent and TELL IT ITS IDENTITY: it is \`${to}\``
            + ` and must pass actor=${to} on EVERY taskops_* call, not only the first —`
            + ` taskops_next task=${event.task} actor=${to}, then the same actor on update,`
            + ` capture and the rest. A call that omits it resolves to the developer's own id:`
            + ` the claim is refused, or worse it succeeds and the NEXT call cannot touch the`
            + ` card the agent itself is holding. Do not do the work in this session.`
          : ' No registered specialist in that id — handle it or dispatch as you see fit.')
    }
    case 'status': {
      const to = event.kind === 'done' ? 'done' : String(event.body.to ?? 'done')
      const from = String(event.body.from ?? '')
      return `${event.task} moved ${from ? `${from} → ` : 'to '}${to} (${who}).`
        + (text ? ` ${text}` : '')
        // Only a review routes, and only when the card could actually be read. A failed read
        // leaves EXACTLY the line this channel sent before — degraded, never absent.
        + (card && wantsCard(event, kind) ? reviewInstruction(event, card) : '')
    }
    case 'recovery':
      return `${event.task} was recovered from ${String(event.body.recovered_from)}`
        + ` and is back in the pool.${text ? ` ${text}` : ''}`
  }
}

// ---------------------------------------------------------------- the leaked markup

/**
 * Tool-call markup that corrupted mid-response and arrived as PROSE.
 *
 * A known Claude Code defect, not a taskops one:
 *   https://github.com/anthropics/claude-code/issues/66011
 *   https://github.com/anthropics/claude-code/issues/68615
 * Berna received a reply through this channel whose text ended in `</parameter></invoke>`, and it
 * was stored on the board that way — the board keeps events forever, so a transient client bug
 * became a permanent one.
 *
 * ONLY the tail is cut, and that bound is the entire design. Somebody explaining an MCP schema
 * writes `<invoke name="...">` in the middle of a sentence on purpose; a sweep over the whole
 * string would eat their example and there would be no way to write about this file. A corruption
 * always trails the answer — the model stops producing prose and starts producing tags — so the
 * end is the one place a cut is safe.
 */
const LEAKED_TAIL =
  /(?:\s*<\/?(?:antml:)?(?:invoke|parameter|function_calls|function_results)(?:\s[^<>]*)?\/?>)+\s*$/

/**
 * The reply text with any trailing tool markup removed.
 *
 * A text that is NOTHING BUT markup comes back unchanged rather than empty: an answer nobody can
 * read is bad, and an answer that never arrives while somebody waits on the board is worse.
 */
export function sanitize(text: string): string {
  const cut = text.replace(LEAKED_TAIL, '')
  if (cut === text) return text
  return cut.trim() ? cut.trimEnd() : text
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
