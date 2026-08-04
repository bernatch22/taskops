# Reports: the record that cannot flatter anyone

A board tells you what is open. A report tells you **what happened** — and on a project where most
of the typing is done by models, that is the difference between a team that knows what it built and
a team that has a directory of changes nobody can account for.

Every report here is a **projection of the event log**. Nothing is written by hand into a report and
then trusted; the facts are derived, every time, from an append-only log with content-hashed ids
that lives in git. A report cannot be out of date without saying so, and it cannot be edited into
something flattering without the edit being visible.

---

## 1 · Why this matters more than it sounds

Three failures this exists to prevent, all of them observed:

**"Done" that nobody can account for.** An agent closes five cards overnight. The board is green.
Nothing in a green board distinguishes five careful implementations from five confident summaries
of work that was not done. A day report lists every card closed, **who** closed it, how long they
held it, and every commit with its diff size — so the question "was this real" has an answer that
does not require reading the whole diff.

**Memory that dies with the session.** A session plans, decides, discovers that the obvious
approach fails, and ends. Tomorrow's agent re-derives all of it, badly. The narration is where
"we tried X, it failed because Y" survives — and it survives in the repository, not in somebody's
scrollback.

**A team that cannot see each other.** Two developers, four agents, three machines. Reports sync
with `push`/`pull` like everything else, so "what did the other side do yesterday" is a file, not a
meeting.

## 2 · The generated views

```sh
taskops report                       # the board
taskops report standup --since 24h   # what changed, per actor, and what needs a human
taskops report day                   # one calendar day, in full
taskops report range --last 7d       # a week, grouped by day
taskops report all                   # the whole project, from the first event
```

A **day** is a calendar day, not a rolling 24 hours, and it is 23 or 25 hours long on the days the
clocks change rather than a flat 86 400.

Whose midnight, though, is a decision a **shared** board has to make, and it is one setting:

```sh
taskops policy day_zone Europe/Madrid   # the project's day, on every machine
taskops policy day_zone                 # read it · `none` goes back to each machine's own
```

Unset, every machine uses its own zone — which is right while there is one machine and quietly
wrong as soon as there are two. Two developers three hours apart file the same events under
different dates, so they render one closed day into two different documents, and a dossier is a
committed *file*: the second one replaces the first with nothing to see in the diff. It has
happened, and the measurement is in `engine/calendar.py` — one day counted 8 commits at UTC-3 and
5 at UTC+2, the other three sitting in the next day's file.

The offset the window was cut at is written into the report's stamp (`tz=+0200`), so a copy cut at
one offset can never overwrite a copy cut at another: that is a `409` naming both, because they are
two windows sharing a name and neither is the newer version of the other.

A day report contains: every card closed with who closed it and how long it was held, each commit
with its files and diff size, every card opened, every card still waiting and what on, and the
**whole conversation** — comments, handoffs, messages between agents.

### A window says what it DID, not what is true now

Every card is filed into its section — `opened`, in flight, blocked, waiting — by the status it
held **when that window closed**, read back out of the event log. Never by the status it holds
today. That is what makes a dossier worth diffing against yesterday's copy: regenerate 2026-07-30
next year and you get the same four sections you got on the 31st.

It did not always work that way, and the failure is the reason this section exists. Filing on the
CURRENT status meant a card planned on Tuesday and finished on Thursday belonged to no Tuesday
section at all by Friday — not "in flight" (it is done now) and not in Tuesday's `closed` either
(it closed on Thursday). On the axion board 2026-07-30 fell from `5 opened` to `3` to `2` over
three regenerations: **the report got shorter every time it was rebuilt**, silently, and one line
of that day's planning was lost per card that closed.

The **glyph** beside a card is still its status today, in every section. Two facts side by side:
the section says what the window did, the glyph says where the card ended up. So a `✓` under
`## Sigue abierto` reads "was in flight that day, since finished", which is what a reader wants.

### The one thing no dossier can recover — windows before 0.5.17

`scheduler.unblock` is the only writer that moves a card between `backlog` and `ready`, and until
0.5.17 it moved them **without recording an event**. Those transitions are gone. Events are facts
about the past and taskops will not invent one to fill a gap, so for any window that closed before
0.5.17 a card sitting between those two states reconstructs as `backlog` — the status its `created`
event states — whatever it actually was on the day.

**What that costs is the glyph, not the section.** The `waiting` section holds `ready` and
`backlog` together, so the card is filed correctly either way; only the mark beside it can be wrong
for an old window. Every other status — `claimed`, `review`, `blocked`, `done`, `cancelled` — has
always been recorded by whoever moved it, so those sections are exact for windows of any age.

Stated here rather than left to be discovered because the failure this whole thread is about was a
report mixing reconstructed history with present state and saying nothing. A limit written down is
a different thing from a limit nobody mentions. `engine/_asof.py` carries the same boundary beside
the code, and `tests/engine/test_asof.py` pins it.

## 3 · The narration — `--digest`

```sh
taskops report day --digest          # yesterday, explained
taskops report all --digest          # the whole project as a document you read instead of git log
```

Claude reads the dossier and writes the part a projection cannot: **what was asked versus what was
delivered**, card by card, the decisions, the surprises, and what is still owed.

- It **streams into your terminal as it is written**, and into the UI over the same WebSocket.
- It uses your existing Claude Code login. **Never an API key** — `ANTHROPIC_API_KEY` and friends
  are stripped from the environment before the call, because an exported key silently beats the
  subscription you already pay for.
- It lands in `.taskops/reports/<label>.md`, committed like source.

**The facts are written before the model is called.** A narration that fails costs you nothing —
the dossier is already on disk. This ordering is the whole reason a failed narration is an
inconvenience rather than a lost day.

### The narration is the one irreplaceable half

A report file has two halves, and they have opposite properties:

| | can be regenerated? | goes stale? |
|---|---|---|
| the **dossier** — facts derived from the log | always, for free | yes, if the day kept happening |
| the **narration** — prose a model wrote or a person edited | **never** | no |

Everything about how reports are written and synced follows from that asymmetry. `write_report`
refuses to overwrite an existing file unless `--force`, and `--force` says out loud that the
narration is lost. When two machines have narrated the same day, the sync rule is: **newest stamp
wins, equal-but-different is always a `409` naming both**, and an unstamped file is never clobbered
by a stamped one. A hand-written narration can never be silently replaced by a generated one.

One thing the stamp cannot order, and it is checked before the stamp is: two copies whose windows
were cut at **different UTC offsets**. The higher `max_seq` there is not the fuller account, it is
the account of a different day — so that pair conflicts on sight and the message names `day_zone`,
which is the decision that ends it.

## 4 · `sweep` — the report that writes itself

You should almost never run `--digest` by hand. `sweep` narrates **every day that has ENDED, has
events, and carries no prose yet**:

```sh
taskops report sweep                 # narrate what is owed, then stop
taskops report sweep --push          # …and send the reports up
```

```
narrated 0 day(s) — every ended day is already written up
  skipped 2026-07-28 — it already carries a narration
```

This is a **barrier, not a clock**, and that is the entire design:

- **The trigger stops mattering.** 00:05, 9am when the laptop wakes, or by hand — all converge on
  the same state.
- **Running it twice costs nothing.** The second run makes zero model calls. The tests assert that
  by *counting calls*, not by diffing files: a version that re-narrated everything and wrote the
  same prose back would pass a diff and arrive on your invoice.
- **Today is never narrated.** A day is not finished until it has ended; a report written at 3pm
  would be missing the evening forever, because the next sweep sees a file that already has prose.
- **A day narrated on somebody else's machine counts as narrated.** Where the prose was written was
  never part of the question.
- **`--limit` (7) caps the run and says when it truncated.** A silent cap reads exactly like
  "everything is written up", which is the one thing it must never be mistaken for on a repository
  with a year of history.

Claude Code's own scheduled-task documentation asks for exactly this shape:

> *A task scheduled for 9am might run at 11pm if your computer was asleep all day. If timing
> matters, add guardrails to the prompt itself.*

The sweep **is** that guardrail.

## 5 · Running it unattended

Two triggers, neither of them touching your operating system.

**It already fires on its own.** The plugin's `SessionStart` hook launches a sweep detached — the
hook returns immediately, is stamped to at most one sweep per project per day, and is silent on any
failure, because a broken sweep may never stop a session from starting. `TASKOPS_NO_SWEEP=1` turns
it off. Open Claude Code at 9am and yesterday writes itself.

**For a real schedule**, use Claude Code's own — not cron, not launchd:

```sh
taskops schedule install
```

```
wrote /Users/you/.claude/scheduled-tasks/taskops-sweep/SKILL.md

That file is the PROMPT. Claude Code keeps the schedule itself, so nothing runs yet — say this to Claude:

  create a daily scheduled task at 00:05 named "taskops-sweep" that runs /taskops:sweep in /path/to/repo
```

The command is honest about the half it cannot do. The prompt is ours; **the schedule belongs to
Claude Code**, which is also what gives it the property that matters: on wake or app start it looks
back seven days and runs **exactly one** catch-up for the most recently missed time. A daily task
that missed six days runs once.

Of the three scheduling mechanisms, only that one is durable:

| | survives closing Claude | machine off | catch-up |
|---|---|---|---|
| `/loop`, `CronCreate` | ✗ session-scoped, 7-day expiry | ✗ | ✗ |
| **Desktop scheduled tasks** | ✓ | needs the machine awake | **✓ one catch-up** |
| Routines (cloud) | ✓ | ✓ | n/a |

## 6 · Reading them

```sh
taskops report day --date 2026-07-28    # in the terminal, rendered
taskops ui                              # the Reports tab: rendered, with a Generate button
                                        #   you can watch writing, streamed live
```

The index knows, per day, whether a report `exists`, whether it is `stale`, how many events landed
after it was written, and whether it `has_narration` — which is exactly what the sweep uses to
decide what it owes.
