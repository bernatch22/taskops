---
name: sweep
description: Write every daily taskops report that is still missing — the unattended backfill. Use when a scheduled task fires, when the machine has been off for days, or when the user asks to "catch up the reports", "escribí los días que faltan", or to fill a hole in the report history.
argument-hint: "[--push]"
---

# Sweep — every day that owes a report

The sweep is a BARRIER, not a clock. It narrates every day that has ENDED, has events, and
carries no narration yet. That is why the trigger does not matter: a scheduled task at 00:05,
a 9am wake-up after a weekend, and a person typing this by hand all converge on the same
files, and the second run costs nothing because it calls no model.

## Run it

```sh
taskops report sweep            # add --push if this project has a remote
```

- It prints the days it narrated, then a line per day it SKIPPED and why.
- `narrated 0 day(s) — every ended day is already written up` is the EXPECTED answer most of
  the time. It is not a failure and it is not worth a paragraph: say it and stop.
- At most 7 days per run (`--limit`). If it says days were left, run it again — that cap
  exists so a first sweep on an old repository is not a hundred model calls at once.
- Today is never narrated: a day is not finished until it has ended, and a report written at
  3pm would be missing its evening permanently.

## Then say what it means

Report in ONE or two lines: which days got written, anything skipped and why. Do not
summarise the reports themselves — each day's file already carries its own narration, and
this task's reader wants to know the backfill happened, not to re-read the week.

Never pass `--force`. It replaces a narration that may have been written or edited by hand,
and it is unrecoverable; only the user can ask for that, per day, by date.

## Committing

The reports are files under `.taskops/reports/`. Commit them if the user's workflow commits
them — that is what makes yesterday's report still true tomorrow:

```sh
git add .taskops/reports && git commit -m "taskops: daily reports"
```
