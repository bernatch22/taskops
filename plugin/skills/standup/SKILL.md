---
name: standup
description: Report what changed on the project — per actor, what is in flight, and what needs a human. Use when the user asks how it is going, for a status update, a standup, or what the other agents have been doing.
argument-hint: "[window: 24h, 7d]"
---

# Standup

1. `taskops_report standup` with `since=$1` (default `24h`).
2. `taskops_report fleet` — who is alive right now.

Then write the report for a HUMAN, not a dump of the tool output:

- Lead with what needs them. Blocked tasks and `SILENT` fleet rows are the only two things
  they can act on; everything else is progress.
- A `SILENT` agent still holds a claim but has gone quiet past the grace period. Say which
  task is stuck, and offer to release it (`taskops_update task=<id> status=released
  comment="…"`) so somebody else can pick it up.
- Group by outcome, not by actor, unless they asked per person.
- Numbers only where they change a decision. "3 of 8 done" is useful; "17 events" is not.

Do not editorialise about pace. The log says what happened; a generated report that flatters
anybody is worse than no report.
