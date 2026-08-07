# Fan-out — why eight green cards did not make one system

A post-mortem of the milestone `ms/ui-react-dashboard-nova` (2026-08-07), and
the paper trail for a decision **not yet taken**. It reports what happened, with
the evidence, and ranks four proposals against the cost of each.

Every file:line below was checked against the tree at
`ms/ui-react-dashboard-nova` @ `c347021` on 2026-08-07. Where a defect has since
been picked up by a card, that card is named and the defect is in the past tense.

---

## 0. The result in one paragraph

Eight cards, eight workers, eight worktrees, eight `--no-ff` merges into one
integration branch. **Zero merge conflicts. Zero stale leases. No `recover`
needed, and none exists.** The coordination mechanism — the lease, the pinned
worktree, the dependency graph, the collision warning — did its entire job
without a single intervention. And the merged tree it produced contained two
`ago()` with different output, three `initials()` with three different answers,
and a served page that still rendered placeholders after six of the eight cards
had closed green.

Nothing in the board was wrong. That is the point of the document.

---

## 1. The plan, and what it actually was

`taskops_plan` wrote eight cards in one call. Their declared shape, read back
from `.taskops/board/events.jsonl`:

```
tk-3b4715  after []            scaffold: ui/package.json, build.mjs, tokens.css, main.tsx
tk-5341aa  after [tk-3b4715]   data layer: client.ts, types.ts, useBoard.ts
  ├ tk-4e0fdb after [tk-5341aa]  chrome: Header, TabNav, KpiRail, AvatarStack
  ├ tk-a7f52a after [tk-5341aa]  pages/Attention.tsx, components/board/GroupRow.tsx
  ├ tk-0d233a after [tk-5341aa]  pages/Board.tsx, board/Column.tsx, board/CardTile.tsx
  └ tk-38c876 after [tk-5341aa]  pages/Hours.tsx
tk-e85ced  after [tk-0d233a]   the card drawer
tk-28e585  after [tk-e85ced]   the headless smoke harness + docs
```

Two cards had to be **invented mid-flight**, after the fan-out merged, to repair
what it produced:

```
tk-ab86b6  after []            one ago(), in format.ts        commit 3c79162
tk-aa77c1  after [tk-ab86b6]   the pages replace the slot     commit 065af09
```

So the milestone as executed was a serialized head of two cards, a wave of four,
and then two repair cards nobody planned. The four fan-out cards were assigned
to `agent:berna/w3..w6` at one timestamp (`1786126487.012904`, four `edited
assignee` events sharing it) and ran concurrently.

**Their declared `files` were pairwise disjoint.** Check them above: `chrome/*`
vs `pages/Attention + board/GroupRow` vs `pages/Board + board/{Column,CardTile}`
vs `pages/Hours`. Not one path appears twice. This matters in §4.

---

## 2. Defect one — two `ago()`, which is how they drifted

`tk-a7f52a` (w4) wrote a duration formatter in
`ui/src/components/board/GroupRow.tsx`. `tk-0d233a` (w5) wrote one in
`ui/src/components/board/CardTile.tsx`. Both are correct. They disagree:

| input | GroupRow's `ago` | CardTile's `ago` |
|---|---|---|
| 40 s | `just now` | `40s` |
| 300 s | `5m ago` | `5m` |
| 5000 s | `83m ago` | `83m` |

(Both bodies are recoverable verbatim from the deletion diff of `3c79162`.)

The same card, on the Attention tab and on the Board tab, told the reader two
different things about the same fact. The duplication was not the bug — the
duplication was the **mechanism that permitted the divergence**, and it appeared
in the same fifteen minutes in two branches neither of which could see the other.

Repaired by `tk-ab86b6` (w7), commit `3c79162`, which created
`ui/src/format.ts` with one `ago()` (the bare magnitude — `45s`, `5m`, `3h`,
`2d`) and deleted both originals with no shim. The choice is argued in that
file's own docstring: the suffix belongs to the caller, not to the quantity.

---

## 3. Defect two — three `initials()`, and the de-duplication card that missed two of them

Repaired by `tk-ae02c1` (w10), commit `46feb44`, merged at `b41fa9b`. Read below
in the past tense; §3.1 is what replaced it, and why the obvious fix was wrong.

At `c347021`, three functions in `ui/src` turned an actor string into an avatar
glyph, and no two agreed:

| site | body | `agent:berna/w4` → |
|---|---|---|
| `ui/src/format.ts:45` | `shortActor(actor).slice(0, 2).toUpperCase()` | `W4` |
| `ui/src/pages/Hours.tsx:256` | `(tail.split(":").pop() ?? tail).slice(0, 2).toLowerCase()` | `w4` |
| `ui/src/components/chrome/AvatarStack.tsx:11` (named `initial`) | `(name.trim()[0] ?? "?").toUpperCase()` | `W` |

`AvatarStack` rendered `initial(member.actor)` for every member of `board.team`
(`AvatarStack.tsx:55` at `c347021`), and `Header.tsx:157` was its only caller. A
board worked by `agent:berna/w1 … w8` therefore drew **eight identical `W`
discs** in the header.

Read the docstring immediately above that function, `AvatarStack.tsx:9-10`:

> `dev:berna` → "B", `agent:berna/w3` → "W". The tail is the person; the head is
> the role, and **a stack of five "A"s would say nothing.**

The worker reasoned about exactly this failure, wrote the objection down, and
then shipped its own instance of it — because on this board the tail is not the
person, `w3` is, and the head it stripped was the only thing that varied. This
is not carelessness. It is a correct rule (`agent:` is noise) applied to an
actor-naming convention the worker had no occasion to look at, in a worktree
where no other avatar existed to compare against.

**The sharper finding is what happened to `tk-ab86b6`, the card whose whole job
was de-duplication.** Its acceptance criteria, as planned, read:

> WHEN `ago`/`shortActor`/`initials` are searched for in `ui/src` THEN exactly
> one definition of each exists, in `format.ts`

It closed green. Two definitions of `initials` remained. The worker was not
wrong: `git ls-tree -r 3c79162^ -- ui/src` lists twelve files, and neither
`pages/Hours.tsx` nor `components/chrome/AvatarStack.tsx` is among them.
`tk-ab86b6` was cut from `1ddd794`; `tk-38c876` merged at `1bb6c9c` and
`tk-4e0fdb` at `57cbf89`, both **after** that branch point. The criterion was
true in the only tree its worker could see and false two merges later.

A repair card inherited the exact blindness it was written to repair.

### 3.1 The repair, and the second error it caught — in the brief

`tk-ae02c1` (w10) collapsed the three into one: `ui/src/format.ts:62`
`initials()` over the single `shortActor()` at `format.ts:39`, with
`AvatarStack.tsx` and `Hours.tsx` now importing it (`AvatarStack.tsx:7`,
`Hours.tsx:27`) and their local copies deleted. At `b41fa9b` there is exactly
one of each.

The number of glyphs is **three**, not the two the card's brief asked for, and
the reason is the interesting part:

> Two would have fixed exactly that board and broken the next one: the live
> board already carries `w1` AND `w10`, which share their first two glyphs.
> — `ui/src/format.ts:44-53`

The brief was written by the orchestrator from memory of the session, and at the
moment it was written the team ran `w1 … w8`, where two glyphs do separate
everyone. By the time the card was worked, `w9` and `w10` existed — this
document's own worker, and the one fixing the defect. The brief's factual claim
had expired between writing it and reading it, and w10 found that out by
rendering against the *live* board rather than against the sentence it was
handed.

Note where that failure sits. It is not §7.1 (search finding nothing) or §7.4
(no reader of the merged tree). It is the same shape as §7.2, one layer up: **a
claim stated as prose in a brief cannot be checked, and this one was false.**
The instruction that caught it — verify the spec's claims against the artifact,
do not repeat them — is the same instruction that produced this section's
timestamps, and it is the cheapest control in the document. The count in
`format.ts:63` is `slice(0, 3)` because somebody checked.

---

## 4. Defect three — six green cards and a placeholder page

`tk-4e0fdb` (w3) owned `App.tsx`, the shell the three pages plug into. It
documented the seam **in a comment** (`git show 57cbf89:ui/src/App.tsx`, lines
9-27):

```
 *   tk-a7f52a  <AttentionPage board={board} onOpen={openCard} />
 *   tk-0d233a  <BoardPage board={board} onOpen={openCard} />
 *   tk-38c876  <HoursPage report={…} />
```

What the three sibling cards actually shipped:

| comment | code |
|---|---|
| `<AttentionPage board onOpen>` | `Attention({ board, openCard, now })` — `pages/Attention.tsx:172` |
| `<BoardPage board onOpen>` | `Board({ board, openCard })` — `pages/Board.tsx:138` |
| `<HoursPage report={…} />` | `Hours({ client })` — `pages/Hours.tsx:79` |

Three names wrong, three prop lists wrong, one page (`Hours`) reading through a
`client` rather than receiving a payload — a real design decision the comment
does not contain, because the comment predates it.

And the contract was not merely unread: **it landed last.** By the `merged`
events, `tk-a7f52a` integrated at `1786126801`, `tk-0d233a` at `1786126839`,
`tk-38c876` at `1786126914`, and `tk-4e0fdb` — the card that wrote the contract
— at `1786127001`. The three pages could not have obeyed a prose contract that
did not exist in any tree while they were being written.

Meanwhile every card was honestly green. `tk-4e0fdb` rendered a `Slot`
placeholder and satisfied its criteria; each page compiled and satisfied its
own. The served bundle showed placeholder panels, and nothing on the board said
so, because **no card's criteria were about the served page**. Repaired by
`tk-aa77c1` (w8), commit `065af09`, whose diff is 66 lines of `App.tsx`: delete
the `Slot`, import the three pages, adapt each call site.

---

## 5. The control, and what it proves

`ui/src/types.ts` has **one** definition of each payload type. Nine files import
from it — `client.ts`, `useBoard.ts`, `components/board/CardTile.tsx`,
`components/chrome/{AvatarStack,Header,KpiRail}.tsx`,
`pages/{Attention,Board,Hours}.tsx` — with zero duplication and zero drift.

Same eight agents. Same session. Same instructions. Same repository conventions.

The only difference is **when it existed.** `types.ts` landed in `tk-5341aa`,
serialized (`after: [tk-3b4715]`) and merged at `777a0f3` before any of the four
parallel cards was assigned. Every one of those four found it by ordinary search
and imported it. `format.ts` did not exist when they branched; neither did the
other three's helpers.

The duplication is not a discipline failure. It is a **visibility** result:
search resolves against a tree, and a concurrent branch is not in it. A worker
that obeys `CLAUDE.md`'s "Do not duplicate. Search first" and searches correctly
finds nothing, correctly, and writes the helper — which is the correct move
given what it can see. Four workers doing the right thing produce four helpers.

---

## 6. Why the board's own warning was structurally blind

`src/taskops/verbs/_context.py:64`:

```python
def collisions(stores: Stores, card: Card, now: float) -> list[dict[str, Any]]:
    """Cards claiming the same files right now. A warning, never a lock — the
    worktrees already make it impossible to overwrite each other's edits."""
    mine = set(card["files"])
```

It intersects the declared `files` of the holder's card with the declared
`files` of every other open, held card. The four fan-out cards declared
pairwise disjoint paths (§1). The intersection was empty. **The warning was
silent, and it was right to be silent.**

> Collision detection lives in path space. This class of failure lives in symbol
> space. Four cards that touch no common file can still write the same concept
> four times, and no intersection of paths will ever see it.

That sentence is the finding. Everything in §7 is an argument about what, if
anything, to do with it.

---

## 7. The four causes, stated as claims somebody can disagree with

1. **Parallel agents search correctly and correctly find nothing.** Structural,
   not negligent (§5). No amount of instruction fixes it, because the
   instruction was obeyed.
2. **A seam expressed as prose cannot be checked; expressed as a type it is a
   compile error in every worktree at once** (§4). `types.ts` was a type and
   held four ways; `App.tsx`'s slot table was a comment and held zero.
3. **Every card's acceptance criteria measured its own part.** Not one measured
   the whole, so six greens summed to a placeholder. `tk-ab86b6` shows the
   sharper version: a criterion phrased about `ui/src` was evaluated against a
   worktree, and the two are not the same directory (§3).
4. **The merged tree has no reader until the orchestrator looks.** Each worker
   verified in a tree where its file was the only new one. Every defect in this
   document exists *only* in the integration branch — a place no worker ever
   opens.

---

## 8. The proposals

Each is judged against the standing allergies: no stored derived state, no
repair verbs, no roles, no hook that decides (`ARCHITECTURE.md` §11, `CLAUDE.md`
"never re-introduce"). Ranked worst-first, so the recommendation lands last.

### A. A merge-time symbol report — *rejected*

**The idea.** `taskops_merge task=` already runs `git merge --no-ff` inside the
integration worktree (`gitwork/trees.py:66-74`, `merge_card` → `tree =
ensure_milestone(...)`). The whole merged tree is on disk at that instant. After
a clean merge it could scan the milestone's touched files and name every
exported symbol that now has more than one definition. Derived, read-only,
nothing stored, no new verb, no role — and it is precisely the second reader §7.4
says the merged tree never had. In this milestone it would have caught `ago()`
at `1ddd794` and `initials()` at `57cbf89`, minutes after each landed.

**The objection, at full strength.** *taskops does not parse source code, in any
language, anywhere.* The board's entire model of a file is a path string:
`Card.files` is documented as "the edit surface as the planner understands it —
a hint, never a lock" (`core/types.py:85`), and `collisions()` is set
intersection over those strings. `gitwork/` runs git and reads git's output;
`store/` reads SQL; `core/` is pure. Nothing anywhere opens a `.tsx` and asks
what it exports.

A symbol scanner is the first component in the system that would have to know
what a language is — and then, immediately, *which* language. Ship it for
TypeScript and taskops silently becomes a worse tool for the Python board it is
written in, the Go board somebody joins with, the mixed repo. Ship it for both
and it is two parsers, then three, then a plugin surface, and the layering rules
of `ARCHITECTURE.md` §14 have nowhere to put any of it: `verbs/` may not run git
or render, `gitwork/` is a git wrapper, `mcp/` is transport.

There is also a cheaper counter-argument that has nothing to do with parsing: a
duplicate-symbol report is **noisy by construction**. `Tone` and `accentInk`
in this very tree share a shape and are deliberately not the same idea — see the
note at the foot of `ui/src/format.ts`. A report that flags them teaches the
orchestrator to skim past it, and a warning nobody reads is worse than none.

**Verdict: rejected.** Not softened. The language-agnosticism is not an
inconvenience to be routed around with a per-project hook or a `taskops tidy`
subcommand — those relocate the parser, they do not remove it, and `tidy`
(`gitwork/trees.py:125`) removes integrated worktrees, which is not this. A
project that wants this check already has the tool for it: a lint rule, in its
own toolchain, run by `./scripts/lint`, which every card's criteria already
require to be green. That is where a language-specific check belongs. The
correct fix for §3 is a `no-duplicate-exports` rule in `ui/`, owned by `ui/`.

### B. Milestone acceptance criteria — *worth doing, if a milestone criterion is written honestly*

**The idea.** A `Card` has `criteria`. A `Milestone` (`core/types.py:94-115`)
has `id`, `title`, `goal`, `rules`, `reviews`, `branch`, `status`, `created` —
and nothing that says what the *chapter* is accepted against. "The served page
renders all three tabs against a real board" is a milestone criterion. It is
false for the entire window in §4, on a board where every card was green.

The shape already exists: `rules` is "a flat list of sentences … the chapter's
half of the spec" (`core/types.py:98-106`) and travels into every `take`.
`criteria` would be its sibling — spec, not status, nothing derived, nothing
stored that could become wrong. `_land()` (`mcp/gitmoves.py:74-95`) already
refuses while any card is open; it could render the criteria and require the
human to answer them before the trunk moves.

**The cost.** One field on a TypedDict, one render in the landing gate, one
paragraph of docs. Small.

**The objection.** It changes nothing unless the criteria are written to be
*falsifiable by looking*, and the same orchestrator that wrote eight per-card
criteria and no whole-system one is the one who will write them. A milestone
criterion that reads "the dashboard works" is a comment again — §7.2 all over,
one level up. And `_land()` runs at the *end*: it would have caught the
placeholder page before `main` moved, but hours after the four workers finished,
which is the wrong end of the loop for the duplication defects.

**Verdict: worth doing, narrowly.** It closes the specific hole in §4 — a
milestone that ships without anyone having asked whether the assembled thing
runs — and it costs almost nothing. It does not touch §2 or §3.

### C. A plan-time shape warning — *not worth it*

**The idea.** `plan` sees the whole tree in one call (`verbs/plan.py:1-11`, and
`run()` iterates every row before writing any card, `plan.py:38-60`). N cards
with no `after` between them, whose `files` share a directory prefix, is a
fan-out onto a shared surface. Warn in the answer; never refuse.

**The cost.** ~15 lines in a verb that is already 156 of a 200-line budget, plus
a test.

**The objection, which is fatal.** Look at what it would have said here. The
four fan-out cards share the prefix `ui/src/` — and so does *every card in the
milestone*, including the two serialized ones. Tighten the prefix to two
segments and the wave splits into `ui/src/components/chrome`,
`ui/src/pages`, `ui/src/components/board` and `ui/src/pages` — one pair, and the
pair (`Attention`, `Hours`) is not where either duplication happened.
`initials()` crossed `pages/` ↔ `components/chrome/`, which the heuristic scores
as *unrelated*.

So at the loose setting it fires on every parallel plan ever written, and at the
tight setting it misses the actual defect. That is not a tuning problem; the
signal it measures — path adjacency — is the same path space §6 already showed is
the wrong space. A warning that is right about a thing nobody was wrong about is
how a board teaches its orchestrator to stop reading warnings.

**Verdict: no.** It is proposal A's blindness dressed as a heuristic.

### D. Walking-skeleton ordering — *the recommendation*

**The idea, and it is not new here — it is the generalisation of the one thing
that worked.** Before fanning out, serialize enough cards to land a **thin
vertical slice that runs**: scaffold, data layer, shell, and *one* page wired
end to end through the real shell against the real payload. Then fan out the
rest.

This milestone did exactly that for the data layer and got exactly zero
duplication in it (§5). It did *not* do it for the shell: `tk-4e0fdb` (the seam
owner) was dispatched **in the same wave** as the three pages that plug into it,
which is the whole of §4. Had `App.tsx` plus one page landed before the wave:

- `<AttentionPage board onOpen>` would have been an exported prop type in the
  merged tree, not a comment in a branch that landed last. The other two pages
  would have imported it, and a mismatch would be a compile error in every
  worktree at once (§7.2).
- `format.ts` would have existed, with `ago()` and `initials()` in it, found by
  the ordinary search each of the other workers already ran (§7.1) — because the
  first page to need a duration formatter would have written one *before* the
  others branched.
- "the served page renders a real tab" would have been true from card three
  onward, so §4's failure mode would be visible at every merge rather than at
  the end.

**The cost.** Wall-clock. One more serialized card before the parallelism starts
— here, the shell plus one page instead of four cards at once. Against it: two
unplanned repair cards (`tk-ab86b6`, `tk-aa77c1`), one more (`tk-ae02c1`), and
this document. The fan-out did not save time; it moved it.

**The objection.** It is a planning discipline, not a mechanism — nothing
enforces it, and `CLAUDE.md`'s own quality bar is full of disciplines that a
tired orchestrator skips. It is also not free of judgment: "thin enough to land
fast, thick enough to fix the seams" has no test. Fair. But every alternative
above pays code, a parser, or a false-positive budget for a *partial* version of
what ordering gives for nothing, and D is the only one of the four with a
control experiment in this very tree proving it works.

---

## 9. Recommendation

**Adopt D. Adopt B as one field. Reject A and C.**

Concretely:

1. **The planner serializes the seams.** A milestone that fans out N cards onto
   one surface lands the scaffold, the shared types, the shell, and one page
   wired end to end *first*. Every later card then plugs into something that
   runs, and every seam it must honour is a type in its worktree rather than
   prose in somebody else's branch. Cost: one serialized card. Evidence: §5.
2. **A milestone gets `criteria`, next to `rules`** — spec, not status, rendered
   by `_land()` before the trunk moves. It makes "six green cards and a
   placeholder page" a question somebody has to answer out loud. Cost: one
   TypedDict field and one render.
3. **Language-specific duplicate detection belongs in the project's own
   linter**, not in taskops. For this repo that is a `no-duplicate-exports` rule
   under `ui/`, run by `./scripts/lint`, which every card's criteria already
   require. taskops does not learn to parse TypeScript.
4. **A brief is evidence, not fact.** Every spec in this milestone was written
   by the orchestrator from memory of a long session, and at least two carried a
   claim that was false by the time it was read (§3.1). The worker verifies
   against the artifact — the live board, the milestone branch, the file — and
   corrects the brief in its close note. This costs nothing and it is the only
   control in this document that caught an error *before* it merged.
5. **Nothing is added to `collisions()`.** It answers a path-space question
   correctly and should keep answering only that. Widening it to guess at
   symbols would make it wrong at a job it currently does right.

The board was not the failure here. Eight parallel workers, zero conflicts, zero
repairs, no `recover` — the mechanism worked exactly as designed. What the
milestone learned is that **coordination is not integration**: keeping eight
agents from colliding is a different problem from making their eight outputs one
system, and the second one is solved by what you land first, not by what you
warn about later.

---

*Sources. §3's three-copy state is quoted at `ms/ui-react-dashboard-nova` @
`c347021`, the tree it describes; §3.1 and every other current-tense claim are
verified at `b41fa9b`, the branch head after `tk-ae02c1` merged.
`.taskops/board/events.jsonl` (the plan, the dispatch timestamps, the merge
order, the criteria as written); `src/taskops/verbs/_context.py:64`;
`src/taskops/core/types.py:85,94-115`; `src/taskops/verbs/plan.py`;
`src/taskops/mcp/gitmoves.py:38-95`; `src/taskops/gitwork/trees.py:66,125`;
`ui/src/pages/Attention.tsx:172`; `ui/src/pages/Board.tsx:138`;
`ui/src/pages/Hours.tsx:79`. At `c347021` only: `ui/src/format.ts:45`,
`ui/src/pages/Hours.tsx:256`, `ui/src/components/chrome/AvatarStack.tsx:9-11,43,55`.
At `b41fa9b`: `ui/src/format.ts:39,44-53,62-63`,
`ui/src/components/chrome/AvatarStack.tsx:7,57`, `ui/src/pages/Hours.tsx:27,214`,
`ui/src/components/chrome/Header.tsx:157`. Commits `3c79162`, `065af09`,
`46feb44`, `57cbf89`, `1ddd794`, `1bb6c9c`, `777a0f3`, `b41fa9b`.*
