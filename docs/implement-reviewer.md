# Implementing review — an optional verifier column and the agent that fills it

An implementation spec. The reader is an Opus session that has not seen the
conversation this came from. Read §0 and §1 before writing a line; §5 is the
file-by-file work; §9 is the order.

The design is Berna's, from 2026-08-07, and §1 states it as he stated it.

---

## 0. This reverses a ban. Read why before you implement it.

`CLAUDE.md` has a "never re-introduce" list, and the first entry is
**reviews/reviewer**. `ARCHITECTURE.md` §11 gives the reason: *"caused deadlocks
in v1"*, enforced by `machine.py` having no review transition and neither role
being a reviewer.

That ban is real and it was earned. v1's review system produced, in production:
a `peer` deadlock where two cards each waited on the other's reviewer, fourteen
separate closing rules spread across six modules, and a reviewer role that
consumed the token budget of the work it was reviewing.

**The owner is reversing it deliberately, for a design that does not reproduce
any of those three failures.** This section is the paper trail, in the same
tradition as `MENTIONS.md` §9 (where Berna narrowed his own no-Claude-hooks
rule). Cite it; do not quietly widen it.

The narrowing, exactly:

> A card MAY require review. Review is a **derived** state and an **optional**
> per-card flag. It adds **no stored status**, **no reviewer role**, and **no
> verb that repairs it**.

Why each v1 failure cannot recur here:

| v1 failure | why it cannot happen |
|---|---|
| `peer` deadlock (A waits on B waits on A) | there is no reviewer *assignment graph*. A verdict is a one-way append. Nothing waits on anything — a card with no reviewer sits in a group whose title is the move to make, and it is TRUE the whole time it sits there |
| 14 closing rules over 6 modules | exactly ONE new clause in `check_transition`, in `core/machine.py`, next to the `done` clause that is already there |
| the reviewer role ate the credit | there is no reviewer ROLE. A reviewer is an ordinary `agent:<dev>/<name>` doing one bounded read. The orchestrator decides whether to spawn one at all |

And the property that makes the whole thing safe: **`review` is off by
default.** A board that never sets it behaves exactly as it does today, and
every test written before this change must still pass untouched. If you find
yourself editing an existing test to accommodate review, stop — you have made
it non-optional, which is the one requirement that cannot bend.

---

## 1. The design, as specified

> A card has `review: false` by default. If `review: true`, you as orchestrator
> assign an agent to review it; if it passes, you move it to done, and if not,
> you talk back to the sub-agent.
>
> The sub-agent and the verifier finish at the same time and the orchestrator is
> the proxy — that way we save time. So no agent has to be invoked to resume.

Three consequences, and they drive everything below:

1. **The orchestrator is the only coordinator.** Worker and verifier never talk
   to each other. This is not a limitation to work around — it is what removes
   the deadlock class entirely, because a one-coordinator graph cannot cycle.
2. **The worker is not discarded when it submits.** It stays reachable, so a
   "changes requested" verdict goes back to the agent that already holds all
   the context, instead of a fresh one that must rebuild it. §4 has the exact
   Claude Code mechanics.
3. **A card that needs review cannot reach `done` by itself.** That is a guard
   in `core/machine.py`, not a convention in a prompt.

---

## 2. The state model

### 2.1 What is stored (two new fields, zero new statuses)

`CARD_STATUSES` stays `("open", "done", "dropped")`. **Do not add a fourth.**
The whole architecture rests on that being three; a stored `in_review` would be
a stored `doing` all over again — a row that outlives the process that meant it.

Two stored fields, both durable facts that stay true when a process dies:

| where | field | type | default | meaning |
|---|---|---|---|---|
| `Card` | `review` | bool | `False` | this card must be reviewed before it can close |
| `Milestone` | `reviews` | bool | `False` | cards planned into this chapter get `review=True` unless the card says otherwise |

The milestone flag is how "the board can be configured with reviewers" is
expressed. It belongs next to `rules` — both are the chapter's half of a card's
contract — and it is *a default, not a rule*: a per-card `review` always wins.

### 2.2 Two new event kinds

Add to `KINDS` in `core/types.py`:

```python
"submitted": Kind(False, ("note",)),          # the worker says it is finished
"reviewed":  Kind(False, ("verdict", "note")),  # verdict: "pass" | "changes"
```

Both are `replayed=False` — **history only**, exactly like `comment` and
`commit`. They do not fold into card state, because what they mean is derived
from reading the thread (§2.3), the same way a pending mention is.

`verdict` is `"pass"` or `"changes"` and nothing else. Validate at the writer
(`verbs/review.py`), refusing anything else with both values named.

### 2.3 What is derived

New pure module `core/review.py` (level 1, no I/O), mirroring
`core/mentions.py`, which already folds threads for exactly this kind of
question:

```python
class Standing(NamedTuple):
    """Where a card stands with its reviewer, folded from its thread."""
    submitted_at: float   # 0.0 = never submitted since the last verdict
    submitted_by: str     # who to talk back to
    verdict: str          # "" | "pass" | "changes" — since the last submission
    verdict_by: str
    note: str             # the reviewer's words, shown verbatim to the worker


def standing(events: list[Event]) -> Standing: ...
def pending(threads: Mapping[str, list[Event]]) -> dict[str, Standing]: ...
```

`standing()` walks one card's events in order and keeps: the last `submitted`,
and any `reviewed` that came **after** it. A `reviewed` older than the latest
`submitted` is stale by construction — the worker resubmitted, so the previous
verdict is answered. Compare by **position in a stable sort by `ts`**, not by
timestamp value; `core/mentions.py::pending` does this and its docstring says
why (a frozen or coarse clock makes an answer share the mention's timestamp).

### 2.4 The precedence, exactly

`graph.derived()` gains two optional parameters and one new block. **The order
below is the specification** — implement it top to bottom and pin the order in
a test:

```
done | dropped   card.status is closed                          (unchanged, first)
reviewing        somebody holds a REVIEW lease right now
review           review ∧ submitted ∧ no verdict since          → orchestrator assigns a reviewer
doing            somebody holds the WORK lease
changes          last verdict is "changes"                      → back to the worker
blocked          a dependency has not closed                    (unchanged)
stalled          it has an assignee                             (unchanged)
ready            otherwise                                      (unchanged)
```

Two placements that are deliberate and will look wrong if you skim:

* `review` sits **above** `doing`. A submitted card whose worker still holds its
  lease is waiting for a reviewer, and that is the move to show.
* `changes` sits **below** `doing`. A worker that picked the card back up after
  a "changes" verdict is *working*, not waiting. The card only reads `changes`
  when nobody is on it — which is precisely when somebody must be.

New signature:

```python
def derived(
    cards: dict[str, Card],
    card: Card,
    holders: Holders | None = None,
    reviewing: Holders | None = None,      # task -> reviewer, live REVIEW leases
    standings: Mapping[str, Standing] | None = None,
) -> str:
```

Both new parameters default to `None` and mean "nothing under review", so
**every existing call site keeps working unchanged** and every existing test in
`tests/test_core.py` stays green untouched. That is the optionality requirement
expressed in a type signature.

Callers to update — these are all of them, verified:

```
src/taskops/verbs/update.py:62
src/taskops/verbs/pulse.py:54
src/taskops/verbs/card.py:47
src/taskops/verbs/_context.py:31, :124, :163, :174
```

`_context.py:163` and `:174` derive the state of a *related* card (the epic, a
blocker) for a one-line summary. Passing the review facts there is optional
polish; do the four that matter first.

---

## 3. Synchronization — the part to get right

### 3.1 The mutex is a second lease, in its own table

`live.sqlite` gains a third table alongside `leases` and `presence`:

```sql
CREATE TABLE IF NOT EXISTS reviews (
    task     TEXT PRIMARY KEY,   -- the PK is the mutex, same as leases
    actor    TEXT NOT NULL,
    acquired REAL NOT NULL,
    expires  REAL NOT NULL
);
```

**A separate table, not a `purpose` column on `leases`.** Adding a column would
mean changing the primary key of `leases`, which SQLite cannot do with `ALTER`
— it needs a table rebuild, and `live.sqlite` is the one file in this system
that is **not** disposable. A new table is purely additive: `CREATE TABLE IF
NOT EXISTS` runs on every open and an existing board gains it with no migration
and no risk to a live claim.

Add to `store/live.py`, mirroring the existing lease methods exactly:

```python
def claim_review(self, task, actor, now, ttl=LEASE_TTL) -> bool   # INSERT OR IGNORE
def reviewer(self, task, now) -> str | None
def reviewing(self, now) -> dict[str, str]        # task -> actor, live only
def drop_review(self, task, actor) -> bool        # only the holder
```

`renew()` must renew review leases too — same rule as work leases, the traffic
is the heartbeat. Extend its `UPDATE` to cover both tables.

**A card can hold a work lease and a review lease at the same time, held by
different actors.** That is correct and intended: the worker is still alive
(§1.2) while the verifier reads.

### 3.2 The three races, and what actually happens

Berna's concern, verbatim: *"si un agente remoto agarra un card para review y se
lanzan agentes en simultáneo, por más que un atomic falle."*

**Race 1 — two verifiers claim the same card.** `INSERT OR IGNORE` on a primary
key. One row, one winner, decided by SQLite. On a remote board every client
talks to one server process holding one file, so there is no second arbiter to
disagree. The loser gets a refusal naming the winner, the same shape
`machine.check_take` already produces.

**Race 2 — the atomic somehow does not save you.** This is the one worth
answering properly, because "it can't happen" is not an engineering answer.
Suppose two verifiers both review and both write a verdict. Nothing corrupts,
and here is why by construction:

* Verdicts are **appended events**, never a mutated field. There is no cell for
  two writers to interleave on.
* Event ids are `sha256(canonical)[:32]`, so two identical verdicts are **one
  event** — the log deduplicates them for free.
* Two *different* verdicts (one `pass`, one `changes`) both land in the thread,
  and the close guard (§6.1) requires a `pass` **and** shows the orchestrator
  the whole thread. A human decides, which is the correct resolution for a
  genuine disagreement between two reviewers.

So the worst case degrades to *wasted tokens*, never to a card that closed
without review or a board that disagrees with itself. Say this in the docstring
of `claim_review` — it is the reason the design is allowed to be simple.

**Race 3 — the verifier dies mid-review.** Its review lease stops being renewed
and expires. The card leaves `reviewing` and returns to `review` on its own,
with no sweep, no writer and no repair verb — the identical mechanism that
already handles a dead worker. **Do not add a recovery path.** If you feel you
need one, you have stored something you should have derived.

### 3.3 What is NOT stored, on purpose

The orchestrator holds its worker's Claude Code agent handle **in its own
session**, never on the board. An agent id dies with the session that spawned
it; writing it to an append-only log would be a fact that is false tomorrow —
the exact mistake `doing` used to make. Across sessions the handle is gone and
you fall back to spawning a fresh worker with the card's `resume` note, which is
what that note has always been for.

---

## 4. The choreography, and the Claude Code mechanics behind it

> *This section states what the platform actually supports. It was researched
> against current Claude Code behaviour rather than assumed; §4.2 records the
> findings and their limits.*

### 4.1 The flow

```
orchestrator                worker (agent:berna/w1)      verifier (agent:berna/r1)
     │
     ├── taskops_assign ────▶ spawn as a CUSTOM agent — keep its agentId (§4.2)
     │                             │
     │                        take → implement → commit
     │                             │
     │◀─── "submitted" ────── taskops_update status=review note="…"
     │                             ▲   (finished, but RESUMABLE — keep the handle)
     ├── spawn verifier, FRESH ──────────────────────────▶ taskops_review task=…
     │      (never a fork — §4.2)                               │
     │                                                     read the diff
     │◀──────────────────────────── taskops_review verdict=… ───┘
     │
     ├─ verdict = pass    → taskops_update status=done      (the orchestrator closes it)
     └─ verdict = changes → RESUME w1 with the note; it still has everything
```

The saving Berna is after is in that last line: no re-spawn, no re-reading of
the spec, no rebuilding of understanding. The orchestrator is a proxy carrying
one message between two agents that never address each other.

### 4.2 What the platform supports — researched, not assumed

Checked against current Claude Code / Agent SDK documentation on 2026-08-07.

**A new sub-agent cannot inherit a different sub-agent's conversation.** A
subagent's context window starts fresh: its own system prompt plus the prompt
string you spawn it with, and nothing else — no parent history, no sibling
context. Do not design around inheritance; it does not exist.

**An already-finished sub-agent CAN be continued with its full context.** This
is what makes Berna's "no hay que invocar ningún agente para retomar" real. The
mechanism — re-verified 2026-08-07, because an earlier draft of this section
described a "resume the session_id and name the agentId in the prompt" dance
that is NOT how it works:

* the Agent tool returns an **agent id** on spawn; keep it;
* to continue the finished worker, the orchestrator sends it a message with
  **`SendMessage`** addressed to that id (or the agent's name) — the sub-agent
  auto-resumes with the **entire conversation, every prior tool call and
  result, and the reasoning state** intact;
* "RESUME w1 with the note" in §4.1 is therefore exactly one `SendMessage`
  carrying the reviewer's verdict note. No new Agent call, no re-reading.

Three limits that matter here:

| limit | consequence for this design |
|---|---|
| built-in agents (`Explore`, `Plan`) are one-shot and return **no agent id** | the worker must be spawned as a **custom agent or `general-purpose`**, or there is nothing to continue. Say so in the brief |
| the agent id is **session-scoped**: a NEW session cannot reach it (resuming the SAME session after a restart can — sub-agent transcripts persist in their own files, cleaned up after ~30 days) | confirms §3.3: never write an agent handle to the board. In a fresh session you fall back to the card's `resume` note |
| continuation **survives the main conversation's compaction** — transcripts are stored separately | a long orchestrator session can still reach a worker it spawned hours ago |

**`subagent_type: "fork"` inherits the PARENT's whole conversation** — same
system prompt, same tools, same model, and it shares the parent's prompt cache,
which makes it cheaper than a fresh spawn when the context really must be
identical. Forks cannot nest, and the feature is behind
`CLAUDE_CODE_FORK_SUBAGENT=1` on a staged rollout.

**Do not use a fork for the verifier.** It is the wrong instrument precisely
because it works: a verifier that inherits the orchestrator's reasoning has
inherited the assumptions it is supposed to be checking. An independent read is
the entire product of a review. Spawn the verifier fresh, with the card and the
diff, and let it disagree.

**Sub-agents can message each other** — `SendMessage` between *named* agents in
the same session (v2.1.206+). **This design deliberately does not use it.** The
platform permitting a reviewer→worker channel does not make it a good idea:
routing every verdict through the orchestrator is what keeps the coordination
graph acyclic, and an acyclic graph is the reason v1's `peer` deadlock cannot
recur here (§0, §1.1). If a direct channel ever seems necessary, stop — you are
rebuilding `peer`.

**If continuation is unavailable** for any reason, the design still works: spawn a
fresh worker with the card's `resume` note and the reviewer's verdict note, both
of which the board already carries verbatim. **Only the token saving is lost,
never the correctness.** Do not block the implementation on it.

---

## 5. File by file

### 5.1 Two modules must be SPLIT before you can add anything

Both are at the 200-line budget that `tests/test_architecture.py` enforces.
**Split first, in its own commit, with the suite green — then add the feature.**
A rule with no test is a suggestion, and this one has a test.

**`src/taskops/core/types.py` — 199/200, margin of ONE line.**
Split the **actor grammar** into `src/taskops/core/actors.py` (level 1): move
`ROLE_DEV`, `ROLE_AGENT`, `ROLE_SYSTEM`, `_NAME_OK`, `role_of`, `_check_name`,
`slugify` — **and `SYSTEM`**, which `role_of` compares against: `types.py` will
re-export from `actors.py`, so `actors.py` importing `SYSTEM` back from
`types.py` would be a cycle. Move it and re-export it too. That is a real seam — *what the rows are* versus *who may speak and
what their names may look like* — not a cut to make room. Re-export from
`types.py` so the importers keep working unchanged:

```
src/taskops/verbs/__init__.py   role_of
src/taskops/http/auth.py        role_of
src/taskops/verbs/update.py     role_of
src/taskops/verbs/plan.py       slugify
scripts/migrate_v1.py           slugify
```

Add `("actors", 1)`… no — `actors` lives under `core/`, so `LEVELS` in
`tests/test_architecture.py` already covers it via the `core` prefix. Nothing to
add there.

**`src/taskops/mcp/tools.py` — 196/200, margin of FOUR lines.**
Move the two handlers that run git — `_assign` and `_merge` — into
`src/taskops/mcp/gitmoves.py` (level 5). The module's own docstring already
names this seam: *"The eight tools — and the git that belongs to three of
them."* `tools.py` keeps the table and the pure-board handlers.

### 5.2 The rest, in dependency order

| file | change |
|---|---|
| `core/types.py` | `Card.review: bool`; `Milestone.reviews: bool`; two `KINDS` entries (§2.2); add `"review"` to `EDITABLE` so it can be flipped after planning |
| `core/review.py` | **new**, pure. `Standing`, `standing()`, `pending()` (§2.3). Model it on `core/mentions.py` — same shape, same stable-sort discipline |
| `core/replay.py` | `_coerce_card`: `review=bool(raw.get("review", False))`. `_milestone`: carry `reviews` on create and edit. Both new kinds are `replayed=False`, so `_mutate` needs **nothing** |
| `core/graph.py` | `derived()` gains the two optional parameters and the precedence block (§2.4) |
| `core/machine.py` | the `done` guard (§6.1) and the verdict guard (§6.2) |
| `store/live.py` | the `reviews` table and its four methods (§3.1); `renew()` covers it |
| `verbs/_facts.py` | `reviewing(stores, now)` and `standings(stores)` — the world half, mirroring `holders()`. `standings` folds `stores.threads()`, which already exists for mentions |
| `verbs/review.py` | **new verb**. Claim/verdict/release. Validates `verdict` ∈ {pass, changes} |
| `verbs/update.py` | `status="review"` writes a `submitted` event — model it exactly on the `status == "released"` branch at line 122, which is the precedent for a `status=` value that is not a stored status |
| `verbs/take.py` | untouched — the verifier's door is `taskops_review`, not a flag on take |
| `verbs/plan.py` | a planned card inherits `review` from its milestone's `reviews`, unless the card says otherwise |
| `verbs/pulse.py` | two new board groups, `review` and `changes` (§7) |
| `verbs/__init__.py` | register `review` — `Verb(review.run, "write", BOTH, "")` |
| `mcp/schema.py` | `taskops_review` schema; `review` on `taskops_take`; `review`/`reviews` on plan and update |
| `mcp/tools.py` | the `taskops_review` tool + handler |
| `mcp/render.py` | render the two new groups; keep the existing group order and slot them where §7 says |
| `mcp/dossier.py` | a "Review" section — the verdict and its note, verbatim, **above the spec** if it is `changes` (it changes what you do before you start) |
| `mcp/brief.py` | when the card has `review=true`, the brief says so and says the exit is `status=review`, not `status=done` |
| `mcp/server.py` | `INSTRUCTIONS`: the review loop, in the worker and orchestrator sections |
| `ui/index.html` | the two new groups in `GROUPS` |

---

## 6. The guardrails, verbatim

Every refusal in this codebase contains the call that fixes it. Keep that.

### 6.1 A card that needs review cannot close on its own

In `core/machine.py::_check_done`, after the existing commit check:

```python
if card["review"] and standing.verdict != "pass":
    raise Refused(
        f"{card['id']} needs a passing review before it closes. "
        f'Hand it in instead: taskops_update task={card["id"]} status=review note="<what you did>" '
        "— the orchestrator assigns a reviewer and closes it when it passes."
    )
```

`check_transition` and `_check_done` are pure and take a `Facts`; extend
`Facts` with `standing: Standing`, gathered in `verbs/_facts.py::facts()`
alongside `holder` and `commits`. Do not reach into the store from `machine.py`
— `test_core_is_pure` forbids it and it is the whole point of that layer.

### 6.2 You may not pass your own work

In `verbs/review.py`:

```python
if actor == standing.submitted_by:
    raise Refused(
        f"you submitted {card['id']}; somebody else reviews it. "
        "Ask the orchestrator to assign a reviewer."
    )
```

This is the one rule that gives review its entire value. Without it the feature
is theatre.

### 6.3 The orchestrator may close a reviewed card

`core/machine.py::_not_somebody_elses` currently refuses **any** actor who is
not the assignee or holder — so today a `dev:` cannot close a card assigned to
`agent:berna/w1`, which is exactly what Berna's flow asks for ("si pasa, la
pasas a done"). Add one exception, narrowly:

```python
# The orchestrator closes what a reviewer passed. It is not taking the card —
# it is recording a decision that was already made, by somebody who is not the
# author (6.2). Any wider and `dev:` becomes able to close work it never saw.
if role_of(actor) == ROLE_DEV and card["review"] and facts.standing.verdict == "pass":
    return
```

### 6.4 Review is off unless somebody turned it on

`review` defaults to `False` everywhere: the `Card` TypedDict, `_coerce_card`
(a card written before this feature has no `review` key and must read as
`False`), and `plan` when the milestone does not say otherwise. **A board that
never sets it must behave exactly as it does today** — that is testable and
§8 says how.

---

## 7. What the board shows

Two new groups in `verbs/pulse.py` and `mcp/render.py`, slotted into the
existing order by the urgency rule the board already follows — *the group whose
move is most blocking comes first*:

```
MERGE     done, not integrated                    → taskops_merge
MENTIONS  addressed to you, unanswered            → answer on the card
REVIEW    handed in, nobody reviewing             → assign a reviewer     ← new
CHANGES   a reviewer asked for changes            → back to the worker    ← new
STALLED   owned, nobody running it                → taskops_assign
TAKE      ready                                   → taskops_assign
DOING     somebody holds it
REVIEWING somebody is reviewing it right now                              ← new (informational, with DOING)
BLOCKED   waiting on a dependency
```

`REVIEW` above `STALLED`: finished work nobody is checking is more blocking than
work nobody has started. `CHANGES` right after it, because the fix is usually
seconds of an agent's time and it unblocks a merge.

A `REVIEW` or `CHANGES` row carries the reviewer's note the way a `MENTIONS` row
carries the comment text — the reason, not just the id. Reuse `_first_line()` in
`render.py`, which already trims a note to one board line.

---

## 8. Tests

`./scripts/lint && ./scripts/test` green, pyright strict included, and **every
new test mutation-checked**: break the fix on purpose, watch the test fail, put
it back. Two tests in this repo looked green with their fix removed until this
was done.

`tests/test_core.py` — pure, no I/O:

| test | pins |
|---|---|
| `test_a_verdict_older_than_the_last_submission_is_stale` | resubmitting answers the previous verdict. Mutate: compare by `ts` value instead of position |
| `test_a_tie_on_the_timestamp_keeps_arrival_order` | a frozen clock must not make a verdict outrank the submission it answers |
| `test_review_states_follow_the_documented_precedence` | the §2.4 table, every row |
| `test_a_card_without_review_derives_exactly_as_before` | **the optionality test.** Same inputs, same answers as today |

`tests/test_verbs.py` — the cycle against a local board:

| test | pins |
|---|---|
| `test_a_card_that_needs_review_cannot_be_closed_by_its_worker` | §6.1, and that the refusal names `status=review` |
| `test_you_may_not_pass_your_own_work` | §6.2 |
| `test_the_orchestrator_closes_what_a_reviewer_passed` | §6.3 |
| `test_changes_requested_sends_it_back_with_the_note_verbatim` | the note survives to the worker unshortened |
| `test_a_dead_reviewer_frees_the_card_by_itself` | §3.3 — advance the clock past the TTL, assert `review`, assert **no verb was called** |
| `test_two_reviewers_one_card_one_winner` | §3.1 |
| `test_a_board_that_never_sets_review_behaves_exactly_as_today` | the optionality test, end to end |

`tests/test_topology.py` — the seam, over a real socket, two clients:

| test | pins |
|---|---|
| `test_two_remote_verifiers_race_and_only_one_claims` | Race 1 across the wire — this is the one Berna asked about |
| `test_two_conflicting_verdicts_leave_the_board_coherent` | Race 2: both land in the thread, the card stays open, nothing corrupts |

`tests/test_mcp.py`: the brief tells a reviewed card's worker to hand in rather
than close; the dossier shows a `changes` verdict **above** the spec.

---

## 9. Order of work

Each step ends green before the next begins. Never big-bang.

1. **Split `core/types.py`** → `core/actors.py`, re-export, suite green. Nothing
   else in this commit.
2. **Split `mcp/tools.py`** → `mcp/gitmoves.py`, suite green. Nothing else.
3. **`core/review.py`** + its `test_core.py` tests. Pure, no I/O, fast.
4. **`core/types.py`** fields and kinds; **`core/replay.py`** coercion. Assert
   an old board with no `review` key still folds.
5. **`core/graph.py`** precedence + **`core/machine.py`** guards, with tests.
6. **`store/live.py`** reviews table + **`verbs/_facts.py`** world half.
7. **`verbs/review.py`**, `update.py`, `take.py`, `plan.py`, registry.
8. **`verbs/pulse.py`** groups, then `mcp/` (schema, tool, render, dossier,
   brief, INSTRUCTIONS), then `ui/index.html`.
9. **`tests/test_topology.py`** seam tests.
10. **Docs, in the same diff**: `ARCHITECTURE.md` (§3 stored-vs-derived, §5 the
    verb table, §6 the tools, §11 — **rewrite the "reviews/reviewer" row rather
    than deleting it**, narrowing the ban and citing this document), `README.md`
    (the tools table, the flow), `CLAUDE.md` (the never-re-introduce list —
    narrow it, do not remove the entry), `docs/design.md` (the new attributes
    and the two groups). Counts and status tables expire; update them.

---

## 10. What NOT to build

Each of these is how v1 got where it got.

* **No reviewer ROLE.** `ROLE_DEV` and `ROLE_AGENT` stay the only two. A
  reviewer is an ordinary agent doing a bounded read.
* **No stored review status.** `CARD_STATUSES` stays three.
* **No `recover`, in any spelling.** An expired review lease is not damage.
* **No automatic reviewer assignment.** The orchestrator decides whether a card
  gets a reviewer at all. Auto-assignment is what made v1's reviewers eat the
  budget of the work they were reviewing.
* **No review requirement that cannot be turned off.** If a board never sets
  `review`, nothing about it changes.
* **No agent id on the board.** §3.3.
* **No reviewer→worker channel.** They speak through the orchestrator, and that
  is what keeps the coordination graph acyclic (§1.1). If a direct channel ever
  seems necessary, you have rebuilt `peer`.

---

## 10b. What actually got built — and where it differs from §2-§7

Green at 201 tests (173 when the feature landed; 28 more were the review suite
itself, every one mutation-checked). `CARD_STATUSES` is still three, there is
no reviewer role, nothing auto-assigns, and a board that never sets `review`
derives exactly as before. Five deliberate departures from the spec above, and
one bug the tests caught:

| §  | the spec | what is built | why |
|---|---|---|---|
| 3.1 | four METHODS on `store/live.py::Live` | four FUNCTIONS over `Live.db` in a new `store/reviews.py` (`claim`, `reviewer`, `reviewing`, `drop`) | `live.py` was at the 200-line budget `tests/test_architecture.py` enforces. The review lease is a cohesive seam of its own — the whole race analysis lives in that module's docstring — so this is a split along a line, not a cut to make room. The DDL stays in `live.DDL`, where every table of that file is declared |
| 5.2 | `verbs/take.py` grows a `review=true` path | **removed entirely** (2026-08-07, second pass): the verifier's ONE door is `taskops_review` — `task=` claims and returns the full dossier, `verdict=` judges. A `review=true` flag on `taskops_take` was briefly built and then deleted: two tool surfaces over the same verb is exactly the duplicate-channel shape that broke v1, and the owner called it. `take` holds the work lease and nothing else |
| 1.2, 5.2 | — | `status=review` does NOT release the work lease; the worker keeps it | §1.2 is the whole point: the worker stays reachable so a `changes` verdict goes back to the agent that already has the context. It is why `graph.derived` puts `review` ABOVE `doing`, and why `machine._not_somebody_elses` needs the §6.3 exception at all (the orchestrator closes a passed card *through* a live lease) |
| 2.3 | `Standing` alone | plus `review.EMPTY`, the default of `Facts.standing` | `check_transition` is called from paths that have no thread to fold; a defaulted field keeps every existing caller and every existing test in `tests/test_core.py` unchanged, which is §0's requirement expressed in a signature |
| 7 | a REVIEW row carries the reviewer's note | a REVIEW row carries no text (there is no verdict yet); a CHANGES row carries the verdict note verbatim | at REVIEW time the only words on the card are the worker's hand-in note, and the move ("assign a verifier") does not depend on them. `tests/test_verbs.py::test_changes_requested_sends_it_back_with_the_note_verbatim` pins the CHANGES half |

**One real bug, found by the optionality test and fixed** (`core/graph.py`):
the `changes` branch was not gated on `card["review"]`, only the `review`
branch was. `review` is in `EDITABLE` — it can be turned OFF after a verdict
was written — and an ungated `changes` meant such a card read `changes`
forever, with no move that could clear it. §6.4 says a card whose flag is off
must derive exactly as it did before the feature existed, so both review
branches are now gated. Mutation-checked against
`test_a_card_without_review_derives_exactly_as_before`.

Two spec items that were missing and are now built:

* **§2.4's call sites.** `verbs/update.py` and `verbs/card.py` derived without
  the review facts, so `status=review` answered `state: "doing"` — the one call
  whose whole point was to stop working on it — and a search never showed a
  review state. `tests/test_verbs.py::test_every_answer_that_names_a_state_knows_about_review`.
* **§5.2's "carry `reviews` on create AND edit."** `core/replay.py::_milestone`
  only carried it on create, so a chapter's review default could not be changed
  after it was written. `taskops_update milestone=… reviews=…` now works; it is
  a DEFAULT for cards planned after it and never retro-flags a card.

The §6.3 exception is deliberately narrow, and a test pins the edge: with two
conflicting verdicts (a `pass` then a `changes`) the orchestrator is refused
like everybody else — it meets the generic "held by <worker>" wall, because the
exception only opens for a standing `pass`
(`tests/test_topology.py::test_two_conflicting_verdicts_leave_the_board_coherent`).

---

## 11. Last task: migrate the axion board off v1

Unrelated to review, and deliberately **last** — do it once everything above is
green. This is the only v1 board worth keeping; every other project was wiped
and starts from zero.

### 11.1 The source, already verified and in hand

The v1 board is served from the box `axion-box` (`10.8.0.2`, WireGuard) at
`~/axion-v3/.taskops/`, and reachable as
`https://taskops.bernardocastro.dev/axion`.

**The source is already downloaded and checksum-verified** (2026-08-07):

```
~/.taskops-migration-backup-20260807-133522/
├── axion-SERVER-authoritative/     ← pulled from axion-box, USE THIS
│   ├── events.jsonl                  410 events · 357,657 bytes
│   │                                 sha256 eb2623ba741ba1704f6e86e9c6ac899d…
│   ├── GUIDE.md
│   └── db.sqlite                     derived, kept only for reference
├── axion-v3-taskops-v1/            ← the laptop's copy of the same board
├── axion-v3-git-hooks/             ← the five v1 hooks, removed 2026-08-07
└── *.mcp.json, claude.json, claude-jp.json
```

The server copy and the laptop copy are **byte-identical** — same sha256, same
length. An earlier note in this project's history claimed the local file was a
partial mirror because `remote.json` reads `{"cursor": 919, "pushed": 2534}`;
that was wrong. Those are v1's two replication counters, not event counts —
the same "two incomparable cursors reconciled by guessing" that
`ARCHITECTURE.md` §10 names as the reason v2 puts a single server `seq` on the
wire. **410 events is the whole board.** Do not go looking for more.

`db.sqlite` is v1's derived index. It is not a migration source and never was;
`events.jsonl` is the truth in both versions. It is in the backup only so
nothing was thrown away.

### 11.2 What the migration produces — dry run already done

`scripts/migrate_v1.py` was run against this exact file into a scratch board.
Every one of the 410 events mapped; **no unknown kind was dropped**:

```
  66 claimed    65 handoff    65 comment    59 commit    58 created
  52 done       21 blocked    12 released    6 status     5 branch    1 message
```

The resulting v2 board: **58 cards**, groups `merge 52 · take 4 · stalled 1 ·
blocked 1 · doing 0`, and **0 pending mentions**.

That zero is correct, not a loss. `MENTIONS.md` §5 flagged the 66 mention-carrying
events (65 `handoff` + 1 `message`) as wanting a human eye. They crossed
intact — but a `handoff` mention naming its own assignee is dropped by design
(assignment already says "this is yours"), and `pending()` clears a mention when
the card closes. With 52 of 58 cards done, nothing is still owed a reply.
**Confirm this rather than assume it**: after installing, run
`_facts.pending_mentions(stores, actor)` per actor and expect an empty list.

### 11.3 Installing it into `~/axion-v3`

Four hazards, all verified present. Handle each before running anything:

1. **`.taskops/remote.json` points at the v1 server** (`url` +
   `token`). v2's `read_config` merges `board.json` with `remote.json`, so
   leaving it makes v2 open a `RemoteBoard` against the **v1** server. Remove it.
2. **The five v1 git hooks are already gone** (removed 2026-08-07, backed up).
   Do not restore them. They pointed at the uninstalled `taskops-cli`
   interpreter and two of them used `|| exit $?`, which blocked every commit —
   the exact `pre-commit` failure `ARCHITECTURE.md` §11 exists to prevent.
3. **72 v1 worktrees live in `.taskops/trees/`**, on v1-style branches
   (`tk/tk-045a24/<slug>` — the slug-in-branch anti-pattern v2 removed). v2
   wants `tk-045a24`, so `gitwork/trees.py::_worktree` will refuse to reuse any
   of them: *"is on X, not Y — remove it or use another card"*. That refusal is
   correct and harmless; 52 of the 58 cards are `done` and need no worktree.
   Decide per worktree, do not bulk-delete.
4. **`tk-790332` has uncommitted work** — 258 added lines across
   `docs/25-investigacion-estrategias.md` and `docs/28-vara-sleeve-vs-book.md`,
   plus an untracked `scripts/audit_panel_grid_drift.py`. **Commit or stash it
   before touching that worktree.** Ask first; it is not yours to discard.

Then, and only then:

```sh
cd ~/axion-v3
rm .taskops/remote.json                 # hazard 1 — the v1 credential and URL
taskops init    # board.json, .taskops/board/, 2 git hooks, .mcp.json,
                # AND the delivery hook in .claude/settings.json (init and join
                # both call _wire). axion-v3 has neither .mcp.json nor
                # .claude/settings.json today (verified 2026-08-07), so both
                # are created fresh — nothing v1 to collide with.

uv run --directory ~/taskops-v2 python scripts/migrate_v1.py \
    ~/.taskops-migration-backup-20260807-133522/axion-SERVER-authoritative/events.jsonl \
    ~/axion-v3/.taskops/board \
    --milestone "axion — imported from taskops v1" \
    --goal "history migrated from the pre-v2 board"
```

Migration is **idempotent** — event ids are content hashes, so running it twice
writes nothing the second time. If you are unsure whether it ran, run it again.

### 11.4 Verify before declaring it done

* `taskops_board` in a fresh session shows the milestone, 58 cards, 52 under
  MERGE;
* pending mentions are empty for every actor (§11.2);
* `.taskops/remote.json` is gone and `.taskops/board.json` is `{}` — that is
  what makes it a LOCAL board rather than one still talking to the v1 server;
* `.taskops/events.jsonl` (v1's file, at the old path) can be deleted **only
  after** the new board reads correctly — the backup is the safety net, not
  that file.

Leave the v1 server running until this is confirmed. Nothing here decommissions
it, and nothing here should.
