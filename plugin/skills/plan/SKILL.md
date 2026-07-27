---
name: plan
description: Decompose work into tasks with dependencies and put them on the shared list. Use when the user describes a feature, a refactor or a bug that needs more than one step, or says "plan this", "break this down", "make tasks".
---

# Plan

YOU do the decomposition — read the code first. `taskops_plan` only makes it durable.

**Understand the work before you split it.** One `megabrain_ask` or a read of the real files.
A plan written from the user's sentence alone invents tasks that do not match the code.

Then call `taskops_plan` ONCE with the whole tree. Each entry:

- **`title`** — the outcome, not the activity. "Bind commits to tasks", not "work on commits".
- **`spec`** — the brief for a FRESH agent with none of your context, possibly on another
  developer's machine three days from now. It must say: what **done** looks like concretely
  enough to disagree with, what must **not** change, and **where to start** (the files, the
  sibling to copy, the test that pins the behaviour). A one-line spec is the single most
  common cause of an agent doing the wrong thing correctly.
- **`files`** — the edit surface. This is what stops two agents being handed the same file.
- **`after`** — dependencies, as the 0-based index of an earlier entry in this same call.

```json
[
  {"title": "Add the events table", "spec": "…", "files": ["storage/_events.py"]},
  {"title": "Board reads it",       "spec": "…", "files": ["render/board.py"], "after": [0]}
]
```

**Check the last line of the output.** If it says NOTHING is ready, your `after` references
have a cycle or an off-by-one — fix it now, because otherwise the first agent to ask for work
gets nothing and nobody will know why.

Prefer fewer, larger tasks over many tiny ones. Every task costs a claim, a branch and a
context load, so a task smaller than that overhead is worse than a line in another task's spec.
