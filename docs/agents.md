# Agents: specialists, orchestration, and sub-tasks

How a team of agents divides work in one repository without colliding — who invokes whom, what a
sub-task actually is, and how a project defines its own specialists.

> **taskops never invokes an agent.** It is the registry, the router and the memory. The thing that
> spawns is always the host session, with its own sub-agent tool. This is not a preference: MCP has
> a mechanism for a server to ask the client for a model call (`sampling/createMessage`), and
> **Claude Code does not implement it**. A design where the board launches work would be a design
> that does not run. What the board does instead is *answer*: it hands back a brief naming the card,
> the branch, the worktree and the specialist — and the orchestrator does the spawning.

---

## 1 · The two agents that ship with the plugin

Installed with `plugin/`, available in any project. They are the two ROLES a board needs and
nothing else — planning is not one of them, because an orchestrator is personal: it belongs in
`~/.claude/agents/`, where it can know your habits and your other repositories. taskops ships
what the BOARD requires, not what a person prefers.

| Agent | Model | Does | Deliberately cannot |
|---|---|---|---|
| `taskops-worker` | sonnet | claims, works, commits, finishes at `review` with its evidence stated | plan or dispatch — and closing its own review: `done` on a card it reviewed itself is refused by the engine |
| `taskops-verifier` | haiku | reads a card's acceptance criteria and the diff, and tries to prove `done` is FALSE | **Write** — an adversary that can edit is not an adversary |

The tool lists are the point. An agent that can do everything is an agent whose role is a
suggestion.

## 2 · Specialists your project defines

A project's own agents are **Claude Code subagents** — `.claude/agents/*.md`, exactly where they
already live, committed and shared with the team. taskops reads that directory and understands two
OPTIONAL extra keys; Claude Code ignores frontmatter it does not recognise, so one file serves both:

```markdown
.claude/agents/collector.md
---
name: collector
description: market-data ETL; knows the lake schemas
tools: [Read, Edit, Bash, taskops_next, taskops_update, taskops_capture, taskops_context]
                                 # short names are fine — materialisation qualifies them
model: sonnet
labels: [collectors, etl]        # WHICH CARDS ARE THIS AGENT'S
files: ["src/data/**"]           # its edit surface
---
You are the collector specialist. Claim your assigned card with taskops_next task=<id>.
Never widen a schema without a migration.
```

`labels` is what makes the file more than a prompt:

- **Routing.** `dispatch` matches card labels against registry labels — most shared labels wins,
  ties break alphabetically, deterministically.
- **A fence at the claim.** An actor named `agent:<dev>/collector` asking for a card outside those
  labels is **refused**, and the refusal names both sets:

  ```
  collector works on [collectors, etl]; this card carries [ui] —
  it belongs to another specialist
  ```

  That is enforcement, not context injection. A role that only appears in a prompt is a role an
  agent can ignore, and an agent that ignores it looks exactly like one that never read it.

- **An assignment beats the fence.** Labels are the routing *heuristic*; an assignment is a
  *decision*. When somebody names a specialist for a specific card, it can claim it whatever its
  labels say.

**Nothing is copied anywhere.** There was briefly a `.taskops/agents/` that taskops mirrored into
`.claude/agents/`, and every piece of that was a mistake: it needed a marker to know which copies
were safe to overwrite, a pruner for renames, and a translator because MCP tool names are spelled
differently in the two places — three bugs in an afternoon, all of them created by having two
directories instead of one. An agent that already exists in a repository just works.

A repo file with the same `name` as a plugin file **wins** — a project can replace the stock worker.

## 3 · The orchestration loop, end to end

```
you ──▶ your orchestrator (personal, ~/.claude/agents/)
          │
          ├─ taskops_context        what we are chasing, what may never break
          ├─ taskops_report board   what is open, who holds what
          ├─ taskops_plan           five cards with dependencies and EARS criteria
          └─ taskops_dispatch       → briefs: [{task, agent_type, branch, tree, brief}, …]
                │
                └─ Task(subagent_type="collector", prompt=brief)    ← the HOST spawns
                     │
                     collector ─ taskops_next task=tk-a       claims ITS card
                     collector ─ …finds the work splits…
                     collector ─ taskops_plan [{…, parent: tk-a}, {…, parent: tk-a}]
                     collector ─ taskops_dispatch             → more briefs
                     collector ─ Task(subagent_type="schema", …)   ← nests, depth 2 of 5
                     collector ─ taskops_update status=review
                                   + which criteria it met, and how
                │
                └─ taskops-verifier per review card: tries to prove it FALSE
                     ├─ holds  → taskops_update status=done evidence="…"
                     └─ fails  → findings on the card; a worker goes back on it
                     (the engine refuses `done` from whoever entered review —
                      nobody declares done on their own work; and a card whose
                      `reviewer` is `human`/`dev:…` refuses it from EVERY agent)
```

Nesting is real: Claude Code allows sub-agents to spawn sub-agents to **depth 5** (since v2.1.172,
capped at 200 per session). Recursion costs taskops nothing — a sub-agent has `taskops_plan` and
`taskops_dispatch` like anyone else, and the board sees the whole tree because every card records
its `parent`.

### Assign, don't queue

`taskops_next` with no arguments means *"give me anything"*. That is right for a pool of
interchangeable workers and wrong for specialists. `dispatch` **assigns first**: the card is bound
to the worker's actor id before anything can claim it, and from that moment **no other agent can
see it at all** — not in the pool, not by id. The worker then claims its own card with
`taskops_next task=tk-a`.

`taskops_capture title=… assign=agent:ana/collector` does the same thing for a single card.

## 4 · Sub-tasks are cards, and they get their own worktree

There is no second concept. A sub-task is a card with `parent` set — same board, same lease, same
guard, same reports. Which means a sub-task can have sub-tasks, be blocked by a sibling, and be
dispatched to a different specialist than its parent.

```python
plan(repo, [{"title": "migrate the collector", "labels": "collectors"}])
#   → tk-c55299

plan(repo, [{"title": "sub: parse the new format", "parent": "tk-c55299"},
            {"title": "sub: backfill history",     "parent": "tk-c55299"}])
#   → tk-d25679, tk-0bf8e1

dispatch(repo, tasks=("tk-d25679", "tk-0bf8e1"))
```

```sh
$ git worktree list
/tmp/repo                            43f43f5 [master]
/tmp/repo/.taskops/trees/tk-0bf8e1   43f43f5 [tk/tk-0bf8e1/sub-backfill-history]
/tmp/repo/.taskops/trees/tk-d25679   43f43f5 [tk/tk-d25679/sub-parse-the-new-format]
```

Two agents, two working trees, two branches, one board. **The lease coordinates who owns the
*card*; the worktree is what keeps their bytes apart.** Both matter and neither replaces the other:
a lease alone would let two agents write the same file, and a worktree alone would let two agents
do the same work.

Worktrees live under `.taskops/trees/`, inside the repository and gitignored. Each worker gets
`$TASKOPS_ROOT` pointing at the main checkout, so a worktree with no `.taskops/` of its own still
reads and writes the one board.

> **Granularity is a deliberate choice.** The lease is per *card*, never per file. Cursor measured
> fine-grained locking with 20 agents and watched throughput collapse to 2–3; the whole field moved
> to isolation for that reason. Coarse leases plus worktrees is the combination that scales.

## 5 · Money, and the ceiling

`dispatch` **prepares and starts nothing** by default: it assigns, makes the worktrees, and hands
back a brief per card. The orchestrator passes each brief to its own sub-agent tool, so workers run
inside the session that is already paid for.

That default is a correction, not a preference. The first version spawned `claude -p` per card — a
new billed session each time. A real fleet of six drained a balance mid-run and left six cards
claimed by processes that no longer existed. `spawn=True` still exists for genuinely detached
workers.

The cap is low on purpose: `DEFAULT_WORKERS = 3`, `MAX_WORKERS = 12`. Every worker is a model doing
unsupervised work in a repository, so a planner that miscounts should hit a refusal rather than an
invoice.

## 6 · What an agent may not do

Two rules are enforced by hooks, not by prompt:

**A commit belongs to a claimed card.** An agent holding none is refused at the git level:

```
commit blocked — `master` is not a task branch and agent:ana/w1 holds no task.
If this work belongs to a card nobody made yet, taskops_capture title=… creates it AND
claims it in one call; otherwise taskops_next picks one up. Then commit on the branch it names
```

The gate is **asymmetric**: a human's terminal commit passes untouched. A refusal reaching a person
as a failed command with no context helps nobody, and the signal is the identity (`agent:*`), not
the environment — `CLAUDECODE` is inherited by every descendant of a session, including your own
shell.

**`done` requires evidence** — a commit bound to the card, and when the card carries acceptance
criteria, which were met and what proves each. `no_evidence` takes a reason and **records it**,
because a rule with no honest exit gets bypassed by lying.

One thing nothing can stop: `git commit --no-verify` skips every git hook — and `post-commit` too,
so the commit is not merely unattributed, it is unseen. That is stated rather than papered over.

## 7 · The chat sidebar, and the activity strip

The board's chat (`⌘/Ctrl+K`) reaches whichever session is running the channel, and the session
answers with the `reply` tool. Underneath the conversation the sidebar draws a **tool strip**: one
dim line per tool call the agent makes, fed by the `activity` events the `PostToolUse` hook writes
through `usecases.track`. Those events are local-only — they never reach the committed log and the
channel refuses to forward them into a session — so the strip is the only place they are read.

**The strip is empty unless the project you are watching installs the hook.** The plugin's own
`hooks.json` covers any project that loads the taskops plugin; a project that does not (a bare
checkout, a scratch repo) emits nothing, and the sidebar will show a conversation with no visible
work behind it. The fix is project-level hooks — a Claude Code feature, `.claude/settings.json` in
the repo being worked on, committed alongside it:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write|Bash|NotebookEdit",
        "hooks": [{ "type": "command",
                    "command": "taskops-hook post-tool-use" }] }
    ]
  }
}
```

The `taskops` package has to be importable by that `python3`, and the hook attributes the call to
the card the caller currently holds — an activity event with no task is dropped rather than filed
under an empty id.
