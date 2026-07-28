---
name: claim
description: Claim the next task from the shared list and start working on it — creates the branch and reads the spec. Use when starting work, when the user says "next", "what should I work on", "pick up a task", or at the start of a session where you hold nothing.
argument-hint: "[task-id]"
---

# Claim work

1. Call `taskops_next` (pass `task=$1` if an id was given, otherwise let the scheduler
   choose — it also avoids handing you a file another live agent is editing).

2. If it returns nothing, READ THE REASON and act on it rather than asking the user:
   - everything blocked → report which tasks need a human, and offer to unblock one
   - everything claimed → say who holds what (`taskops_report board` shows the holder per card)
   - nothing planned → offer to plan the work with `/taskops:plan`

3. Create the branch it names, exactly:

   ```bash
   git switch -c <the branch from the output>
   ```

   Not a branch of your own choosing. The commit guard matches that exact shape.

4. **Read the ⚠ collision section if there is one.** Those are other tasks touching your
   files. Message them BEFORE editing, not after the merge:

   ```
   taskops_update task=<theirs> comment="I'm about to change <file> for <mine>. Shout if
   that clashes." mentions="<their actor>"
   ```

5. Read the spec and start. If the spec is too thin to act on, say so and ask — do not guess
   and do not silently reinterpret it. A task done correctly against the wrong understanding
   is the most expensive outcome here.

Commit normally when you have something working. The `Task:` trailer is added for you.
