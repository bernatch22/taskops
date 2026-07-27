---
name: handoff
description: Hand your current task back to the queue with your progress recorded, or pass it to a specific agent. Use when out of context, out of depth, blocked, or when the user says stop, hand off, or switch tasks.
---

# Hand off

The honest move when you cannot finish. Abandoning the task also works — the lease lapses in
about fifteen minutes — but that throws away everything you learned, and the next agent starts
from zero on a task that looks untouched.

1. **Commit what works.** Half-finished work in a commit on the task branch is recoverable;
   half-finished work in a dead session is not. If it does not build, say so in the comment.

2. **Release it, with a real comment:**

   ```
   taskops_update task=<id> status=released comment="<where you got to>"
   ```

   The comment is the whole point. Write:
   - what you finished, and what is on the branch
   - what you tried that did NOT work, and why — this is what saves the next agent an hour
   - the exact next step as you understand it
   - anything you discovered that the spec got wrong

3. **If a dependency is what stopped you**, say so in the graph rather than only in prose:

   ```
   taskops_update task=<id> blocked_on=<other-id> comment="…"
   ```

   A dependency that lives only in a comment is one the scheduler will walk somebody else
   straight into.

4. **If a specific agent should take it**, add `mentions="<their actor>"` so it lands in their
   inbox rather than waiting for them to notice the queue.

Do not mark a task `done` because you are stopping. `done` means a commit bound to the task
and the outcome achieved; the server will refuse it anyway, and trying is how a board starts
lying.
