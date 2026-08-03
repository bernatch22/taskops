# The workflows

Every flow taskops has, end to end, with the commands that make it happen and the reason each
step is there. `USAGE.md` is the tutorial — it walks one story from nothing. This is the map: nine
flows, each one readable on its own, so you can find the one you are in.

| | flow | starts with |
|---|---|---|
| 1 | [Starting a board on one machine](#1--starting-a-board-on-one-machine) | `taskops init` |
| 2 | [Planning work](#2--planning-work) | `taskops_plan` |
| 3 | [The loop: claim → commit → review → close](#3--the-loop-claim--commit--review--close) | `taskops_next` |
| 4 | [Landing: how the work reaches the trunk](#4--landing-how-the-work-reaches-the-trunk) | closing a card |
| 5 | [Sharing a board](#5--sharing-a-board) | `taskops board create` |
| 6 | [Bringing somebody in](#6--bringing-somebody-in) | `taskops board invite` |
| 7 | [Milestones and the standing context](#7--milestones-and-the-standing-context) | `taskops milestone new` |
| 8 | [The daily report](#8--the-daily-report) | nothing — it triggers itself |
| 9 | [What a person sees](#9--what-a-person-sees) | opening a session |

Two rules run through all nine and are worth reading first, because most of the design is
downstream of them.

**`.taskops/events.jsonl` is the truth.** Append-only, content-hashed ids, committed. `db.sqlite`
is a cache and is disposable — `taskops sync` rebuilds it from the log. Nothing writes state that
is not derived from the log, which is what makes two clones converge through an ordinary
`git pull` with no merge resolution: appending to different ends of one file is the edit git
merges without help, and importing the same event twice is a no-op.

**An instruction is not a mechanism.** Anything a model must remember across a long session
belongs in the message that needs it, or in a guard that refuses. That is why every refusal below
names what to do next, and why questions arrive in return values rather than in a guide.

---

## 1 · Starting a board on one machine

```sh
cd your-repo
taskops init
```

One command writes all of it, and merges rather than overwrites — a hook, an MCP server or a
`statusLine` you configured yourself is left exactly as you wrote it:

| what | where | why it is there |
|---|---|---|
| the log and the cache | `.taskops/` | the log is committed, the cache is ignored |
| the ignore block | `.gitignore` | path by path, so a new file under `.taskops/` is tracked by default — which is right for `board.json` and was a hazard the day `remote.json` arrived holding a bearer |
| five git hooks | `.git/hooks` | never tracked, so a fresh clone has none: re-running `init` is the repair |
| the MCP server | `.mcp.json` | with an ABSOLUTE interpreter — a bare `python3` is whatever the shell that typed it answers, which is not what a GUI-launched session resolves |
| five Claude Code hooks + the status line | `.claude/settings.local.json` | machine-specific (it names paths on this disk), hence `.local` and gitignored |
| two specialists | `.claude/agents/` | `taskops-worker` and `taskops-verifier`, regenerated every init to match the installed version |

**Do not register the MCP server by hand.** `init` did it, and a `claude mcp add … python3 …`
typed into a shell records the wrong interpreter in a way that fails silently.

Re-running is always safe and is how you repair a clone.

---

## 2 · Planning work

One call with the whole tree — tasks, specs, dependencies, subtasks — because a plan made one
card at a time is a plan whose dependencies were guessed at:

```
taskops_plan entries=[
  {"title": "the CSV reader", "spec": "explicit encoding, never the system's"},
  {"title": "normalise dates", "spec": "DD/MM, annotated on the row", "after": [0]},
  {"title": "the transactional batch", "spec": "all or nothing", "after": [1],
   "acceptance": ["WHEN a row fails THE SYSTEM SHALL keep the rest"]}
]
```

`after` takes an index into this batch or an id that already exists. `parent` makes a subtask the
same way. Ids are minted before the first insert, so `parent: 0` resolves — which it did not,
silently, until a card came out with no parent and nothing said why.

What comes back is the ids in the order you listed them, so you can map your own plan onto them,
plus two things worth reading:

- **`N ready to start now`** — or a warning that NOTHING is, which is almost always an `after`
  cycle or an off-by-one index. Invisible until the first `next` returns nothing, so it is said here.
- **who closes these** — for every card that named no reviewer. See flow 3.

From the terminal the same thing is `taskops tasks plan <file.json>` or, for one card,
`taskops tasks add "<title>" --spec "…"`.

---

## 3 · The loop: claim → commit → review → close

```
taskops_next                      claim: returns the spec, the branch to create, the collision warning
  ↓
git switch -c tk/<id>/<slug>      the branch the claim named
  ↓
git commit                        the trailer is added FOR you, by the hook
  ↓
taskops_update status=review      hand it over, with what you did per criterion
  ↓
somebody else closes it           never the author — see the reviewer, below
```

Three things the engine enforces rather than suggests:

- **A commit must be on the claimed card's branch.** The `PreToolUse` hook sees `git commit`
  before it runs, refuses one no lease covers, and rewrites the command to add the `Task:`
  trailer. The refusal names the branch to switch to or the card to claim.
- **`done` requires a commit bound to the card**, so the board cannot say finished about work
  that does not exist. A card that legitimately produced no code closes with `no_code`.
- **A claim is a LEASE.** Every taskops call renews it; if the process dies it expires and the
  card returns to the queue. A write refused for a missing lease means claim again, not work
  around it.

### Who may close a card

The answer is **on the card**, in its `reviewer` field, written when the card is created and read
by the engine at close time. Three guards, layered, and all three read the card and never a
setting:

| the card says | what is refused |
|---|---|
| *(nothing)* | **always on**: an agent may not close the review it opened itself. Only while the card is in `review`, and only for `agent:` actors — a person may |
| `peer` | the **dev** of whoever closes must differ from the author's dev |
| `human` | no agent closes it; a person must |
| `dev:ana` | that person, nobody else |

`peer` compares by DEVELOPER, not by actor id, and that is the whole point: `agent:dev2/w1` and
`dev:dev2` are one person with two hands. Comparing ids let `dev:dev2` close a card its own agent
had handed over — two different strings, and in every sense that matters the author signing off on
their own work. It happened to two real cards *while independent verifiers were still running on
them*, and both verifiers had to write their verdict as a comment, because `done` is terminal.

**There is no project-wide default**, deliberately: with nobody else on the board, a rule refusing
every close would make the tool unusable the first time somebody tries it. So a card with nothing
set is guarded only by the weakest of the three — which is why `plan` asks, in its return value,
naming the ids. A team that has decided can set what new cards get:

```sh
taskops policy reviewer peer     # or: human, dev:<name>, a registered specialist, none
taskops tasks edit <id> --reviewer peer          # or change one card
```

The policy is read at CREATION and stamped on the card. A card planned under an old policy keeps
the rule it was created with, and one that opted out is not dragged back in by a setting changed
afterwards.

### When a card stops being worked on

It must SAY so. Silence is the failure mode — a card nobody touched for a week reads exactly like
a card somebody is working on:

```sh
taskops tasks release <id> -m "where I got to and why I stopped"   # out of depth, out of context
taskops_update task=<id> blocked_on=<other-id>                    # adds the edge AND marks it blocked
taskops tasks cancel <id> -m "why"                                 # it will never be done
```

There is no delete. The log is append-only, and cancelling keeps the reason — which is what
somebody wants three weeks later when the same idea comes back.

---

## 4 · Landing: how the work reaches the trunk

**Approval is the trigger, and there is no separate merge step to remember.** A card reaching
`done` has been read by somebody who is not its author; that is exactly when a merge is justified.
Closing runs it, on the **client** — the server has state and no checkout, and git lives on a
developer's machine:

```
fetch the branch                   the closer's clone has never seen it
catch the trunk up from the remote somebody may have landed a minute ago
merge --no-ff                      the card's work stays findable as a unit
push, and CHECK that it landed     a refused push is not a landing
```

The last two exist because they were missing. Landing is concurrent by construction — two
developers approving each other's cards is the normal case — so without the catch-up the second
one merged onto a trunk hours old, and without the push check `land` reported success while the
shared trunk had never seen the work.

**A conflict is work, not a failure.** The card closes either way — refusing over a git problem
would strand finished work behind something nobody is looking at — and the outcome is recorded on
the board, so `taskops attention` lists it under `LAND`. From there it is a job for a
`taskops-worker` sub-agent — a conflict is a card whose work happens to be a merge — and
`taskops land <id>` is the retry once it is resolved.

A card that never carried code is silent here rather than reported as unlanded: filling a sweep
with cards nobody can act on is how a sweep stops being read.

---

## 5 · Sharing a board

Two ways, and neither needs you to ssh anywhere. Which one you want depends on one question:
**is this project on GitHub?**

Somebody runs the server once, and after that nobody logs into it again:

```sh
taskops serve --root ~/taskops-server --host 0.0.0.0
```

### Without GitHub — three commands

```sh
taskops remote add https://boards.example.com   # names the server; no board yet, so no credential
taskops board create test                       # creates it, and writes the minted token here
taskops board invite ana                         # one code, one person — flow 6
```

The first asks for nothing on purpose: there is no board yet, so there is nothing to authenticate
to and nothing to authenticate with. The second returns the board's **token**, which lands in
`.taskops/remote.json` — gitignored, `0600`, never printed twice — plus a session over that board,
so it appears in your list on the server's front page. Who may create at all is a deployment
question the server answers: `taskops serve --no-create` shuts the door, and on that path **that
flag is the whole access control**.

### With GitHub

```sh
cd your-repo
taskops board create --server https://boards.example.com
```

The name comes from `origin`, the repository it binds to comes from `origin`, and a session comes
back with it. The authorisation is the same question a login asks, one step earlier: *you may
create a board for a repository you can already push to.* Nothing is granted that GitHub had not
granted first.

What that buys is an **access list that revokes itself** — access IS push access to the repo, so
there is no user list to go stale, and revoking takes effect on their next login. A teammate needs
no URL and no code: `.taskops/board.json` is committed (it holds the address and no secret), so
their clone already knows where its board is.

```sh
taskops join     # in a fresh clone: init, hooks, MCP wiring, and the first pull
```

### What changes once there is a server

**Every write executes in the server's store.** Not "syncs to" — executes in. Between two syncs,
two agents on two machines can both find the same card `ready` and both take it, because each
sqlite grants its own lease. The fix is not a better algorithm, it is a single PLACE: `next` and
`update` run in the server's database, where the race is the one the engine already wins.

Reads degrade to this machine's cache with a warning on stderr. Writes never degrade — a
remote-configured project whose server is unreachable raises, naming the URL, because quietly
claiming locally is the collision this design exists to prevent.

`.taskops/events.jsonl` **stops growing** at the moment you link: it keeps the history up to
then, and the server's log is the truth from there. `taskops board create` says so, out loud.

---

## 6 · Bringing somebody in

For a board with no GitHub repository behind it, access is per person:

```sh
taskops board invite ana
```

```
send them this — it works ONCE, and expires in 7 days:
    taskops join https://boards.example.com/test?invite=<code>
```

The right to invite is the right to write, so this needs the board's own credential out of
`remote.json` and no server session. The code is stored **only as a digest**, is never printed
twice, and inviting somebody again replaces it. `taskops board invite ana --withdraw` takes back
one that has not been used.

`join` does everything: init, the git hooks, the MCP wiring, and the first pull. One line and
they are working.

To see who can get in: `taskops board access`. For a linked board it prints the `gh` commands
that grant and revoke, because that is where the answer lives — a user list here would be a copy
of the repository's collaborators, and a copy goes stale the day somebody is removed.

---

## 7 · Milestones and the standing context

Two vocabularies over one log, and the seam between them is TIME.

A **milestone** is the chapter a board is in: a thing a person would recognise as finished. Every
card belongs to exactly one, and a board with none refuses to plan — which is the rule the whole
model rests on. An agent may open one, work under it and REPORT it finished; only a person may say
it was reached.

```sh
taskops milestone new "que el importador ande de punta a punta" --horizon 2026-08-20
taskops milestone new "que se pueda facturar" --planned      # written down, not started
taskops milestone                                            # every ACTIVE chapter, with counts
taskops milestone review 31b0b89a -m "las tres cards cerradas, el import anda"
taskops milestone done   31b0b89a                            # a PERSON, and the record says who
```

Several are active at once on a real board — a team ships two things in a fortnight — so `plan`
asks which chapter its cards belong to when more than one is open. It refuses rather than guessing:
a card in the wrong chapter is judged against somebody else's rules, and nothing says so.

The **context** is the facts a worker needs on every card, and the reason it is a SLICE rather than
a book: past roughly 150–200 standing instructions, compliance decays, so a context that grows
makes every agent slightly worse.

```sh
taskops context rule     "cero dependencias fuera de la stdlib" --project
taskops context decision "el CSV se lee en streaming"        # sin alcance: llega a toda su card
taskops context decision "sqlite y no postgres" --labels db
taskops context note     "el importador tiene tres etapas"
taskops me objective     "el parser de fechas"               # yours, and only yours
taskops context          # or: log, retire <id-prefix>, --task tk-…, --milestone <id>
```

Three sorts, three dimensions of scope:

| sort | what it is |
|---|---|
| `rule` | it does not break. Unscoped by nature, and `--project` outlives every chapter |
| `decision` | settled, so it is not re-litigated |
| `note` | standing, and neither. Always a chapter's — a permanent note is a rule |
| `me objective` | what one PERSON is chasing. One each, the latest wins |

**`labels`/`files` narrow by subject** — a decision about the database does not reach a card about
the parser. **The person narrows by owner**: a fact you state for yourself reaches your sessions and
nobody else's. **The chapter narrows by time**: a fact belongs to the milestone open when it was
written and leaves every slice when a person verifies that milestone — nobody retires it by hand.

The first protects relevance and the other two protect SIZE, from the two directions it grows: with
the TEAM (everybody reads the project's facts and their own, so a slice grows by ONE whether three
people are on the board or thirty) and with the YEAR (a decision taken in March is no longer
injected in December).

---

## 8 · The daily report

Nobody triggers it. Three doors, one thing writing:

| who | when |
|---|---|
| the **sweep**, detached | `SessionStart` launches it — at most once per project per day, stamped before the spawn, so ten sessions resuming in a morning cost one model call |
| a **scheduled task** | `taskops schedule install` writes the prompt file and prints the sentence to say to Claude; the time lives inside the app |
| **you** | `taskops report day --digest` |

The sweep narrates every ended day that has events and no write-up yet. It never delays a
session: the child is detached and the hook returns in microseconds, and every failure is
swallowed — a report nobody gets is better than a session nobody starts. `TASKOPS_NO_SWEEP=1`
turns it off.

**A narration is a subprocess of the `claude` somebody is logged into**, so where the request is
SERVED decides whether it can happen at all. On a laptop it can. On a box running `taskops serve`
there is usually no `claude` and certainly no session — so the browser's Generate button asks
first and answers with the fix: run it on your own machine, which writes the prose there and
sends it here, and which is also whose subscription pays for it.

---

## 9 · What a person sees

Everything else the hooks produce goes to the model: `additionalContext` is wrapped in a system
reminder nobody sees, and a hook's plain stdout is hidden too. Two surfaces are for the human.

**The opening sentence** — `systemMessage`, the one hook field that reaches a terminal:

```
taskops is tracking this project with your team — the team is working towards ship the importer
(by 08-20), and you are on the date parser. Right now: 5 ready to hand to an agent and 2 waiting
for somebody to review. Since yesterday, you moved tk-ff2f62 to review and ana picked up tk-0a84e1.
Board: https://boards.example.com/probe/
```

One line, coloured, in plain English — no board vocabulary, because `dispatch` and `specless` are
scheduler states and a reader learns nothing from a count of them. It never grows with the board:
people are capped at two and cards are counted per meaning. It says `on this machine only` when
there is no server, because "5 ready to hand out" means something different on a board only you
can see.

**The status line** — the row above Claude Code's own footer badges, repainted on every update:

```
-- INSERT --  ·  ◐ tk-92c0aa the date parser  ·  4 to hand out, 2 to review  ·  probe (shared, cached)  ·  78% ctx
```

`init` wires it and leaves a `statusLine` you already had alone. It never touches the network and
never writes: Claude Code re-runs a status line on a 300 ms debounce, so an HTTP call there would
be a request per keystroke-burst, and a projection that wrote would make merely looking at the
screen an event on an append-only log. Which is why, on a shared board, it says **`cached`**.

It cannot remove `⏵⏵ bypass permissions on` — a status line renders in its own row *above* the
built-in badges. What it can do is repeat `-- INSERT --`, which it does when you use vim bindings.

**And the board itself.** `taskops open` opens it whichever kind of project this is: with a
server, the address the team shares; without one, it starts a local `taskops ui` and opens that.
The `SessionStart` hook does the same, so the opening line always has somewhere to click —
`TASKOPS_NO_UI=1` if you would rather it did not.

---

## The one thing an orchestrator reads every turn

```sh
taskops attention
```

What the board is waiting for, grouped by the move each card needs, ordered by which to answer
first. It replaced a notification channel, and the reason is worth stating: **every reaction to
one of those events turned out to be idempotent and derivable from state.** A card sitting in
review with nobody verifying it needs a verifier whether the event arrived a second ago or the
session opened this morning — so the state can be asked instead of the event delivered, which is
what makes it work in the deployment a channel never could: a scheduled session on a server,
where nothing is listening because nothing is open.

It writes nothing, deliberately. A sweep that fixed what it found would be a second dispatcher
running on a timer, and there is exactly one: the orchestrator decides, everything else reports.
