# taskops, step by step

Every command a new user runs, in order, with what you should see. Nothing here is aspirational —
if a step does not do what it says, that is a bug worth reporting.

Follow it top to bottom the first time. **Part 1** gets one developer working in ten minutes.
Parts 2–5 add the live board, a second agent, a second developer, and the team deployment.

---

## Part 0 — Install

You need Python 3.10+ and git. Node is only needed if you want to change the UI.

```sh
# From a checkout (what you have now):
cd ~/taskops
uv venv --python 3.12          # or: python3 -m venv .venv
uv pip install --group dev -e .   # or: pip install -e . && pip install pytest ruff mypy pyright
```

Check it:

```sh
.venv/bin/taskops --version
```

```
0.1.0
```

**Put it on your PATH** so you can type `taskops` from any repository:

```sh
export PATH="$HOME/taskops/.venv/bin:$PATH"     # add this to ~/.zshrc
```

From here on, every example assumes plain `taskops`.

---

## Part 1 — One developer, one agent

### 1.1 Initialise a repository

`cd` into a git repository you actually work in. (If you want to try it on something disposable,
`mkdir /tmp/try && cd /tmp/try && git init`.)

```sh
taskops init
```

```
created taskops project at /Users/you/your-repo
hooks installed: post-commit, post-checkout, post-merge

Register the MCP server with:
  claude mcp add taskops -- python3 -m taskops.transports.mcp
```

What just happened:

| Created | What it is |
|---|---|
| `.taskops/events.jsonl` | The event log. **Commit this.** It is the only tracked file, and it is how teammates sync. |
| `.taskops/db.sqlite` | The local cache. Gitignored — rebuildable from the log. |
| `.taskops/GUIDE.md` | The manual agents read. Gitignored: it is generated, and `init` rewrites it every run so it always matches the installed version. |
| `.git/hooks/post-commit` etc. | Bind commits to tasks. Chained onto any hooks you already had. |
| A block in `.gitignore` | Ignores everything above except the log. |

`taskops init` is safe to re-run, and re-running is how you **repair a fresh clone** — `.git/hooks`
is not tracked, so a clone starts with none.

> If it says `.git/hooks does not exist — not a git repository yet`, run `git init` first, then
> `taskops init` again. Everything else still works; you just get no automatic commit recording.

### 1.2 Connect Claude Code

```sh
claude mcp add taskops -- python3 -m taskops.transports.mcp
```

Then, to get the hooks and the `/taskops:*` skills as well:

```sh
claude plugin install ~/taskops/plugin
```

Restart Claude Code and confirm it is connected:

```
/mcp
```

You should see `taskops` listed with 5 tools.

### 1.3 Plan some work

Ask Claude, in plain language:

> Read the auth module and plan the work to add refresh tokens. Use taskops.

It will call `taskops_plan` and you will see something like:

```
# planned 3 task(s)

| id        | title                          | pri | after     |
|-----------|--------------------------------|-----|-----------|
| tk-4f2a9c | Add the refresh token table    | 2   | —         |
| tk-8b31d0 | Issue refresh tokens on login  | 2   | tk-4f2a9c |
| tk-2e7f11 | Rotate on use                  | 2   | tk-8b31d0 |

1 ready to start now
```

Or do it yourself from the terminal:

```sh
echo '[
  {"title": "Add the refresh token table",
   "spec": "Migration plus the model. Done when a token round-trips through the store with an expiry. Do not touch the existing session table.",
   "files": ["db/migrations", "models/token.py"]},
  {"title": "Issue refresh tokens on login",
   "spec": "Return one alongside the access token. Done when the login test asserts both.",
   "files": ["auth/login.py"],
   "after": [0]}
]' | taskops plan -
```

**Read the last line.** If it says `⚠ NOTHING is ready`, your `after` references have a cycle or an
off-by-one, and no agent will be able to start. Fix it now rather than wondering later.

### 1.4 Let an agent claim and work

> Claim the next task and start on it.

Claude runs `taskops_next` and gets back the spec, the branch to create, and a warning if another
agent is in the same files:

```
# tk-4f2a9c — Add the refresh token table

Claimed. Create the branch and work there:

    git switch -c tk/tk-4f2a9c/add-the-refresh-token-table

## ◐ claimed · priority 2 · held by agent:you/main

### Spec

Migration plus the model. Done when a token round-trips…

### Blocking 1 task(s)

- tk-8b31d0 — Issue refresh tokens on login
```

You can do the same yourself:

```sh
taskops next
```

### 1.5 Commit — and watch the enforcement work

Create the branch it named, then commit normally:

```sh
git switch -c tk/tk-4f2a9c/add-the-refresh-token-table
git add -A && git commit -m "Add the refresh token table"
```

Either way, the commit is now bound to the task:

```sh
taskops ask tk-4f2a9c | grep -A2 Commits
```

```
### Commits (1)

- 8133e1614a72
```

**Two mechanisms bind it, and which one you get depends on where you commit:**

| Where | What binds it |
|---|---|
| Inside Claude Code, plugin installed | The `PreToolUse` hook **rewrites** the agent's command to add a `Task: tk-4f2a9c` trailer. The agent never types it. |
| A plain terminal | No trailer — nothing is intercepting your shell. The **branch name** binds it, and `post-commit` records it. |

The trailer matters because a branch name does not survive a squash or a rebase onto main, which is
the normal end of a branch's life. If you commit from a terminal and want the durable binding, add
it yourself — `git commit -m "…" -m "Task: tk-4f2a9c"` — or just let the agent commit.

**Now try to break it.** On a branch that belongs to no task:

```sh
git switch -c random-branch
taskops guard commit --message "sneaky"; echo "exit=$?"
```

```
taskops: commit blocked — `random-branch` is not a task branch. You hold 1 task(s) —
switch to one of tk/tk-4f2a9c/… (taskops_ask gives the exact branch name)
exit=2
```

Inside Claude Code that refusal reaches the **agent** as text it can act on, and the commit never
runs. Exit 2 is what Claude Code reads as "deny".

Note that `taskops guard` on its own does **not** stop a determined `git commit` in your terminal —
nothing hooks your shell, and a `pre-commit` hook was deliberately not installed (a refusal there
reaches a human as a failed command with no context). The enforcement is on the agents, which is
where the volume is.

### 1.6 Close it

> Mark it done.

```sh
taskops update tk-4f2a9c --status done --comment "Table and model landed; expiry is a column, not a job."
```

```
tk-4f2a9c → done

Unblocked 1 task(s):
- tk-8b31d0 — Issue refresh tokens on login
```

**Try closing something with no commits** and see the guard that makes the board trustworthy:

```
taskops: tk-8b31d0 has no commit bound to it. Commit your work (the guard adds the trailer),
or pass no_code with a comment if this task legitimately produced none
```

For research or a decision that produced no code:

```sh
taskops update tk-8b31d0 --status done --no-code \
  --comment "Decided against rotation-on-use; reasoning in the thread."
```

### 1.7 See where things stand

```sh
taskops report board        # every column, who holds what
taskops report standup      # what changed in 24h, and what needs a human
taskops report fleet        # which agents are alive right now, on what file
taskops ask tk-4f2a9c       # one task in full
taskops ask "refresh"       # search titles and specs
```

---

## Part 2 — The live board

```sh
taskops studio
```

```
taskops studio → http://127.0.0.1:2140/  (/Users/you/your-repo)
```

Open it. The board updates **by itself** as agents work — no refresh button, and no polling from
your side. The dot in the top right ticks green on every event.

What you can do there:

- **Click any card** for the full task: spec, dependencies, commits, the conversation, and a
  warning listing other tasks touching the same files.
- **Reply in the thread.** Add actor ids under "notify" (`agent:ana/api-1`) and it reaches that
  agent's inbox within one of its tool calls. This is a human talking to somebody's agent through
  the same channel the agents use — there is no separate mechanism for people.
- **Change a status**, including `released` to hand a stuck task back to the queue.
- **Watch the fleet panel.** A member marked `SILENT` still holds a claim but has gone quiet. That
  is the row worth acting on, which is why it is shown rather than hidden.

Useful flags:

```sh
taskops studio --port 3000
taskops studio --readonly              # for a screen in a room: refuses every write
taskops studio --host 0.0.0.0 --token "$(openssl rand -hex 16)"
```

With `--token`, open the URL the studio prints — it carries the token, and the page remembers it.

> **Why SSE and not WebSocket:** the channel only ever pushes, the engine is deliberately
> synchronous, SSE needs no dependency, and it goes through nginx with no upgrade handling.
> `src/taskops/transports/http/live.py` has the full argument.

---

## Part 3 — Two agents at once

This is what taskops is actually for. Open **two** Claude Code sessions in the same repository.

Give each one an identity so the board can tell them apart:

```sh
# terminal 1
export TASKOPS_ACTOR="agent:you/api"
# terminal 2
export TASKOPS_ACTOR="agent:you/ui"
```

Now tell both: *claim the next task and start.* You will see:

- **They never get the same task.** The claim is one `INSERT` on one primary key; SQLite settles
  it. (Tested with 50 threads: exactly one winner.)
- **They avoid each other's files.** A task whose `files` overlap what a live agent is editing
  sorts last, behind everything else, regardless of priority.
- **They can talk.** From one session:

  ```
  taskops_update task=tk-8b31d0
    comment="I'm changing the token model in models/token.py — hold off until I land it."
    mentions="agent:you/ui"
  ```

  The other agent sees it on its **next tool call**, and it appears live on the board.

- **A crash does not strand work.** Kill a session with `ctrl-C`. Within fifteen minutes its lease
  expires and the task returns to the queue — no cleanup, no stuck card. (Every taskops call an
  agent makes renews its lease, so the timeout bounds a *crash*, not a slow task.)

### What the hooks do for you

Once the plugin is installed, every session gets this without asking:

| Hook | What happens |
|---|---|
| `SessionStart` | The agent starts knowing what it holds and who messaged it. |
| `PreToolUse` on Bash | A commit with no claim is denied; a valid one gets the trailer injected. |
| `PostToolUse` | New messages are delivered; activity appears in the fleet panel. |
| `Stop` | The session posts a summary to each task it holds — a standup nobody wrote. |

---

## Part 4 — A second developer

No server. The event log travels in git.

**Adopt it in this order.** ONE person runs `taskops init` first and commits, because init touches
`.gitignore` — if two people create that file independently in a repo that had none, git refuses to
merge them. Everyone else clones or pulls, *then* runs `taskops init` (which they need anyway, for
the hooks).

```sh
# you, first
taskops init
taskops sync
git add .gitignore .taskops/events.jsonl
git commit -m "taskops: adopt the shared task list"
git push
```

```sh
# your teammate, after pulling your commit
git pull
taskops init        # their hooks; safe, and it touches nothing tracked
taskops report board
```

From then on it is just git:

```sh
# you
taskops sync && git add .taskops/events.jsonl && git commit -m "taskops: plan the token work" && git push
```

```sh
# them
git pull            # the post-merge hook runs `taskops sync` for them
taskops report board
```

They now see your tasks, and their agents will not start the ones yours claimed. Their agents'
comments come back to you the same way.

**Why there are never conflicts:** the log is append-only with content-hash ids. Appending to
different ends of a file is the one edit git merges without help, and importing the same event
twice does nothing. Events are facts about the past, so the union of two logs *is* the correct log.

If the log ever looks wrong, the cache is disposable:

```sh
rm .taskops/db.sqlite && taskops sync      # rebuilt from the log
```

> Live cross-machine messaging (rather than at `git pull` speed) needs the relay, which is designed
> in `PLAN.md` §9 and **not built**. Today, two developers converge when they push and pull.

---

## Part 5 — Putting the board on a screen

The studio binds to loopback by default. To share it:

```sh
taskops studio --host 0.0.0.0 --port 2140 --readonly --rate-limit 120
```

Behind nginx:

```nginx
location / {
    proxy_pass http://127.0.0.1:2140;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;

    # The live feed needs these two. Without them nginx buffers the stream and the board
    # updates in lumps whenever the buffer fills, which looks exactly like a broken board.
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

Use `--readonly` for anything on a wall: a shared display should not be able to close somebody's
task, and a passer-by should not be able to post as an agent.

---

## Reference

### Commands

```
taskops init [--no-hooks]                  create .taskops/, install the git hooks
taskops next [--labels x] [--task tk-…]    claim work
taskops update <task> [--status …] [--comment …] [--mentions …] [--blocked-on …] [--no-code]
taskops ask <task-id | text>               read one task, or search
taskops plan <file.json | ->               create tasks from JSON
taskops report [board|standup|fleet] [--since 24h]
taskops studio [--port 2140] [--host] [--token] [--readonly] [--rate-limit]
taskops sync                               reconcile with the committed log
taskops inbox                              messages waiting for you
```

Hook-invoked (you rarely type these): `guard`, `ingest`, `brief`, `checkout`, `track`, `hook`.

### Statuses

```
backlog ──▶ ready ──▶ claimed ──▶ in_progress ──▶ review ──▶ done
              ▲          │            │              │
              └──────────┴── released ┘              │
                         └──── blocked ──────────────┘
```

`done` is terminal. Reopening would make the log say a task finished twice; the honest record of
"we shipped it and it was wrong" is a new task referencing the old one.

`released` is not really a status — it is the word for handing work back, and it maps to `ready`
plus dropping your lease. It is always allowed, deliberately: a guard there would make abandoning
the task the easier move, and an abandoned task loses everything you learned.

### Environment

| Variable | What it does |
|---|---|
| `TASKOPS_ACTOR` | Who you are: `agent:<dev>/<name>` or `dev:<name>`. Otherwise resolved from git. |
| `TASKOPS_SESSION` | The Claude Code session id. The plugin sets it. |
| `TASKOPS_API_TOKEN` | Default `--token` for the studio. |

### When something looks wrong

| Symptom | What it means |
|---|---|
| `no taskops project at or above …` | Run `taskops init` in the repository root. |
| A commit was denied | Read the message — it names the branch to switch to or the task to claim. Do not use `--no-verify`: `post-commit` records the commit anyway and you get one nobody agreed on. |
| `taskops_next` says nothing is ready | Read the reason. "Everything blocked" is worth telling a human; "everything claimed" means ask again shortly. |
| Hooks are not firing | `.git/hooks` is not tracked, so a fresh clone has none. `taskops init` again. |
| The board says `studio not built` | You are on a checkout with no bundle: `cd studio && npm install && npm run build`. |
| A card is stuck in `claimed` | The agent died. Wait for the lease (≤15 min), or `taskops update <id> --status released --comment "…"`. |

### Changing the UI

```sh
cd studio
npm install
npm run build        # typechecks, then writes the bundle into the Python package
npm run check        # build + fail if the committed bundle drifted from its source
```

The bundle is **committed** on purpose: `pip install taskops` has to serve the board with no node
toolchain anywhere. `npm run check` is what stops the committed output from drifting from the
source it was built from.
