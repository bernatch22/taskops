import { describe as group, expect, test } from 'bun:test'

import {
  changeOf,
  classify,
  describe,
  parseFrame,
  parseKinds,
  selects,
  strings,
  summarize,
  type BoardEvent,
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
