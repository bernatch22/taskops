---
name: standup
description: Report what changed on the project — per actor, what is in flight, and what needs a human. Use when the user asks how it is going, for a status update, a standup, or what the other agents have been doing.
argument-hint: "[window: 24h, 7d]"
---

# Standup

1. `taskops_report standup` with `since=$1` (default `24h`).
2. If they asked about a DAY ("what got done yesterday"), use `taskops_report` with
   `kind=day` and `date=yesterday` instead: a calendar day is the same report tomorrow,
   and it carries the commits and their diff sizes per closed card.

Then write the report for a HUMAN, not a dump of the tool output:

- Lead with what needs them. Blocked tasks are what they can act on; everything else is
  progress.
- A card sitting `claimed` with nothing moving is the other thing worth naming. Offer to
  release it (`taskops_update task=<id> status=released comment="…"`) so somebody else can
  pick it up.
- Group by outcome, not by actor, unless they asked per person.
- Numbers only where they change a decision. "3 of 8 done" is useful; "17 events" is not.

Do not editorialise about pace. The log says what happened; a generated report that flatters
anybody is worse than no report.
