# Mentions — design, not a Claude hook

Berna asked for two things: keep v1's `@mentions` (currently dropped by
`scripts/migrate_v1.py`), and make sure a dev or a sub-agent finds out about a
mention addressed to them **every turn**, without having to remember to look.

The second half, read literally ("Claude hooks debe comprobar..."), is the one
thing this project's own constitution forbids. `CLAUDE.md` idea #4 — *"Context
travels in the answer, not in a hook"* — and the "never re-introduce" list both
name Claude hooks explicitly, with the cost written down in `ARCHITECTURE.md`
§11: latency, and a second thing to install and drift. This document is the
alternative that gets the SAME outcome — nobody misses a mention, checked on
every single turn — through the mechanism the project already has for exactly
this: layers 2 and 3 of context injection (§2.3), which already run on every
tool call. **No hook, no new file to install, no drift.**

If, after reading this, a literal Claude hook still seems like the right call
for some reason this document didn't account for — stop and ask Berna before
building it; that reverses a decision he made deliberately, more than once.

## 1. The shape of the fact

A mention is not a new kind of event — it is a property of one that already
exists. v1 attached `mentions: list[str]` to two kinds, `message` and
`handoff`; v2 has neither. The natural home is `comment`, which is what both
of those collapsed into during migration (`scripts/migrate_v1.py::map_event`).

```
comment  { "text": "...", "mentions": ["agent:berna/w2", "dev:berna"] }
```

`mentions` is OPTIONAL and EXTRA — `core/event.py::make()` already tolerates
extra body keys (it only checks the kind's *required* keys are present), so
this needs **no change to `KINDS`, no change to `core/types.py`, no change to
`core/replay.py`**. `comment` is `Kind(False, ...)` — history-only, never
folded into card state — which is correct: a mention is a fact about who
should read something, not a fact about the card.

## 2. Pending is DERIVED, not stored — same rule as everything else

The hard part is not storing the mention. It is knowing whether it is still
**pending** — and the project's answer to "is this thing still true" is always
the same: derive it, never write a second fact to contradict the first later.

> A mention of `actor` on `task` is pending until `actor` writes ANY event on
> `task` after it, or the card closes.

That is it. No `read: true` flag, no `taskops_ack` verb, no sweep. The moment
the mentioned actor comments, claims, updates, or releases that card, the
mention resolves itself — by the same logic that already makes `doing` and
`blocked` self-correcting (`core/graph.py`). Ignoring it forever leaves it
pending forever, which is the correct behavior, not a bug to fix.

```python
# core/mentions.py (new, pure, no I/O — same tier as graph.py)

def pending(events_by_task: dict[str, list[Event]], actor: str) -> list[PendingMention]:
    """Every mention of `actor` with no later event from `actor` on that task."""
    out = []
    for task, events in events_by_task.items():
        ordered = sorted(events, key=lambda e: e["ts"])
        for event in ordered:
            if event["kind"] != "comment":
                continue
            if actor not in event["body"].get("mentions", []):
                continue
            if any(e["actor"] == actor and e["ts"] > event["ts"] for e in ordered):
                continue  # actor answered — resolved, forever, with no flag anywhere
            out.append(PendingMention(task=task, by=event["actor"],
                                       text=event["body"].get("text", ""), ts=event["ts"]))
    return out
```

Cost: this is O(events) per call, same order as `graph.derived()` today.
`store/cache.py` already indexes `events(task, ts)`; a `pending()` call at
board scope reads once via `stores.cache.since(0)` (already used by
`stores.state()`) and groups in memory. No new SQL, no new table. If this ever
shows up in a profile, index `(kind, ts)` — already exists — and filter kind
first; do not reach for a stored `read` flag as the fix.

## 3. Where it surfaces — the three layers, reused

**Layer 2 — `taskops_board`.** A new group, ranked ABOVE `stalled` (a mention
is usually more urgent than a card going quiet): `MENTIONS — addressed to
you, not yet answered`. Rendered per actor: the orchestrator's board shows
mentions of `dev:<name>`; a worker's shows mentions of its own
`agent:<dev>/<name>`. This is the ONE-CALL check: the protocol already says
*"open every turn with `taskops_board`"* (both roles, `mcp/server.py`
`INSTRUCTIONS`) — that sentence is doing the job the hook was asked to do.

**Layer 3 — the pulse line.** Every tool result already ends with one line
(`verbs/_context.py::pulse()`, rendered by `mcp/render.py`). Add a mention
count to it so it is visible even when the actor did NOT call `taskops_board`
this turn — e.g. mid-task, calling `taskops_update`:

```
─ ◆ juego de terminal · 2 doing · 1 ready · 1 stalled · ✉ 1 mention for you ─
```

This is the actual "every turn" guarantee: `pulse()` already runs on
`board`, `take`, `update`, `plan`, `dispatch` — every write and the one read
the protocol says to open with. Nothing needs to poll, because nothing was
ever NOT already being called.

**Layer 1 — MCP `instructions`.** One added sentence, static, in
`mcp/server.py::INSTRUCTIONS`: *"a `✉` in the pulse line means somebody
mentioned you — `taskops_card task=<id>` to read it, then act or reply."*
That is the whole onboarding cost. Compare to a hook: zero new files in the
repo, zero new process, nothing that can be configured once and forgotten.

## 4. Writing a mention

`verbs/update.py::run` already builds a `comment` event when `comment=` is
passed with no `status=`. Add `mentions=[...]`:

```python
mentions = _args.strings(args, "mentions")
for who in mentions:
    role_of(who)  # reuse the actor grammar's own validator — refuse a typo'd
                   # actor the same way role_of already refuses a malformed one,
                   # rather than storing an address nobody will ever match
body: dict[str, Any] = {"text": comment}
if mentions:
    body["mentions"] = mentions
events.append(make(card["id"], actor, "comment", body, now))
```

Both roles may already call `update` (`BOTH` in the registry) — a worker
mentioning the orchestrator, or the orchestrator mentioning a specific worker,
both work with no registry change.

## 5. The migration script owes this back

`scripts/migrate_v1.py::map_event` currently drops `mentions` on both `handoff`
and `message` (documented at the top of that file as a deliberate loss). Once
`comment.mentions` exists, fix both:

* `message {"text", "mentions"}` → `comment {"text": ..., "mentions": [...]}`
  — direct, no loss left.
* `handoff {"assigned_to", "mentions"}` → keep the existing
  `edited(assignee=...)` mapping (assignment already implies "this is yours"),
  **and**, only when `mentions` contains someone OTHER than `assigned_to`,
  emit a companion `comment` with empty text and that residual mentions list
  — so a handoff that also looped in a second person does not silently drop
  that second person.

Re-run against the axion board after this ships; 66 events (65 `handoff` + 1
`message`) carried `mentions` and are worth re-checking by hand — diff the
`pending()` output before/after against what a human remembers being owed a
reply.

## 6. What NOT to build

* **No `taskops_ack` / mark-as-read verb.** The derivation already clears
  itself. A verb to clear it manually is the same shape as the `recover` verb
  that was rejected earlier in this project, for the same reason: it exists
  only because something was stored that should have been derived.
* **No Claude hook, no `settings.json` entry, no `SessionStart`/`PreToolUse`
  wiring.** See the top of this document.
* **No push/notification transport** (email, Slack, desktop alert). Out of
  scope — the guarantee this document makes is "found within one turn of
  calling ANY tool," which is what was actually asked for, not "found the
  instant it is written."

## 7. Work list, in order

1. `core/mentions.py` — `pending()`, pure, tested with events fixtures (no
   Stores). Mutation-check: an actor's own later event on the task must clear
   it; an EARLIER one must not.
2. `verbs/update.py` — accept `mentions=`, validate via `role_of`, extend the
   `comment` body.
3. `verbs/_facts.py` or `_context.py` — a `holders`-shaped helper,
   `pending_mentions(stores, actor, now)`, feeding both the board group and
   the pulse count.
4. `verbs/pulse.py` — new `MENTIONS` group, ranked above `stalled`; extend
   `_row()`/pulse dict with the mention count.
5. `mcp/render.py` — render the group; render `✉ N mention(s) for you` in the
   pulse line when count > 0, nothing when 0 (silence when there is nothing to
   say, same as every other group).
6. `mcp/server.py::INSTRUCTIONS` — the one added sentence from §3.
7. `mcp/schema.py` — `mentions` as an optional `array[string]` arg on
   `taskops_update`.
8. `scripts/migrate_v1.py` — the two mapping fixes from §5.
9. `ui/index.html` — optional, secondary: a small badge on a card whose
   thread has a pending mention. Not required for the "every turn" guarantee,
   since the UI is a human's read-only dashboard, not a turn loop.
10. Docs: `README.md` (the tools table gains the `mentions=` arg on
    `taskops_update`), `CLAUDE.md` if the protocol sentence changes anything
    load-bearing, `ARCHITECTURE.md` §6 event kinds table.
11. `tests/test_core.py` (mentions.py), `tests/test_verbs.py` (write + surface
    + self-clearing, end to end through `update`/`board`), `tests/test_mcp.py`
    (pulse line + board group render).

Definition of done, same as every stage in this repo: `./scripts/lint &&
./scripts/test` green, pyright strict included, every new test survives a
mutation-check, and every doc this touches says the truth when it is done.

## 8. What actually got built — and where it differs from §1-§7

All eleven steps are done (green at 155 tests; 173 now, after §9, the
milestone rules, the per-call actor and the board watcher). Zero Claude
hooks, nothing under `.claude/`, no `settings.json`. Five deliberate departures
from the sketch above, each one for a reason:

| §  | the sketch | what is built | why |
|---|---|---|---|
| 2 | `e["ts"] > event["ts"]` decides who answered | sort by `ts` (stable) and compare by POSITION in that list | a frozen or coarse clock makes an answer share the mention's timestamp, and the mention would survive its own reply. `replay` settles simultaneity the same way — stable sort, arrival order — and this had to agree with it |
| 2 | `pending()` handles only "the actor answered" | it also takes `closed`, a collection of card ids | §2's own prose says a closed card clears it; passed in rather than looked up, exactly as `graph.Holders` is, so the module stays pure |
| 3 | `pending_mentions(stores, actor, now)` | `pending_mentions(stores, actor)` in `verbs/_facts.py`, plus `Stores.threads()` | there is no time in the question. And the whole-log read belongs behind `Stores`, not in a verb reaching into `stores.cache` — `store/` is the only layer that knows how events are indexed |
| 4 | `mentions=` extends the `comment` body | same, and `mentions=` **with** `status=` is REFUSED | with a status the comment IS the status event's note, so the address would have been silently dropped. The refusal names the call that works |
| 9 | a badge on a card whose thread has a pending mention | the UI draws the `mentions` group the payload already carries, ranked above STALLED like the board | the group is per-viewer (the credential's own actor), so it says who owes what instead of only that something is owed — and it reuses the row renderer that was already there |

`_context.pulse()` gained a required `actor` argument rather than an optional
one: defaulted, a call site that forgot it would report a silent zero, and the
"nobody misses a mention" guarantee would hold everywhere except there.

## 9. The delivery hook — the owner's reversal (2026-08-06)

Berna, who wrote the no-Claude-hooks rule, reversed it for ONE narrow purpose
after seeing §1-§8 working: **mid-turn delivery**. The gap is real and §6
named it: the pulse line rides only on *taskops* tool results, so a worker
twenty minutes deep in Edit/Bash calls learns of a mention only at its next
board call. A human watching the web board has no way to interrupt that.

The reversal is narrow, and the narrowness is the design:

> **A Claude hook may DELIVER. It may never decide, never store, never write.**

The board stays the single source of truth. Delete the hook and nothing is
lost but immediacy — `pending()` still derives, the pulse still rides, the
group still renders. What stays banned is what v1's hooks actually did:
holding state, gating actions, being a second place where truth lived.

### 9a. The command — `taskops hook claude`

A third subcommand next to the two git hooks in `cli/` (`hook trailer`,
`hook commit` — same layer, same "never break the caller" contract). It:

1. Reads the Claude-hook JSON from stdin (`tool_input`, `cwd`, event name).
2. Resolves the board via the existing `find_root` walk from `cwd`.
3. Resolves the ACTOR, in order:
   - `TASKOPS_ACTOR` env, if the hook process has it;
   - else, any path in `tool_input` (or `cwd`) inside `.taskops/trees/tk-X/`
     names card tk-X — the actor is its live lease holder, else its assignee.
     This is what makes SUB-AGENT delivery work: the hook process does not
     inherit the worker's shell env, but the worker's tool calls all touch its
     own worktree, and the worktree names the card, and the card names them;
   - else `dev:$USER` — the orchestrator.
4. Throttles per actor: a stamp file under `.taskops/` (gitignored), skip
   silently if that actor was checked < 30s ago. A hook that adds a round
   trip to every Edit is the v1 latency bug reborn.
5. Queries `pending_mentions` through the normal `Board` (local read, or the
   remote RPC with a 2s timeout). **Any failure → exit 0, no output.** A
   mention system that can break a turn is worse than no mention system.
6. If pending mentions exist for that actor, emits the Claude-hook JSON that
   injects context (`hookSpecificOutput.additionalContext`), one line per
   mention: `✉ taskops: dev:berna mentioned you on tk-X: "…" — reply on the
   card (taskops_update) and it clears.` If none: **no output at all** —
   silence costs zero context, and this fires on every tool call.

   The implementer MUST verify the exact output contract for `PostToolUse`
   and `UserPromptSubmit` against current Claude Code hooks documentation
   rather than trusting this sketch — the JSON shape has changed before.

### 9b. The wiring — written by `init`/`join`, like everything else

`gitwork/install.py` gains `write_claude_hooks(repo)`: merge into the
project's `.claude/settings.json` (create if absent, MERGE if present — same
non-clobbering contract as `write_mcp`):

- `PostToolUse` (no matcher — every tool) → `taskops hook claude`
- `UserPromptSubmit` → same command (turn-start delivery for the dev)

Idempotent, marked recognizable so `join` twice does not duplicate entries.

### 9c. The human writes from the board

The UI's card panel gains ONE write: a comment box with a mention picker
(actors seen in `TEAM`), POSTing `verb=update` with `comment` + `mentions`
through the `rpc()` helper the page already has — the same door, the same
token, the same server-side validation (`role_of` refuses a typo'd address).
The UI stays a signal-refetch design for everything it *shows*; this is its
first and only write, and it exists so a human watching the board can reach a
working agent mid-turn without opening an MCP session. Together with 9a that
closes the loop Berna asked for: human types on the board → agent's very next
tool call carries the ✉ line.

### 9d. Docs this reverses

`CLAUDE.md` idea #4 and the never-re-introduce list must be REWRITTEN, not
appended to: the ban narrows from "Claude hooks" to "Claude hooks that decide
or store". `ARCHITECTURE.md` §11's hook row gets the same narrowing, §10
gains the delivery channel. `README.md` quickstart mentions what `init`/`join`
now write. This section is the paper trail for why the rule moved — cite it.

### 9e. What actually got built — and where it departs from 9a-9c

Built by hand (the first agent sent at this was stopped mid-way; its partial
work was kept where it was right). Three departures, each one earning its
place:

| § | the sketch | what is built | why |
|---|---|---|---|
| 9a.5 | "queries `pending_mentions` through the normal `Board`" | a dedicated read verb, `mentions` (`verbs/pulse.py`), and the hook calls THAT | every other read opens with `live.renew(actor)` — right for a call the actor typed (the call IS the heartbeat), fatal here: a hook firing on the orchestrator's `Read` of a dead worker's worktree would renew that worker's lease and its card would never reach STALLED. A stored `doing` grown back by the side door. The verb renews nothing, and a test pins it |
| 9a.3 | the hook resolves the card's holder itself | the hook sends `for_task=tk-X` and the SERVER resolves the addressee (`pulse._addressee`) | the holder lives in `live.sqlite`, which a remote client cannot read — resolving client-side would have worked only for local boards, silently |
| 9a.4 | throttle, then ask | the stamp is written BEFORE the board is asked | a board that is down would otherwise be retried once per keystroke: the throttle exists precisely for the case where asking is expensive |

The stamp file is `.taskops/hook-seen.json` (gitignored by `install.IGNORED`),
keyed per reader. `board.open_board` gained an optional `timeout` so the hook's
remote reads give up in 2s; every other caller keeps the 20s default.

Verified end to end, live and in `tests/test_claude.py` (6 tests, each one a
property from the module docstring, all mutation-checked): mention → hook
emits the ✉ context JSON; 1s later → throttle, silence; no env, only a
worktree path in `tool_input` → the worker is resolved through
path → card → holder; the worker replies on the card → the hook is silent with
no verb called; no board / garbage stdin → exit 0, no output; `join` twice →
one entry, foreign hooks kept.
