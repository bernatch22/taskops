# The orchestrator runs the board. The channel was the doorbell.

A design note written after running both, not before. It compares the flow as it works today
(channel on) with the flow as it should be (orchestrator only), names the one case the channel
genuinely covered, and recommends the cut.

---

## 1. The cast, so the diagrams read

```
YOU            the human. Types into ONE Claude Code session, or clicks the board UI.
ORCHESTRATOR   that session. Plans, assigns, dispatches, spawns, closes. Decides EVERYTHING.
organiser      ~/.claude/agents/organiser.md — turns an intention into cards. Never holds one.
worker         plugin/agents/taskops-worker.md — claims ONE card, codes on its branch, hands over.
verifier       plugin/agents/taskops-verifier.md — sonnet, read-only, checks EARS criteria, closes.
ENGINE         the taskops Python package. Guards, leases, the state machine. Refuses; never asks.
CHANNEL        plugin/channel/server.ts — tails the UI's websocket, pushes board events INTO
               the open session as <channel …> tags. This is the piece under review.
```

And the one fact that decides the whole question:

> **The channel never decided anything.** `events.ts` is pure — it classifies, filters and
> describes. Every write on the board is either the engine refusing something or the
> orchestrator asking for it. So removing the channel removes NOTIFICATIONS, not control.

---

## 2. BEFORE — the flow with the channel on

```
 YOU ──"build the board and do it"──▶ ORCHESTRATOR
                                          │
                                          ├─▶ Agent(organiser)  ──▶ taskops_plan (6 cards, wired)
                                          │        ◀── card ids, order, "start with tk-a"
                                          │
                                          ├─▶ taskops_dispatch count=2
                                          │        engine: assign tk-a → agent:berna/w1
                                          │                assign tk-b → agent:berna/w2
                                          │                worktree + branch + brief each
                                          │
                                          ├─▶ Agent(taskops-worker, brief tk-a)   ┐ in parallel
                                          └─▶ Agent(taskops-worker, brief tk-b)   ┘
                                                   │
        ┌──────────────────────────────────────────┘
        │  worker w1: taskops_next task=tk-a  → lease
        │             code · commit on tk/tk-a/…  (git hook binds commit ↔ card)
        │             taskops_update status=review  → lease released, assignee kept
        │
        ▼
   .taskops/events.jsonl ──▶ taskops ui ──ws /api/live──▶ CHANNEL ──▶ session
                                                              │
   and the session receives, DURING ITS OWN TURN:             ▼
        <channel event_kind=claimed  actor=agent:berna/w1>      ← echo of its own dispatch
        <channel event_kind=claimed  actor=agent:berna/w2>      ← echo
        <channel event_kind=review   actor=agent:berna/w1>      ← echo — the worker's return
                                                                   value ALREADY said this
        <channel event_kind=done     actor=taskops-verifier>    ← echo — it spawned the verifier
```

Measured on one ordinary afternoon: **six events crossed, one was news.** The five echoes are
not free — each one is a mid-turn interruption the model must read, classify as "that was me",
and discard. An instruction says "ignore your own echoes"; an instruction is not a mechanism,
and twice the session answered an echo as if somebody had asked.

There is a second cost, structural: the channel makes the review handoff LOOK asynchronous —
worker moves the card, event fires, session reacts, spawns verifier — when the session was the
one that spawned the worker and is sitting on its return value. The event arrives to tell it
something it already knows, one second later, through a websocket, a filter, and an MCP
notification. Three moving parts (UI server lifecycle, ws reconnect-every-5-min, event filter)
to deliver an intra-process fact.

## 3. AFTER — orchestrator only

Same afternoon, no channel. Every arrow that used to be an event is now a **return value**.

```
 YOU ──"build the board and do it"──▶ ORCHESTRATOR
                                          │
                       PLAN               ├─▶ Agent(organiser) ──▶ taskops_plan
                                          │        ◀─ "6 cards; tk-a first, it unblocks 3"
                                          │
                       ASSIGN             ├─▶ taskops_dispatch count=2
                                          │        ◀─ two briefs, agent_type routed per labels
                                          │
                       EXECUTE            ├─▶ Agent(worker, tk-a) ┐ parallel; each claims its
                                          │─▶ Agent(worker, tk-b) ┘ own card, codes, commits
                                          │        ◀─ "tk-a → review: criteria 1,2 met, ran X"
                                          │        ◀─ "tk-b → review: criterion 1 met"
                                          │
                       VERIFY             ├─▶ Agent(taskops-verifier, tk-a) ┐ parallel again
                                          │─▶ Agent(taskops-verifier, tk-b) ┘
                                          │        ◀─ "tk-a: 3/3 hold → closed done"
                                          │        ◀─ "tk-b: criterion 2 fails → bounced,
                                          │            assignee kept, comment says why"
                                          │
                       LOOP               ├─▶ Agent(worker, tk-b)   the bounce goes round again
                                          │─▶ taskops_dispatch      tk-a's children just unblocked
                                          │        … until the tree is done or blocked on YOU
                                          │
                       REPORT             └─▶ "4 done, 1 in review, tk-f blocked on a decision"
```

What holds it together is **not** the orchestrator remembering to do things. Every "must" in
this loop is a mechanism that fires without anyone's memory:

```
 forgotten claim      → git pre-commit hook REFUSES the commit on main / off-branch
 forgotten close      → Stop + SubagentStop hooks: "you hold tk-b" blocks the turn end (≤2×)
 self-certification   → engine: agent + acceptance criteria → only review, never done
 own review           → engine: you opened it, you cannot close it
 dead worker          → lease TTL 900 s, `taskops recover` for the impatient
 orchestrator coding  → organiser carries claims:false; the engine refuses its claims
```

The orchestrator can be lazy, interrupted, or compacted mid-run, and the board still cannot
lie — that was always the design; the channel just sat on top of it.

## 4. Side by side

```
                          BEFORE (channel)              AFTER (orchestrator only)
 who decides              orchestrator                  orchestrator        (unchanged)
 review handoff           event → react → spawn         return value → spawn
 echoes per cycle         ~5                            0
 moving parts             engine + UI + ws + filter     engine              (UI stays, mute)
 UI lifecycle             coupled to the session        `taskops ui` when you want it
 mid-turn interruptions   every kept event              none
 human clicks UI          event, instantly              seen at next turn / next status
 remote dev pushes        event, instantly              seen at next `taskops sync` + report
 recover at 3am           event, instantly              seen at next turn
 org policy needed        channelsEnabled: true         nothing
 flag to run it           --dangerously-load-…          nothing
```

The right column's three "seen at next turn" rows are the entire price. Which brings us to:

## 5. The one valuable use case — and what actually covers it

The channel earned its keep in exactly one scenario: **events the orchestrator did not cause.**
A remote dev's card landing in review. You rejecting a card from the UI. `recover` freeing a
fleet at 3am. Multi-machine, multi-writer, nobody typing — the prod board.

But look at what the reaction to each of those events IS:

```
 event nobody caused          the reaction               needs a LIVE push?
 remote card → review         spawn a verifier           no — next sweep finds it in review
 human reject from the UI     re-dispatch to its worker  no — next sweep finds the bounce
 recover freed six cards      re-dispatch the ready ones no — next sweep finds them ready
```

**Every reaction is idempotent and state-based.** None of them needs the event — they need the
STATE, and the state is one `taskops report` away. A sweep at the top of every orchestrator
turn ("anything in review unassigned? anything bounced? anything freed?") covers all three with
zero new machinery, because `dispatch`, the verifier spawn and the bounce loop already exist.
Latency goes from ~1 s to "whenever the orchestrator next runs" — and for the prod board, where
no session is open anyway, the channel never worked either: a doorbell in a house with nobody
home. What prod needs is a session that WAKES UP (cron / scheduled task) and sweeps — which is
the same sweep.

That is the honest verdict on the channel: it optimised the latency of a reaction that did not
need to be fast, in the one deployment (laptop, you present) where you were the trigger anyway,
and it was structurally absent in the deployment (prod) that motivated it.

## 6. What was built

All four recommendations below, in one change. The sweep is `taskops attention` (`taskops_report
kind=attention` for agents): one read, five groups, `verify` first because finishing beats
starting. It writes nothing — that is the line between it and `recover`, and a test pins it.

Two things the implementation found that this note had wrong, both by writing the test first:

- **A cancelled dependency is not a dead end.** `unblock` counts `cancelled` as closed and frees
  the card the next time anything runs. The real hole was one status up: `unblock` only scans
  `backlog` and `ready`, so a card parked with `blocked_on` sits there until a person moves it —
  the failure this project already named "never leave a story dead".
- **A parked card keeps its lease.** Only `ready`, `review`, `done` and `cancelled` release one,
  so a worker that had just declared itself blocked went on looking busy for the fifteen minutes
  until the TTL ran out. `blocked` is therefore judged BEFORE the lease: an agent saying "I am
  blocked on this" is saying it is not working on it, whatever its lease still claims.

The channel is opt-in behind `$TASKOPS_CHANNEL=1` and `taskops setup --channel`. Nothing was
deleted.

## 7. Recommendation

1. **Cut the channel from the default path.** No `--channels` flag in `taskops setup`, no
   channel lifecycle coupled to the UI. The code moves to a branch or stays as an opt-in the
   README stops advertising — it is 1 200 tested lines whose one real job now has a cheaper owner.
2. **The sweep replaces the doorbell.** Orchestrator sessions open with `taskops report` and
   act on state: unverified reviews → spawn verifiers; bounces → re-dispatch; freed cards →
   dispatch. Prod gets the same sweep on a schedule instead of a resident session.
3. **The UI decouples and stays.** `taskops ui` on demand, read-and-comment, one lifecycle of
   its own. It was never the channel's child; the channel was its parasite.
4. **Nothing else moves.** Every guard in §3 predates the channel and is what actually keeps
   the board honest. The channel's removal deletes notifications, and notifications were the
   part that lied by interruption.
