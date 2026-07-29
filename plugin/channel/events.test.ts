import { describe as group, expect, test } from 'bun:test'

import {
  changeOf,
  classify,
  describe,
  parseFrame,
  parseKinds,
  readCard,
  reviewRoute,
  selects,
  strings,
  summarize,
  wantsCard,
  type BoardEvent,
  type ReviewCard,
} from './events.ts'

function event(kind: string, body: Record<string, unknown> = {}): BoardEvent {
  return { id: 'ev1', task: 'tk-90bd23', actor: 'dev:berna', kind, body, ts: 1 }
}

group('the frame', () => {
  test('a change frame yields its event', () => {
    const frame = parseFrame(JSON.stringify({ type: 'change', event: event('comment') }))
    expect(changeOf(frame)?.kind).toBe('comment')
  })

  test('hello and narration are not board changes', () => {
    expect(changeOf(parseFrame('{"type":"hello"}'))).toBeNull()
    expect(changeOf(parseFrame('{"type":"narration","message":{"kind":"narration.delta"}}'))).toBeNull()
  })

  test('a malformed frame is null, never a throw', () => {
    // A channel that throws on one bad frame drops the socket for the rest of the session.
    expect(parseFrame('{not json')).toBeNull()
    expect(parseFrame('"a string"')).toBeNull()
    expect(changeOf(parseFrame('{"type":"change"}'))).toBeNull()
  })
})

group('what is worth interrupting for', () => {
  test('a comment with mentions is a mention', () => {
    expect(classify(event('message', { text: 'careful', mentions: ['agent:ana/one'] }))).toBe('mention')
  })

  test('a message that reached nobody is not', () => {
    expect(classify(event('message', { text: 'careful', mentions: [] }))).toBeNull()
  })

  test('a plain comment crosses only when it names somebody', () => {
    expect(classify(event('comment', { text: 'noted' }))).toBeNull()
    expect(classify(event('comment', { text: 'ping @dev:berna' }))).toBe('mention')
  })

  test('an assignment crosses', () => {
    expect(classify(event('handoff', { assigned_to: 'agent:ana/one' }))).toBe('assignment')
  })

  test('only review, blocked and done are loud statuses', () => {
    expect(classify(event('status', { from: 'in_progress', to: 'review' }))).toBe('status')
    expect(classify(event('status', { to: 'blocked' }))).toBe('status')
    expect(classify(event('status', { to: 'in_progress' }))).toBeNull()
    expect(classify(event('status', { to: 'claimed' }))).toBeNull()
    expect(classify(event('done', { from: 'review', to: 'done' }))).toBe('status')
  })

  test('a recovery crosses, a deliberate release does not', () => {
    expect(classify(event('released', { recovered_from: 'agent:ana/one' }))).toBe('recovery')
    expect(classify(event('released', { text: 'handing it back' }))).toBeNull()
  })

  test('activity NEVER crosses, at any setting', () => {
    // The whole reason this channel is worth reading. A per-keystroke heartbeat in the
    // session trains the reader to ignore everything the channel says.
    const beat = event('activity', { summary: 'Edit src/a.py' })
    expect(classify(beat)).toBeNull()
    for (const kinds of [['mention'], ['status'], ['mention', 'assignment', 'status', 'recovery']] as const) {
      expect(selects(parseKinds(kinds.join(',')), beat)).toBeNull()
    }
  })

  test('an unknown board kind stays quiet', () => {
    expect(classify(event('astral_projection', { text: 'hi' }))).toBeNull()
    expect(classify(event('commit', { sha: 'a'.repeat(40) }))).toBeNull()
  })
})

group('the selector', () => {
  test('the default is the curated set', () => {
    expect(parseKinds(undefined)).toEqual(['mention', 'assignment', 'status', 'recovery'])
    expect(parseKinds('')).toEqual(['mention', 'assignment', 'status', 'recovery'])
  })

  test('a narrower csv narrows it', () => {
    expect(parseKinds('mention, recovery')).toEqual(['mention', 'recovery'])
  })

  test('a typo drops the name rather than the channel', () => {
    expect(parseKinds('mention,mentions,nonsense')).toEqual(['mention'])
    expect(parseKinds('nonsense')).toEqual(['mention', 'assignment', 'status', 'recovery'])
  })

  test('selects honours the configured set', () => {
    const only = parseKinds('mention')
    expect(selects(only, event('message', { mentions: ['dev:ana'], text: 'x' }))).toBe('mention')
    expect(selects(only, event('status', { to: 'review' }))).toBeNull()
  })
})

group('the payload', () => {
  test('mentions read as a sentence and route on the card', () => {
    const { content, meta } = describe(
      event('message', { text: 'careful with r.py', mentions: ['agent:ana/one'] }),
      'mention',
    )
    expect(content).toContain('agent:ana/one')
    expect(content).toContain('careful with r.py')
    expect(meta.card).toBe('tk-90bd23')
    expect(meta.event_kind).toBe('mention')
  })

  test('every meta key is an identifier', () => {
    // Keys with a hyphen are silently DROPPED by the client, so a bad key vanishes
    // instead of failing.
    const { meta } = describe(event('status', { from: 'in_progress', to: 'review' }), 'status')
    for (const key of Object.keys(meta)) expect(key).toMatch(/^[A-Za-z0-9_]+$/)
    for (const value of Object.values(meta)) expect(typeof value).toBe('string')
  })

  test('a status line names both ends of the move', () => {
    const { content } = describe(event('status', { from: 'in_progress', to: 'review' }), 'status')
    expect(content).toContain('in_progress')
    expect(content).toContain('review')
  })

  test('a recovery says who dropped it', () => {
    const { content } = describe(event('released', { recovered_from: 'agent:ana/one' }), 'recovery')
    expect(content).toContain('agent:ana/one')
  })
})

group('mentions as two shapes', () => {
  test('a list and a comma-separated string both read', () => {
    expect(strings({ mentions: ['a', ' b '] }, 'mentions')).toEqual(['a', 'b'])
    expect(strings({ mentions: 'a, b' }, 'mentions')).toEqual(['a', 'b'])
    expect(strings({}, 'mentions')).toEqual([])
  })
})

group('the board snapshot', () => {
  test('it names the counts, the cards and who holds them', () => {
    const text = summarize({
      repo: '/x',
      ready: 1,
      total: 2,
      columns: [
        { status: 'ready', cards: [{ task: { id: 'tk-1', title: 'Write the router' }, lease: null }] },
        {
          status: 'in_progress',
          cards: [{ task: { id: 'tk-2', title: 'Then the UI' }, lease: { actor: 'agent:ana/one' } }],
        },
        { status: 'done', cards: [] },
      ],
    })
    expect(text).toContain('1 ready of 2')
    expect(text).toContain('tk-1  Write the router')
    expect(text).toContain('[agent:ana/one]')
    expect(text).not.toContain('done')
  })

  test('an empty board does not throw', () => {
    expect(summarize({})).toContain('0 ready of 0')
    expect(summarize(null)).toContain('board ?')
  })
})

test('an assignment to a registered specialist asks for delegation, by name', () => {
  // The orchestrator that received "tk-b61984 was assigned to agent:me/api" and then did the
  // work itself was not disobeying — nothing in the message told it to delegate, and the
  // connect-time instructions are one compaction away from being forgotten.
  const event = {actor: 'dev:me', kind: 'handoff', task: 'tk-b61984',
                 body: {assigned_to: 'agent:me/api'}, ts: 1, id: 'x'} as BoardEvent
  const line = describe(event, 'assignment').content
  expect(line).toContain('Spawn a `api` sub-agent')
  expect(line).toContain('taskops_next task=tk-b61984')
})

test('an assignment to a plain dev asks for nothing of the sort', () => {
  const event = {actor: 'dev:me', kind: 'handoff', task: 'tk-1',
                 body: {assigned_to: 'dev:ana'}, ts: 1, id: 'x'} as BoardEvent
  expect(describe(event, 'assignment').content).not.toContain('Spawn')
})

test('the delegation line names the actor the sub-agent must use', () => {
  // Watched live: the sub-agent was spawned, called taskops_next without an actor, resolved to
  // the developer's own id, was refused the card assigned to it, followed the refusal into the
  // pool and claimed an unrelated frontend card. Every step correct, nobody had told it who it
  // was.
  const event = {actor: 'dev:me', kind: 'handoff', task: 'tk-b61984',
                 body: {assigned_to: 'agent:me/api'}, ts: 1, id: 'x'} as BoardEvent
  const line = describe(event, 'assignment').content
  expect(line).toContain('actor=agent:me/api')
})

group('a card in review routes', () => {
  // Watched live: a specialist implemented a card, ran its tests 4/4, committed, moved it to
  // `review` — and the channel said "tk-x moved claimed → review" and nothing else, so the
  // session read it and the card sat in the column. The line has to say what to DO.
  const moved = event('status', { from: 'claimed', to: 'review' })

  function card(over: Partial<ReviewCard> = {}): ReviewCard {
    return {
      reviewer: '', branch: 'tk/tk-90bd23/router', commit: 'a'.repeat(40),
      criteria: 3, board: 'http://127.0.0.1:2140', ...over,
    }
  }

  test('only a move INTO review costs a card read', () => {
    expect(wantsCard(moved, 'status')).toBe(true)
    expect(wantsCard(event('status', { to: 'blocked' }), 'status')).toBe(false)
    expect(wantsCard(event('done', { to: 'done' }), 'status')).toBe(false)
    expect(wantsCard(event('message', { mentions: ['dev:ana'] }), 'mention')).toBe(false)
  })

  test('a reviewer reads as a person, a specialist, or the default', () => {
    expect(reviewRoute('human')).toBe('human')
    expect(reviewRoute('dev:berna')).toBe('human')
    expect(reviewRoute('tester')).toBe('agent')
    expect(reviewRoute('agent:me/tester')).toBe('agent')
    expect(reviewRoute('')).toBe('default')
    expect(reviewRoute('   ')).toBe('default')
  })

  test('an AGENT reviewer asks for that sub-agent, by name and with its actor', () => {
    const { content } = describe(moved, 'status', card({ reviewer: 'tester' }))
    expect(content).toContain('Spawn a `tester` sub-agent')
    expect(content).toContain('actor=agent:<dev>/tester')
    expect(content).toContain('tk/tk-90bd23/router')
    expect(content).toContain('acceptance criteria')
    expect(content).not.toContain('HUMAN')
  })

  test('a full agent id is spawned by its tail, not by the whole id', () => {
    const { content } = describe(moved, 'status', card({ reviewer: 'agent:me/tester' }))
    expect(content).toContain('Spawn a `tester` sub-agent')
  })

  test('a HUMAN reviewer stops the session and hands over the facts', () => {
    const { content } = describe(moved, 'status', card({ reviewer: 'dev:berna' }))
    expect(content).toContain('NEEDS A HUMAN REVIEW (dev:berna)')
    expect(content).toContain('Do not close it and do not review it yourself')
    expect(content).toContain(`commit ${'a'.repeat(12)}`)
    expect(content).toContain('branch tk/tk-90bd23/router')
    expect(content).toContain('3 criteria')
    expect(content).toContain('http://127.0.0.1:2140/#tk-90bd23')
    expect(content).not.toContain('Spawn')
  })

  test('NO reviewer states the default instead of leaving it unsaid', () => {
    const { content } = describe(moved, 'status', card({ reviewer: '' }))
    expect(content).toContain('No reviewer named')
    expect(content).toContain('anyone but the agent that asked for the review')
    expect(content).not.toContain('Spawn')
  })

  test('a status event that is NOT review is unchanged', () => {
    // The regression. Every other move keeps the line it has always had, card or no card.
    const blocked = event('status', { from: 'claimed', to: 'blocked', text: 'waiting on tk-2' })
    const bare = describe(blocked, 'status').content
    expect(describe(blocked, 'status', card({ reviewer: 'tester' })).content).toBe(bare)
    expect(bare).toBe('tk-90bd23 moved claimed → blocked (dev:berna). waiting on tk-2')
    const closed = describe(event('done', { from: 'review', to: 'done' }), 'status', card())
    expect(closed.content).toBe('tk-90bd23 moved review → done (dev:berna).')
  })

  test('an unreadable card degrades to the plain move, never to silence', () => {
    // `cardOf` returns null on a 404, a timeout or a token problem.
    expect(describe(moved, 'status', null).content)
      .toBe('tk-90bd23 moved claimed → review (dev:berna).')
  })
})

group('reading the card off /api/task', () => {
  test('it picks the reviewer, the branch, the last commit and the criteria', () => {
    const facts = readCard({
      task: { id: 'tk-90bd23', reviewer: 'tester' },
      lease: { actor: 'agent:me/api', branch: 'tk/tk-90bd23/router' },
      commits: [{ sha: 'b'.repeat(40) }, { sha: 'c'.repeat(40) }],
      history: [
        { kind: 'acceptance', body: { criteria: ['one', 'two'] } },
        { kind: 'status', body: { to: 'review' } },
      ],
    }, 'http://x')
    expect(facts).toEqual({
      reviewer: 'tester', branch: 'tk/tk-90bd23/router', commit: 'c'.repeat(40),
      criteria: 2, board: 'http://x',
    })
  })

  test('the LATEST acceptance event wins', () => {
    // `contracts/acceptance.py`: rewriting the criteria is a statement about the card now.
    const facts = readCard({
      history: [
        { kind: 'acceptance', body: { criteria: ['a', 'b', 'c'] } },
        { kind: 'acceptance', body: { criteria: ['a'] } },
      ],
    }, 'http://x')
    expect(facts.criteria).toBe(1)
  })

  test('criteria as one blob split on LINES, never on commas', () => {
    // An EARS criterion — "When X, the system shall Y" — is full of commas.
    expect(readCard({ history: [{ kind: 'acceptance', body: { criteria: 'When a, b shall c\nAnd d' } }] },
                    'http://x').criteria).toBe(2)
  })

  test('a card with no lease, no commits and no criteria reads as empties', () => {
    const facts = readCard({ task: { reviewer: 'human' }, lease: null }, 'http://x')
    expect(facts).toEqual({ reviewer: 'human', branch: '', commit: '', criteria: 0, board: 'http://x' })
  })

  test('a payload of the wrong shape never throws', () => {
    expect(readCard(null, 'http://x').reviewer).toBe('')
    expect(readCard({ commits: 'nope', history: 7 }, 'http://x').criteria).toBe(0)
  })

  test('the human line survives a card with nothing but a reviewer', () => {
    const { content } = describe(event('status', { to: 'review' }), 'status',
                                 readCard({ task: { reviewer: 'human' } }, 'http://x'))
    expect(content).toContain('NEEDS A HUMAN REVIEW (human)')
    expect(content).toContain('0 criteria')
    expect(content).not.toContain('commit ')
  })
})

test('the delegation line asks for the actor on EVERY call, not only the claim', () => {
  // The second half of the same lesson. Told to pass the actor on taskops_next, a specialist
  // claimed its card correctly and then could not write to it: the update resolved to the
  // developer's id and the board answered "held by someone else" — about a lease the agent
  // itself was holding.
  const event = {actor: 'dev:me', kind: 'handoff', task: 'tk-b61984',
                 body: {assigned_to: 'agent:me/api'}, ts: 1, id: 'x'} as BoardEvent
  const line = describe(event, 'assignment').content
  expect(line).toContain('EVERY taskops_* call')
})

test('a chat message from the sidebar reaches the session', () => {
  // The sidebar exists to interrupt this session; a chat line that did not cross would be a
  // notes field. It arrives on the SENTINEL task, so nothing downstream may read the tag's
  // card attribute as a real card.
  const event = {actor: 'dev:berna', kind: 'chat', task: 'project',
                 body: {text: 'why is tk-2 still open?'}, ts: 1, id: 'x'} as BoardEvent
  expect(classify(event)).toBe('mention')
  expect(selects(parseKinds(undefined), event)).toBe('mention')
})
