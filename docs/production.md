# Production: agents that run where the board lives

**Status: a plan, not a promise.** Nothing in this document is built. It exists so that when we
start, we start from a design instead of from enthusiasm — and so the parts we build first (the
review loop, the channel, assign-from-UI) are built in a way that does not paint us out of this.

The goal in one sentence: a developer — or their teammate, from the web board — assigns a card,
and an agent picks it up and works it **on a machine that is not anybody's laptop**, with the
same rules the laptop enforces: leases, the commit guard, evidence on `done`, review by another.

---

## 1 · What exists today, and the gap

```
             TODAY                                    │  THE GAP
                                                      │
  laptop ── claude session ── sub-agents              │  the laptop must be open.
     │            │                                   │  close the lid and the
     │      taskops MCP ──────────┐                   │  fleet dies with it.
     │                            ▼                   │
     └── push/pull ────▶  server (boards + claims)    │  the server COORDINATES
                          taskops.example.com         │  but cannot WORK: it has
                          · atomic claims             │  no model, no checkout,
                          · reports sync              │  no claude login.
                          · web board                 │
```

Everything that coordinates is already server-side. What is missing is a **worker host**: a box
that holds a checkout, a `claude` login, and something that turns "a card was assigned" into "an
agent is working it".

## 2 · Target architecture

```
                          ┌────────────────────────────────────────────┐
                          │  BOARD SERVER (already exists)             │
   jp ── browser ────────▶│  boards · claims · reports · /api/live WS  │
   berna ── browser ─────▶│                                            │
   laptops ── push/pull ─▶│  events out ──────────────┐                │
                          └───────────────────────────┼────────────────┘
                                                      │ WS (the same feed the
                                                      │  channel consumes)
                          ┌───────────────────────────▼────────────────┐
                          │  RUNNER (new, one per environment)         │
                          │                                            │
                          │  taskops runner --env staging              │
                          │   · a long-lived claude session            │
                          │     (claude -p or SDK) with the taskops    │
                          │     MCP + the project checkout             │
                          │   · listens: assigned / ready+label        │
                          │   · spawns sub-agents per card, exactly    │
                          │     like a laptop orchestrator does        │
                          │   · pushes commits to a BRANCH, never main │
                          └────────────────────────────────────────────┘
```

The runner is **not** new machinery pretending to be a person. It is the same orchestrator
pattern that already works on a laptop — dispatch → briefs → sub-agents → review loop — moved to
a box and pointed at the board's live feed. Every rule that binds a laptop agent binds it: the
commit guard, the fence, evidence, and (once built) review-by-another.

**What the runner is NOT:** it is not the board server growing a model. The board stays a
coordinator with zero credentials beyond its tokens. The runner is a separate process, on a
separate box if we want, whose blast radius is one checkout and one branch namespace.

## 3 · Environments: sandbox → staging → prod

The promotion ladder, using machinery git already gives us:

```
  SANDBOX (per card)          STAGING (shared)              PROD
  ─────────────────           ────────────────              ────
  a git worktree +            a checkout on the box         the deployed thing
  branch tk/<id>/…            tracking `staging`;           (shipway, or whatever
  — ALREADY EXISTS,           runner merges reviewed        the project uses)
  every card gets one         cards here; CI + smoke
                              run against it
        │                            │                          │
        └── verifier passes ──▶ merge to staging ──▶ human — or a release
             (the review loop)      gate: tests green      card — promotes
```

- **Sandbox is already built**: the per-card worktree IS the sandbox. An agent cannot touch main;
  the guard binds its commits to its branch. What a runner adds is only *where* the worktree
  lives.
- **Staging is a branch plus a rule**: reviewed cards merge to `staging`, and a runner (or CI)
  keeps a deployed staging environment tracking that branch. The rule worth enforcing in taskops
  itself later: a card is not `done` until its branch merged somewhere — today `done` means
  "commit exists", which is weaker.
- **Prod promotion stays human** until we trust the ladder. The honest sequencing: agents write
  → agents verify → humans merge → automation deploys. Remove the human from the middle only
  after the verifier has a track record you can read in the reports.

## 4 · The hard problems, named now so they do not surprise us

**Credentials.** A runner needs a `claude` login. Options, in order of preference: a dedicated
subscription seat for the runner (clean billing, clean identity `agent:runner/*`); an API key
with a hard budget cap (the `DROPPED_ENV` machinery already exists to keep this deliberate).
Never a person's own login on a shared box.

**Git identity and push rights.** The runner pushes branches, never main. GitHub-side: a machine
user or deploy key with branch protection on `main`/`staging`. The commit guard already stamps
`Task:` trailers, so every runner commit is attributable to a card.

**Money.** A runner that reacts to every assignment is a runner somebody can spend money with by
assigning cards. Gates, all cheap: only cards assigned to registry specialists trigger it; a
per-day budget (N worker-sessions, then it queues and says so on the card); and the board shows
runner activity like any actor, so spend is visible in the standup.

**Security.** The board's write surface becomes remote-code-execution-adjacent the moment a
runner obeys it. Mitigations that must land WITH the runner, not after: the runner only picks up
cards from actors it recognises (the GitHub-auth identity, not free-text); it runs with the
narrowest tool set (`--allowedTools`); the box is disposable (a container or a VM snapshot);
and no permission relay — nothing a board write can do may approve a tool call.

**Observability.** Already mostly free: the runner is an actor, so `status`, the fleet view,
the day reports and the narration cover it. The one addition worth making: a runner heartbeat
on the board, so "the runner is down" is visible where everyone already looks.

## 5 · Deploy shape (when we get there)

The board server deploys as it does today. The runner is one more service on a box:

```
pm2/systemd: taskops-runner   (env: TASKOPS_ROOT=<checkout>, the remote configured,
                               a claude login, TASKOPS_ACTOR=agent:runner/main)
```

One runner per environment, not per project — it can watch several boards the same way a
developer works several repos. Staging first, for weeks, before any prod runner exists.

## 6 · Sequencing

1. **Now (in flight):** review loop · channel · assign-from-UI. Each is laptop-side and each is
   a prerequisite: the runner will reuse the channel's event contract, the assign flow is its
   trigger, and the review loop is what makes unattended work reviewable.
2. **Next:** `taskops runner` as a verb — the laptop version first (your own machine reacting to
   your own assignments), because it exercises the whole trigger path with zero new
   infrastructure.
3. **Then:** the same verb on a staging box, dedicated seat, branch-only pushes, budget gate.
4. **Last:** prod, human merge gate intact, and only after staging has a readable track record.
