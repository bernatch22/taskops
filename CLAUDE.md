# Working in taskops

taskops is a shared task board for Claude Code agents. It is also **used to build itself**, and
that is not decoration: every rule below was written after breaking it here first.

> The agent-facing manual is `.taskops/GUIDE.md`, written by `taskops init` and kept in sync
> with the tools. This file is what a SESSION needs — the orchestrator, the one reading this.

---

## The rule that gets broken most

**Claim the card before you do the work, and close it when you ship.**

On 2026-07-29 fourteen cards sat `ready` while the work in every one of them had already been
committed. Nothing was lost, but for most of a day the board said the opposite of the truth —
which is the one thing a board exists not to do. The mechanism is simple and it was skipped:

- work done on `main` without a claim binds no commit to any card,
- so `done` has nothing to stand on and is refused,
- so the card stays `ready` and the board drifts from reality, silently.

If you are about to edit code, one of these is true. Do the matching thing:

| Situation | What to do |
|---|---|
| A card exists for it | `taskops_next task=tk-…` — claim it first |
| No card exists | `taskops_capture title=… spec=…` — creates it AND claims it in one call |
| It is several pieces with dependencies | `taskops_plan` once, with the whole tree |
| It is somebody else's specialty | dispatch it — do not do it yourself |

And when it ships: `taskops_update status=review` with what you did. Somebody else closes it.

**A card you shipped and did not close is a lie with a timestamp.** If you find yourself
closing a batch of them at the end of a day, that is the smell — you were not using the board,
you were reporting to it.

## Never leave a story dead

A card that stops being worked on must SAY so, in the card:

- out of depth or out of context → `status=released` with a comment saying where you got to
- blocked on something → `blocked_on`, which adds the edge AND marks you blocked
- it will never be done → `taskops tasks cancel <id> -m "<why>"`. There is no delete: the log
  is append-only, and cancelling keeps the reason, which is what somebody wants three weeks
  later when the same idea comes back.

Silence is the failure mode. A card nobody touched for a week reads exactly like a card
somebody is working on, and `taskops status` counts it as open.

## The orchestrator does not implement

**And it does not have to be told.** `SessionStart` states the role, the context and
`attention` before anybody types; `SubagentStop` asks for the verifier the instant a worker
hands a card over; `Stop` refuses to end a turn on a review that session opened. All three
were written after watching two live sessions do the work themselves and leave both cards dead
in `review` — because the opening injection ended with "Run taskops_next to claim one".


**Open every turn with `taskops attention`.** It is the one read that says what the board is
waiting for — reviews nobody verified, cards assigned to workers that are not running, ready work
to dispatch, and the two kinds only a person can fix. It replaced the board channel, which pushed
those same facts in as notifications: every reaction to one turned out to be idempotent and
derivable from state, so five of every six events were echoes of what this session had just done.
`docs/orchestrator.md` has the before/after.


A session that plans and dispatches is doing a different job from a session that codes, and
doing both means the plan stops being kept the moment the coding gets interesting. `.claude/agents/`
holds the specialists; `taskops_dispatch` hands them briefs; the host spawns them.

`taskops-manager` and `taskops-organiser` carry `claims: false` and the engine REFUSES their
claims. That is there because being told not to take cards did not stop it happening — twice.

**When you spawn a specialist, tell it who it is.** `actor=agent:<dev>/<name>` on EVERY
`taskops_*` call, not just the first. A sub-agent that omits it resolves to the developer's own
id, is refused the card assigned to it, and wanders off into the pool. That has cost four
debugging sessions.

## Verifying is not optional, and it is not the tests

Run the suite, then **run the thing**. Half the bugs in this repository's history passed every
test and failed the first time a human looked at them: a report that regenerated stale
narrations, a channel that adopted a UI it never started, a specialist spawned with no tools.

- `.venv/bin/ruff check . && .venv/bin/python -m pytest -q` — both, always
- `cd plugin/channel && bun test` — when the channel changed (opt-in; see `docs/orchestrator.md`)
- `cd ui && npm run build` — when the UI changed, and **commit the bundle**
- then exercise it by hand and paste the real output

**Never run a mutating diagnostic against a live project.** Running `next_task` against
`~/experiments/fake-project` to "check something" left a lease held and broke a live test run.
Scratch repos are free: `/tmp`.

## The architecture, in one screen

```
contracts/   L0 — types. Imports nothing.
engine/      pure logic: the state machine, the scheduler, replay, briefs
storage/     the ONLY place SQL exists
usecases/    one file per verb; every transport calls these and never storage
transports/  cli · mcp · hooks · http — thin, and never identical to each other
render/      pure: takes a value, returns text. No I/O, no clock, no env
```

`tests/architecture/` enforces this and it is not advisory: **≤70 code lines per module**, SQL
only in `storage/`, `render/` pure, one home for the state machine, `_clock` the only reader of
the clock. When a module will not fit, that is the invariant telling you it does two things.

`.taskops/events.jsonl` is truth — append-only, committed, content-hashed ids. `db.sqlite` is a
cache and is disposable: `taskops sync` rebuilds it. Nothing may write state that is not derived
from the log.

## Test the SEAM, not the module

Twelve bugs in three days, and **not one was a bug in the logic**. Every one lived between two
machines — client/server, clone/clone, clone/origin — and every test in the suite ran one repo,
one process, one store. That is why they were all found by a person running it.

`tests/e2e/test_the_real_topology.py` is the fix and it is deliberately the only one of its
kind: a real HTTP server on a real port, a BARE origin, two clones that ran `taskops join`, and
a card walked from plan to trunk. Eight mutations of real past bugs were fed to it and it
caught eight.

**When something breaks in a live run, ask where it lived before you fix it.** If the answer is
a seam, the test belongs there — a unit test of the same bug will pass either way, which is how
the same class came back four times.

And mutation-test the new test: break the fix on purpose and check it fails. Twice here a test
that "covered" a fix stayed green when the fix was deleted — once because the trunk was already
up to date, once because it claimed through an agent id when the failure took the dev id.

## Things that cost a day each, so you do not repeat them

- **A hook speaks to whoever its event delivers to, and no further.** `SubagentStop` injects
  into the sub-agent that stopped — a worker, with no ability to spawn anything. An ask for a
  verifier placed there had a worker spend four turns explaining it lacks the tool. Before
  writing an instruction into a hook, name the reader and check it can do the thing.
- **Pin a session's actor in the environment, never in git config.** An agent rewrote a lab
  clone's `user.email` mid-run — because this very file tells it which git identity to use —
  and a whole developer silently became somebody else. Two clones drifting to the SAME name
  would deadlock `reviewer: peer`: the only actor allowed to close would be the author.
- **Nothing that stays on one machine can be reviewed.** A card's branch is pushed when its
  worker commits, and it has to be: with `reviewer: peer`, the only person allowed to close a
  card was the only one who could not see it, and seven cards got implemented twice.
- **A root cause written by an agent in a card is a HYPOTHESIS.** One reported that "an update
  with only a comment closes the card"; it does not — the events showed one call carrying both
  a comment and `status=done`. Reproduce it before you fix it.
- **The direction nobody checks is the one where every value is the same.** `attention` sorted
  priority backwards from the day it was written, invisible until a board finally had a card
  that was not the default.
- **An instruction is not a mechanism.** Anything a model must remember across a long session
  belongs in the message that needs it, or in a guard that refuses. Prompts dissolve.
- **Two directories for one concept is three bugs.** `.taskops/agents/` mirrored into
  `.claude/agents/` needed a marker, a pruner and a name translator, and each one broke. The
  specialists are Claude Code subagents, read where they already live.
- **A project with a remote has ONE source of truth: the server.** Every write routes there
  (`/api/rpc` + the claim/update endpoints); reads degrade to the local cache with a warning.
  Five bugs in one day came from the replica thinking it was an authority. A new remote-safe
  verb is a ROW in `transports/http/_verbs.py`, not a bespoke endpoint.
- **A project is a directory whose `.taskops/` holds the LOG.** Matching on the directory made
  `~` a project, because `~/.taskops/sessions.json` is where login lives.
- **Never `python3 -m taskops…` from outside.** Console scripts (`taskops`, `taskops-hook`)
  carry their own interpreter; a bare `python3` is whatever pyenv answers.
- **Verify the argument order before writing the test.** More than one "bug" here was a
  hand-made literal that did not match the type it was standing in for.

## Releases

Never `Co-Authored-By` or generated-with trailers, in commits or PR bodies. Git identity is
`Bernardo Castro <me@bernardocastro.dev>`. PyPI is **`taskops-cli`** (the name `taskops` was
taken); the command, the import and the MCP module are all `taskops`. The plugin version in
`plugin/.claude-plugin/plugin.json` must match `__version__` — a test pins it.
