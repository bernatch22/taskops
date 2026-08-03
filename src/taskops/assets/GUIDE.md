# taskops — how work happens in this repository

You are reading the shared task list's manual. One document for agents and humans, on
purpose: two documents drift, and then the two audiences are told different things.

`taskops init` copies this to `.taskops/GUIDE.md`. If anything here contradicts what the
tools actually do, the tools are right and this file is a bug.

---

## The one-paragraph version

Tasks live in this repository, not in anybody's session. You **claim** one before you code,
and the claim is a lease nobody else can take. Your commits are bound to the task that
motivated them — enforced, not suggested. When you finish, whatever was waiting on your task
becomes available to everyone else automatically. Every developer's agents share the same
list, and it travels by `git push` and `git pull` with no server involved.

## The loop

```
  taskops_next ──▶  work  ──▶  git commit  ──▶  taskops_update status=review
       │                            │                     │
   a lease, the spec,          the guard adds        whatever was waiting
   and a collision             `Task: tk-…`         on you becomes ready
   warning                     for you              for everyone
```

**Start every session by finding out where you stand.** If you do not already hold a task,
call `taskops_next`. It returns the spec, the exact branch to create, the conversation so
far, and a warning listing any other agent editing the same files. If nothing is available
it tells you *why*, which is usually something you can act on.

**Work on the branch it names** — `tk/<task-id>/<slug>`. Not a branch of your own choosing:
the commit guard matches this exact shape, and an invented name gets your own commits denied.

**Commit normally.** The guard adds the `Task:` trailer. You do not write it.

**How you finish depends on what the card promised.**

- The card names a `reviewer` or carries `acceptance` criteria → `taskops_update status=review`
  with a comment saying which criterion you met and how. Somebody ELSE closes it, and this is
  ENFORCED twice: an agent cannot `done` a card that carries criteria at all, and cannot close
  a review it opened.
- It carries neither → close it yourself: `status=done` with `evidence`. Review is for work
  that promised something checkable, and there is nothing here to check against.

**If the work belongs to no card, make one — do not work around the guard.** A bug you tripped
over, a fix a reviewer asked for, a refactor the task turned out to need:

```
taskops_capture title="fix the refund timeout" spec="DONE = the retry test passes"
   → created tk-4987b6, claimed, commit on tk/tk-4987b6/fix-the-refund-timeout
```

One call: the card exists, you hold it, and the reply names the branch. Use `taskops_plan`
instead when you are decomposing into SEVERAL cards with dependencies; use this when there is
one thing and you are already doing it.

## The three rules the server enforces

These are not conventions. The server rejects the call.

**1. A commit belongs to a claimed task.** You must be on the task's branch and hold its
lease. Why: a commit nobody can attribute is a commit nobody can review against the work it
was supposed to do, and the moment one is allowed the board stops being a complete picture of
what changed.

**2. `done` requires a commit bound to the task.** Otherwise "done" means only that an agent
said so — which is exactly what a human reading a board instead of the diff is trying to
avoid. If a task legitimately produced no code (research, a decision, docs elsewhere), pass
`no_code: true` **with a comment saying what it produced instead**. That is recorded, so a
review can see which closures had no code and why.

**3. `done` on a card that carries acceptance criteria requires `evidence`.** Name which
criteria were met and what proves each — a test that passes, a command, a run. If a criterion
no longer applies, `no_evidence` takes the reason and **writes it into the event**. The exit
exists because a rule with no honest way out gets bypassed by lying, and a lie is worse than a
recorded exception.

## Your claim is a lease, not an assignment

It expires. Every taskops call you make renews it, so a task that takes an hour is fine — you
do not have to do anything special. What the deadline actually bounds is a **crash**: if your
process dies, the lease lapses within fifteen minutes and the task returns to the queue
instead of sitting there looking claimed forever.

Two consequences worth knowing:

- If a write is refused for a missing lease, **claim again**. Do not work around it. Another
  agent may genuinely have taken the task while you were gone.
- If you are out of context or out of depth, use `status: released` **with a comment** saying
  where you got to. That is the honest move and it is always allowed. Abandoning the task
  silently also works, eventually — but it throws away everything you learned.

## Talking to other agents

`taskops_update` with `mentions` puts a message in another actor's inbox:

```
taskops_update task=tk-4f2a9c
  comment="I'm rewriting the tokenizer in parser.py — hold off until I land this."
  mentions="agent:ana/api-1,dev:ana"
```

They see it within one tool call of their own, and it appears live on the board. The message
lives in the task's thread, so it is still findable in three weeks — which is why there is no
separate chat tool.

**When to use it:** the collision warning in `taskops_next` and `taskops_ask` lists other
tasks touching your files. That list is the one thing that prevents a merge conflict rather
than reporting it afterwards. Message them *before* you edit, not after the merge.

## Writing a spec that works

`taskops_plan` is where most of the damage gets done, because the reader of a `spec` is a
**fresh agent with none of your context** — possibly on another developer's machine, three
days from now.

A spec that works says:

- what **done** looks like, concretely enough to disagree with
- what must **not** change
- **where to start** — the files, the sibling to copy, the test that pins the behaviour

Better still, give the card `acceptance` — one criterion per line, in EARS:

```
WHEN a lease expires THE SYSTEM SHALL return the card to ready
WHEN a card is requeued THE SYSTEM SHALL keep the previous holder's comments
```

Lines in that shape map almost one-to-one onto test cases, which is what makes closing the card
checkable by somebody who was not you. A criterion that does not fit the shape is kept with a
warning, never rejected — prose criteria beat none.

A one-line spec is the single most common cause of an agent doing the wrong thing correctly.

Also name `files`. It is how the scheduler avoids handing two agents the same file, and it is
what the collision warning is computed from.

## Dependencies

`after` in `taskops_plan` accepts the 0-based **index** of an earlier task in the same batch,
so a whole plan lands in one call:

```json
[
  {"title": "Add the events table",  "spec": "…", "files": ["storage/_events.py"]},
  {"title": "Board reads the table", "spec": "…", "after": [0]}
]
```

Nothing polls. When a task closes, everything that was only waiting on it becomes ready
immediately, and `taskops_update` tells you what you just handed to the fleet.

If you discover a dependency mid-task, use `blocked_on` — it adds the edge **and** marks you
blocked. A dependency that lives only in a comment is one the scheduler will walk somebody
straight into.

## You do not have to be told you are the orchestrator

If you are reading a session's FIRST message, the hook already said so: `SessionStart` fires
for the main conversation only — sub-agents never see it — so the event itself proves which one
you are. It injects your role, the project's standing facts, and `attention`, before anybody
types anything.

Two more hooks close the loop, and neither is advice:

- when a worker of yours hands a card to `review`, it shows up in your `attention` — and if
  you try to end the turn with it still unverified, **Stop blocks and names it**. Nothing is
  said to the worker itself: a worker cannot spawn a sub-agent, so telling it to would just
  cost it turns.
- **your turn cannot end on a review you opened.** Stop blocks — twice, then lets you go — on
  cards your session finished and left unverified. It never blocks on work nobody started: a
  ready card is not this turn's debt.

## When there is nothing to do and others are mid-flight

Do not end the turn and do not invent a poller. Run, in the background:

```
taskops attention --wait
```

It blocks until the board wants a decision from you, prints it, and exits — keep working (or
wait on it) and sweep when it returns. A session once wrote itself a bash loop to get exactly
this; the verb exists so the next one does not have to be clever.

It wakes on MESSAGES too, and that matters more than it sounds: a review routed to you arrives
as a message, so a loop watching only card moves would sleep through the one thing somebody
chose you for.

Push instead of poll: the CHANNEL delivers the same directed events instead of you reading
them. It carries only what is addressed at you — never an echo of your own agents' moves, never
the same event twice, and no status changes at all, because those are derivable and this sweep
is where you read them. It needs the experimental flag
(`claude --dangerously-load-development-channels server:taskops-channel`) and the entry in
`.mcp.json` (`TASKOPS_CHANNEL=1 taskops init`). `--wait` needs nothing and works today. The two
are the same facts, pushed or polled — you never need both.

## If you are an ORCHESTRATOR: start every turn with `attention`

```
taskops_report kind=attention
```

One read, and it is the only one that tells you what the board is WAITING for rather than what
is on it. Five groups, in the order to act on them:

| group | what it means | what you do |
|---|---|---|
| `VERIFY` | handed to review, nobody closed it | spawn `taskops-verifier` on each |
| `RESUME` | assigned to a worker that is not running | spawn that worker, or release the card |
| `DISPATCH` | ready, unassigned, has a spec | `taskops_dispatch`, then spawn one per brief |
| `NEEDS A SPEC` | ready with nothing a worker could follow | a PERSON writes it — do not guess |
| `PARKED` | `blocked`, and nothing ever unblocks that on its own | unblock, re-plan, or cancel |

Finishing comes before starting on purpose: closing a review may unblock three cards, while a
dispatch adds a fourth thing in flight.

It writes nothing and it is safe to run in a loop, which is what makes it the right thing to run
after every batch of sub-agents returns as well as at the start. A card being worked on right now
never appears — if it is in this list, nothing is going to happen to it until you decide something.

## If you are an ORCHESTRATOR: dispatching workers

`taskops_dispatch` assigns cards, creates a git worktree per card, and hands you a **brief per
card**. It starts nothing. You then spawn ONE SUB-AGENT PER BRIEF, all in a single message so they
run in parallel — they use the session you are already in.

```
taskops_plan      →  the cards
taskops_dispatch  →  N briefs           ← nothing is running yet
your Agent tool   →  N sub-agents       ← paste one brief each, in ONE message
```

Two rules for the workers, and both are in the brief already:

- **Each works inside its own worktree** (`.taskops/trees/<id>/`), which is already checked out on
  the card's branch. A worktree is per CARD, not per agent.
- **Nobody ever runs `git switch`.** Sub-agents share the repository, so switching would move the
  branch under every other worker at once. This is the whole reason the worktree exists.

There is no detached mode and no `spawn` flag. It was removed: it opened a NEW billed session per
worker, and it could not hand that worker the specialist a project registered — the detached
process got a generic prompt and the shell's default model. A sub-agent of your session gets the
right prompt, the right model and the right tools, on the subscription already paid for.

**If a brief names an `agent_type`, spawn THAT sub-agent type.** It is the specialist this project
registered for the card's labels (see below), and it is the difference between a worker that knows
the domain and one that reads the repository from scratch.

**If you dispatch and then do not spawn**, the cards sit assigned to workers that never existed. Run
`taskops recover` to hand them back.

## When a fleet dies

Workers get killed: a session ends, a balance runs out, somebody hits ctrl-C. Their cards stay
`claimed` until their leases expire, which is fifteen minutes of a board that looks busy and is not.

```
taskops recover           # releases every card whose worker has gone quiet
taskops recover --force   # …including the ones still reporting, for a fleet that is alive and wrong
```

It clears the assignment as well as the lease — a card handed back still assigned to a dead worker is
one NOBODY can pick up, since the scheduler hides it from everyone else.

And it writes on each card what survived: commits are safe in git, and **uncommitted work is named
with its path**, because a killed agent writes before it commits. Read that before starting over.

## Reviewing: one verifier per card, and never your own work

## A review is routed to ONE of you

With `reviewer: peer` on a board where more than one developer is connected, a card entering
review is not announced — the server picks its reviewer and assigns the card to that dev: never
the author, then whoever is carrying the fewest reviews, then whoever signalled most recently.
It appears in THEIR sweep and in nobody else's, and any of their agents may claim it. If nobody
acts on it, the routing expires after half an hour and the card opens to everybody eligible
again — a nudge with a deadline, not a lock.

So if a review is in your sweep, it is yours: nobody else was told about it.

Claiming a card that is in `review` is how you say **"I am checking this"**. It takes the lease
and LEAVES the card in review, so it stops appearing in everybody else's sweep — one real card
was verified three times in parallel before that existed. Its own worker claiming it back means
the opposite (leaving the handoff to fix the findings) and lands on `claimed`.

If the card says `reviewer: peer`, the engine refuses a `done` from anybody on the AUTHOR'S
dev — `dev:ana` and `agent:ana/w1` are one person with two hands. Hand it to another
developer's session, or to a verifier they spawn.

That value is normally not typed per card: `taskops policy reviewer peer` sets what every new
card is created with. The engine still reads the CARD, so changing the policy never rewrites
who was allowed to close work planned last week.

## What this project has already decided

Before you design anything, read the standing facts:

```
taskops_context                     the objective, the decisions, the notes
taskops_context task=tk-4f2a9c      …the SLICE that applies to one card
```

Four kinds, and they are not advice:

- **objective** — what the project is chasing now. You get TWO: the project's, and your own
  developer's if they set one. If your card serves neither, say so rather than doing it well.
- **decision with no scope** — what must never break. Every agent receives every unscoped decision, always;
  there is no card whose slice leaves one out.
- **decision** — what was already decided, and *why*. This exists so you do not re-propose a
  thing that was tried and rejected. If you think a decision is wrong, argue with it in a
  comment; do not quietly do the other thing.
- **note** — standing, and neither a goal nor a rule. A habit, a warning, a thing worth
  remembering. Usually your developer's own.

You never see another developer's own facts, and that is deliberate: a slice grows by ONE
whatever the size of the team, so three people each stating an objective does not make you
read four. **You may not state one either** — an objective is what you are judged against, and
a worker that could restate it could move its own goalposts. Say it on the card with
`taskops_update`; the session that planned the work decides whether it becomes standing.

## The specialist you may be

A project can register its own agents as ordinary Claude Code subagents in `.claude/agents/*.md` — a name, a prompt, a model, a
tool list, and the `labels` of the cards that are theirs. Two consequences for you:

- **If your actor id matches one** (`agent:<dev>/collector`), a card outside your labels is
  REFUSED at the claim, naming both label sets. That is not a bug to work around: another
  specialist owns it. An explicit assignment to you always wins over this.
- **If you are an orchestrator**, the brief tells you which specialist to spawn. The registry
  is data in the repository, so it arrives with `git pull` and a teammate's new specialist is
  available to you the moment you pull.

## Reading the board

- `taskops_report attention` — what is WAITING on a decision, and the move each card needs
- `taskops_report board` — every column, who holds what
- `taskops_report standup --since 24h` — what changed, per actor, and what needs a human
- `taskops_report day` — one calendar day in full: what closed, every commit, the conversation

`taskops_report` only READS. Writing a report, and paying a model to narrate one, is a person's
call or a scheduled task's — never yours.

**Read the day before yours before you start.** A dossier is where "we tried X, it failed
because Y" survives after the session that learned it ended. Re-deriving that badly is the most
expensive thing an agent does.

## A team on a server: two words to join, and sync is nobody's job

Joining a shared board is ONE command, and it takes no argument — `.taskops/board.json` is
committed, so the clone already carries its board's address:

```
git clone <repo> && cd <repo>
taskops join
```

That is init, the git hooks, the CLAUDE CODE hooks (into the project, not a plugin), the MCP wiring, the remote, and the first pull, in one. Re-running it repairs
a clone (fresh checkouts lose their git hooks).

A clone older than that file takes the URL once — `taskops join https://server/project` — and
writes it for everybody after. Making the board in the first place is `taskops board create`,
from the repository, with nobody logging into the server.

After that, **the server IS the board** — there is no sync because there is nothing to
synchronise. Every verb that writes (plan, claim, close, assign, context) executes in the
server's store; every verb that reads answers from it. Two rules cover every failure:

- a WRITE never falls back to local: unreachable server → a refusal naming the URL. A write
  that quietly landed somewhere else would fork the board precisely when nobody is watching.
- a READ degrades to this machine's last-known cache, with a warning on stderr. Refusing to
  show your own last-known board because a server is down helps nobody.

`db.sqlite` is that cache and stays disposable: `taskops sync` refetches everything from the
server. `push`/`pull` remain only for adopting a board that predates the server.

## Multi-developer, no server

`.taskops/events.jsonl` is an append-only log, and it is **committed**. Two developers'
agents converge through `git pull`: appending to different ends of a file is the one edit git
merges without help, and every event's id is its content hashed, so importing the same event
twice does nothing.

`.taskops/db.sqlite` is a **cache** and is gitignored. It can be rebuilt from the log, so
deleting it loses nothing but live leases.

The `post-merge` hook syncs for you. Run `taskops sync` by hand any time; it is idempotent.

## Three doors, and which one is yours

```
taskops <cmd>                       a person, at a terminal. fifteen commands.
taskops_* (MCP)                     you. nine tools — this is your door.
python -m taskops.transports.hooks  git and Claude Code. never type it.
```

Yours is the MCP tools. If one of them is refused, the refusal names what to do — read it
rather than reaching for the CLI, which no longer carries `next`, `update`, `ask`, `plan` or
`log` at all. What a person types is `taskops tasks …`, and what a hook runs is the third
line, which exists only because git cannot speak MCP.

## If something looks wrong

- **"no taskops project"** — run `taskops init` in the repository root.
- **A commit was denied** — read the message; it names the branch to switch to or the task to
  claim. Do not use `--no-verify` to get around it. The `post-commit` hook will record the
  commit anyway, and you will have a commit whose task nobody agreed on.
- **`taskops_next` says nothing is ready** — read the reason. "Everything blocked" is worth
  reporting to a human; "everything claimed" means ask again shortly.
- **Hooks are not firing** — they live in `.git/hooks`, which is not tracked, so a fresh
  clone has none, and a repository set up by an older taskops has a line naming a command that
  has since moved. `taskops init` again repairs both: it chains onto hooks somebody else put
  there, and rewrites the line it wrote itself. Worth knowing why nothing warned you — every
  hook line ends in `|| true`, so a hook pointing at a command that does not exist fails
  completely silently, and commits just stop appearing on their cards.
