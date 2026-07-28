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
| `.taskops/remote.json` | Only once you run `taskops remote add`: the server's URL and your **token**. Mode `0600` and gitignored — a bearer in git history outlives the file. |
| A block in `.gitignore` | Ignores everything above except the log. |

`taskops init` is safe to re-run, and re-running is how you **repair a fresh clone** — `.git/hooks`
is not tracked, so a clone starts with none. It also **rewrites** a hook line it installed before
rather than leaving it alone, which is how a repository set up by an older taskops picks up the
current wiring. That matters more than it sounds: every hook line ends in `|| true`, so one naming
a command that no longer exists does not fail — it silently stops binding your commits to cards.

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

You should see `taskops` listed with its tools. They are unchanged by the CLI's slimming —
the agent's door is the MCP server, and only the developer's door got smaller.

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
]' | taskops tasks plan -
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
taskops tasks
```

### 1.5 Commit — and watch the enforcement work

Create the branch it named, then commit normally:

```sh
git switch -c tk/tk-4f2a9c/add-the-refresh-token-table
git add -A && git commit -m "Add the refresh token table"
```

Either way, the commit is now bound to the task:

```sh
taskops tasks show tk-4f2a9c | grep -A2 Commits
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
python3 -m taskops.transports.hooks commit --message "sneaky"; echo "exit=$?"
```

(That is the **wiring** transport, not `taskops`. Nobody types it in normal use — `taskops init`
writes it into `.git/hooks` and the plugin's `hooks.json` names it. It is spelled out here only
because seeing the refusal is the point of this step.)

```
taskops: commit blocked — `random-branch` is not a task branch. You hold 1 task(s) —
switch to one of tk/tk-4f2a9c/… (taskops_ask gives the exact branch name)
exit=2
```

Inside Claude Code that refusal reaches the **agent** as text it can act on, and the commit never
runs. Exit 2 is what Claude Code reads as "deny".

Note that the guard on its own does **not** stop a determined `git commit` in your terminal —
nothing hooks your shell, and a `pre-commit` hook was deliberately not installed (a refusal there
reaches a human as a failed command with no context). The enforcement is on the agents, which is
where the volume is.

### 1.6 Close it

> Mark it done.

```sh
taskops tasks done tk-4f2a9c -m "Table and model landed; expiry is a column, not a job."
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
taskops tasks done tk-8b31d0 --no-code \
  -m "Decided against rotation-on-use; reasoning in the thread."
```

### 1.7 See where things stand

```sh
taskops report board        # every column, who holds what
taskops report standup      # what changed in 24h, and what needs a human
taskops report day --date yesterday   # ONE calendar day in full: what closed, with the
                                      # commits and diff sizes, and what was said
taskops report day --write            # …and file it under .taskops/reports/YYYY-MM-DD.md,
                                      # committed, stamped with the log position it covers.
                                      # Refuses to overwrite one; --force if you mean it.

# A day is rarely the question. The same dossier over any span of days:
taskops report range --last 7d                    # also 2w, 1m — inclusive of both ends
taskops report range --from 2026-07-22 --to 2026-07-28
taskops report all                                # from the log's first event to today
taskops report all --digest                       # …and have Claude narrate the whole project

# --write and --digest work on all three. The file is named by the window:
#   .taskops/reports/2026-07-28.md · 2026-07-22..2026-07-28.md · all.md
# In a range, `## Cerrado` groups its cards by day, newest first. `## Abierto` lists the
# cards the window CREATED and has not closed, each with what it waits on and what waits
# on it — a day spent planning is a day something happened on. `## Sigue abierto` carries
# every other open card the window touched, including `ready` and `backlog`.
#
# What is PRINTED is short; what is WRITTEN is the record. The file carries each card's
# spec quoted whole, every comment attributed and complete, and every file of every
# commit — it is meant to be read instead of the git log a month later. --digest then
# asks Claude for a paragraph per card: what was asked, what was delivered, what was
# decided, what it cost. A dossier past ~60k characters is narrated in slices and
# stitched (several model calls, a couple of minutes) rather than trimmed to fit.

taskops report fleet         # which agents are alive right now, on what file
taskops tasks show tk-4f2a9c # one task in full
taskops tasks search refresh # search titles and specs
```

---

## Part 2 — The live board

```sh
taskops ui
```

```
taskops ui → http://127.0.0.1:2140/  (/Users/you/your-repo)
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
- **Read the reports.** The third tab, `Reports`, lists everything in `.taskops/reports/` newest
  first and renders the one you pick — headings, tables and code, with the `## Narración` lifted
  to the top in its own panel. A row carries a `stale +N` badge when N events landed after the
  report was generated, and a `✎` when somebody (or Claude) has written the narration. The
  **Generate / Regenerate** button runs the same `report day --digest` from the browser, and you
  **watch it being written**: the request returns immediately and the prose arrives on the live
  socket a fragment at a time, rendered as it lands, while the same text is saved to the file on
  disk as it goes. Closing the page does not stop it, and reopening it shows the file — which is
  the durable copy; the socket is only the window. The row in the list says `narrating…` while it
  runs. A model call takes minutes on a big window, so a second Generate for the same report is
  refused with a 409 (two models rewriting one file is corruption, not contention), and if
  `claude` is missing or logged out the server's own words reach the screen. It is a write, so
  `--readonly` refuses it — a board on a screen in a room cannot spend anything by being looked at.

Useful flags:

```sh
taskops ui --port 3000
taskops ui --readonly              # for a screen in a room: refuses every write
taskops ui --host 0.0.0.0 --token "$(openssl rand -hex 16)"
```

With `--token`, open the URL it prints — the link carries the token, and the page remembers it.

> `taskops studio` was the old name and still runs, printing one deprecation line first.

> **`/api/live` is a WebSocket, with SSE as the fallback.** One route, two envelopes, one
> source — the browser upgrades, and anything that cannot (a proxy that mangles the handshake)
> gets server-sent events, which also makes `curl -N /api/live` a working debugging tool. It
> carries two things: `change` frames, which are stored events and only a signal to refetch,
> and `narration` frames, which are ephemeral prose that is never stored anywhere.
> `src/taskops/transports/http/live.py` has the full argument.

### 2.1 Many projects on one host — `taskops serve`

`taskops ui` serves the repository you are standing in. `taskops serve` serves a **directory of
projects**, each under its own URL prefix and behind its own token — which is what you want on a
host, where several projects' boards live together and agents on different machines compete for
the same cards inside one sqlite.

The code stays in git. What centralises is the **board**.

```sh
taskops serve init axion --root ~/taskops-server
taskops serve init otro  --root ~/taskops-server
```

```
created axion at /home/you/taskops-server/axion
token (shown ONCE, kept in /home/you/taskops-server/axion/token):

    d5bad97814a5e3211832f59c09a6b98b

open the board at  http://<host>/axion/?token=d5bad97814a5e3211832f59c09a6b98b
```

The token is minted by the box, written `0600`, and **printed exactly once** — re-running
`serve init` says the project already exists and does not reprint it. Nothing can recover it; a
lost token is re-minted by deleting the file and running `serve init` again. It never goes into
git and never into a log.

```sh
taskops serve --root ~/taskops-server            # loopback
taskops serve --root ~/taskops-server --host 0.0.0.0 --port 2160
```

```
taskops serve → http://127.0.0.1:2160/<project>/  (/home/you/taskops-server)
```

Each project answers under its prefix — `/axion/` is the board and `/axion/api/...` is the same
JSON API `taskops ui` serves, live feed included:

```sh
curl -H "Authorization: Bearer $AXION_TOKEN" http://host:2160/axion/api/board
curl -N -H "Authorization: Bearer $AXION_TOKEN" http://host:2160/axion/api/live
```

What is different from `taskops ui`, and why:

- **The token is required for everything, including reads.** `ui` may be open because loopback
  is loopback; this is meant to face a network. No token, no board.
- **A token is an answer about ONE project.** axion's token on `/otro/` is a 401.
- **A project with no `token` file is not served at all** — refused rather than served open,
  because the failure mode of the alternative is a public board because a file was missing.
- **A name that is not `[a-z0-9-]{1,40}` never reaches the filesystem**, and an unknown project
  is a bare 404 that lists nothing: naming what does exist would hand a stranger every board on
  the host.
- **No git hooks, no guard.** A server directory is a store of boards, not a working tree, so
  `serve init` creates the project with hooks disabled and the directory need not be a git
  repository at all.
- `--readonly` and `--rate-limit` apply to every project on the server.

`.taskops/` in each project directory is an ordinary taskops store, so everything else in this
guide — `taskops report --repo ~/taskops-server/axion`, an agent over MCP, `sync` against a
checkout — works against it unchanged.

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

| Hook | Runs | What happens |
|---|---|---|
| `SessionStart` | `…hooks session-start` | The agent starts knowing what it holds and who messaged it. |
| `PreToolUse` on Bash | `…hooks pre-tool-use` | A commit with no claim is denied; a valid one gets the trailer injected. |
| `PostToolUse` | `…hooks post-tool-use` | New messages are delivered; activity appears in the fleet panel. |
| `Stop` | `…hooks stop` | The session posts a summary to each task it holds — a standup nobody wrote. |

`…hooks` is `python3 -m taskops.transports.hooks`. It is a transport of its own, beside the
CLI and the MCP server, precisely so that a hook line is not an entry in the menu a developer
reads.

---

## Part 4 — A second developer

Two ways, and you pick one per project. **With a server** the boards converge in seconds;
**through git** they converge when you push and pull, with no server to run. Neither is
deprecated — the second is still the right answer for a team that does not want to operate
anything.

### 4a — With a server

One person runs `taskops ui` somewhere both machines can reach, and issues each developer a
token. Then, on every machine:

```sh
taskops init
taskops remote add https://taskops.example.com --token <your-token>
taskops push
```

That is the whole setup. From then on:

```sh
# you, after an afternoon of work
taskops push
```

```sh
# them, whenever they want to be current
taskops pull
taskops report board
```

**`push` pulls too**, which git does not do and here it should: the round trip is one more
request against a server you have just proved you can reach, and the alternative is two
developers whose boards diverged this morning, each convinced they are current. `push` prints
what moved in both directions.

**Agents on two machines cannot claim the same card.** This is the reason to run a server at
all. Once a project has a remote, `taskops_next` and `taskops_update` — and `taskops claim`,
`taskops tasks done`, every surface — stop deciding locally and execute **in the server's
store**. Two agents asking for one card are then two inserts on one primary key in one sqlite:
one gets the claim, the other gets the ordinary "somebody is on it" and moves to the next task.
Nothing about the commands changes; you configure the remote and the writes follow it.

You do not have to `pull` first, and you do not have to remember to `pull` after: every remote
write pulls before it answers, so the board you read next is the board the server just wrote.
If that pull fails, the whole call fails — an agent told "claimed" whose own board has never
heard of the claim would be denied by its own commit guard a minute later.

**And if the server is down, a claim FAILS.** It does not quietly claim locally instead:

```
this project's writes go to https://taskops.example.com, which did not answer
(Connection refused) — taskops will NOT claim locally instead, because a local claim
could collide with another machine's; retry, or check the network
```

That refusal is the feature. A local claim made while the server was unreachable is exactly the
collision the server was there to prevent, and it would be discovered when two agents had
already edited the same files. Reading — `board`, `ask`, `report` — keeps working offline; only
the two writes that hand out work stop.

Anyone holding the project token can act as any actor in the project: the server has no way to
learn who is on the other machine, so the token is the boundary — the same one git draws, where
whoever can push can commit under any name. Issue one token per developer.

**Where the token lives.** `.taskops/remote.json`, mode `0600`, and `taskops init` gitignores
that path — a bearer in git history is still a bearer after somebody deletes the file, and
nobody notices they need to rotate it. `taskops remote` shows the URL and the token's *length*,
never the token. One remote per project: a second `add` is refused by naming the first, because
two remotes means two cursors over two logs, and that is federation, which is not designed.

**Reports never clobber.** A dossier regenerates from the log any time; the **narration** under
it was written once, by a model somebody paid for or by a person, and nothing can reconstruct
it. So the copy stamped with the larger `max_seq` — the one that saw more history — wins, and
anything else is refused:

```
pushed: 12 event(s) out, 3 in, reports 1 up, 0 down
  ! 2026-07-28: the server's copy is stamped at seq 812, yours at 774 — nothing was
    overwritten. Run `taskops pull` to take the server's, or `taskops push --force` to
    replace it (any narration there is lost).
```

Two independent narrations of the *same* dossier always land here, and that is the honest
answer: nobody can decide that one for you. `--force` is the valve, and the message says what
it costs before you reach for it.

**Offline is not an error state for `push`/`pull`** (it is for a claim — see above). No network
means one line and exit 1, with nothing marked half-sent: events are marked as pushed only after the server answers 200, so a push cut in half
re-sends on the next run and the server accepts each event exactly once. Your board keeps
working the entire time — it is a local sqlite cache of a local log, and the server is a place
they meet.

**If the server is rebuilt** and forgets where you were, your next `pull` re-reads its whole
log. That is a no-op, not a repair job: ids are content hashes, so every event is imported
exactly once no matter how many times it is offered.

### 4b — Through git, with no server

The event log travels in git.

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

> This path converges at `git pull` speed. For seconds instead of pull-cycles, run a server and
> use `taskops push`/`pull` — Part 4a.

---

## Part 5 — Putting the board on a screen

The UI binds to loopback by default. To share it:

```sh
taskops ui --host 0.0.0.0 --port 2140 --readonly --rate-limit 120
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

`taskops --help` lists **ten**, and ten is all there is. What a person does:

```
taskops init [--no-hooks]                  create .taskops/, install the git hooks
taskops tasks …                            the task list (below)
taskops report [board|standup|fleet] [--since 24h]
taskops ui [--port 2140] [--host] [--token] [--readonly] [--rate-limit]
taskops recover [--apply]                  release cards held by silent workers
taskops sync                               reconcile with the committed log
taskops run [--yes] [--use-api-key]        run ready cards with headless Claude workers
taskops remote [add <url> --token <t> | remove]    the server this project syncs with
taskops push [--force]                     send this board up, then take theirs
taskops pull                               take the server's events and reports
```

`remote`, `push` and `pull` are the **developer's**, which is why they are here and not on the
MCP surface: an agent works a board, it does not decide when this machine talks to a server.
They sit *beside* `sync` rather than replacing it — a team with no server converges through git
exactly as before, and that path is not deprecated.

`taskops run` is the one command here that starts Claude sessions, so it says what it costs
before it starts anything and an unattended caller must pass `--yes`. Its workers run on your
**logged-in subscription**: the Anthropic credentials (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_BASE_URL`) are stripped from the spawn environment, because the `claude` CLI prefers an
exported key over the subscription and a background agent nobody is watching would otherwise bill
per token on a plan you already pay for. `--use-api-key` puts them back for whoever wants that —
CLI only, never an MCP tool.

```
taskops tasks                              one line per open task (same as `tasks list`)
taskops tasks show <task-id>               read one task in full
taskops tasks add <title> [--spec …] [--after id,id] [--files …] [--priority N] [--label …]
taskops tasks edit <task-id> [--title …] [--spec …] [--priority N]   correct a card
taskops tasks plan <file.json | ->         create tasks from JSON
taskops tasks done <task-id> [-m …] [--no-code]
taskops tasks release <task-id> [-m …]     hand it back, unfinished
taskops tasks log <task-id>                the agent's conversation for a card
taskops tasks search <text>                search titles and specs
```

`tasks edit` is the exception: it is the one behaviour this group ADDS, because until it
existed a card's title and spec were whatever the planner typed and the only way to fix a
wrong brief was to cancel the card and plan a new one — losing its thread and its commits.
At least one flag is required; each changed field records an `edited` event, so the fix
reaches a teammate's clone through the log like everything else. A `done` or `cancelled`
card refuses: the log is the record of what was delivered, and rewriting the spec of
finished work rewrites that record. Editing stays out of the MCP tools deliberately —
correcting a brief is a human act, and an agent that can rewrite its own spec can talk
itself into having finished.

### The thirteen commands that are gone

`--help` once listed seven of twenty. The other thirteen were registered and hidden, which
reads the same from the outside as absent and is not the same thing: they were still doors
into the binary a person types, and both git and Claude Code came in through them.

Each audience now has its own door.

| Was | Is now |
|---|---|
| `taskops next · update · ask · plan · dispatch · log` | The MCP tools — `taskops_next`, `taskops_update`, `taskops_ask`, `taskops_plan`, `taskops_dispatch`. Reading a card by hand is `taskops tasks show`. |
| `taskops guard commit` | `python -m taskops.transports.hooks commit` |
| `taskops hook <event>` | `python -m taskops.transports.hooks <event>` — `pre-tool-use`, `post-tool-use`, `session-start`, `stop` |
| `taskops ingest commit\|branch` | `python -m taskops.transports.hooks ingest commit\|branch` |
| `taskops brief · inbox · track · checkout` | Nothing to call: the hook events do this directly, which is all they were ever for. |

Nothing in the middle column is meant to be typed. `taskops init` writes it into `.git/hooks`
and the plugin ships it in `hooks.json`. `taskops sync` stayed on the CLI as well, because
reconciling by hand is a thing a person legitimately does.

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
| `TASKOPS_API_TOKEN` | Default `--token` for `taskops ui`. |

### When something looks wrong

| Symptom | What it means |
|---|---|
| `no taskops project at or above …` | Run `taskops init` in the repository root. |
| A commit was denied | Read the message — it names the branch to switch to or the task to claim. Do not use `--no-verify`: `post-commit` records the commit anyway and you get one nobody agreed on. |
| `taskops_next` says nothing is ready | Read the reason. "Everything blocked" is worth telling a human; "everything claimed" means ask again shortly. |
| Hooks are not firing | `.git/hooks` is not tracked, so a fresh clone has none — and a repository initialised by an older taskops has a line naming a command that moved. `taskops init` again fixes both; it rewrites its own line. |
| `taskops guard`: *invalid choice* | The wiring left the CLI. It is `python3 -m taskops.transports.hooks commit`, and normally nothing types it by hand. |
| The board says `ui not built` | You are on a checkout with no bundle: `cd ui && npm install && npm run build`. |
| A card is stuck in `claimed` | The agent died. Wait for the lease (≤15 min), or `taskops tasks release <id> -m "…"`. |

### Changing the UI

```sh
cd ui
npm install
npm run build        # typechecks, then writes the bundle into the Python package
npm run check        # build + fail if the committed bundle drifted from its source
```

The bundle is **committed** on purpose: `pip install taskops` has to serve the board with no node
toolchain anywhere. `npm run check` is what stops the committed output from drifting from the
source it was built from.
