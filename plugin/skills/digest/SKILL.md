---
name: digest
description: Write the day's report — generate the deterministic dossier for a date, then narrate it for a human and commit it. Use when the user asks for the daily report, a write-up of the day, "cerrá el día", or a digest of what happened on a date.
argument-hint: "[date: today, yesterday, YYYY-MM-DD]"
---

# Digest — the day, written down

The dossier is GENERATED and the narration is yours. Keep the line clean: never edit a fact,
never add one the file does not carry.

## 1. Make sure the file exists

```sh
taskops report day --date $1 --write     # $1 defaults to today
```

- It prints the path it wrote, under `.taskops/reports/YYYY-MM-DD.md`.
- If it REFUSES because the file already exists, that is the expected answer, not an error:
  read the file. Somebody may already have narrated it. Only pass `--force` if the user asked
  for a regeneration and you have told them the existing narration is lost.

## 2. Read the file

Read the whole `.md`. Everything you are allowed to say comes from it: what closed and who
closed it, how long each card was held, the commits with their diff sizes, what is still in
flight or blocked, the conversation, the roll-up per actor.

## 3. Replace the `## Narración` section

Edit the file in place: keep the fingerprint comment on line 1 and the dossier untouched,
and replace the body under `## Narración` (the `_pendiente — …_` placeholder) with your
write-up. Six to twelve lines, Spanish, prose with bullets where a list is genuinely a list.

- **Lead with what needs a human.** Blocked cards, a claim that has gone quiet, a decision
  nobody made. That is the only part of the report somebody can act on tonight.
- **Then what actually moved**, grouped by outcome rather than by actor — unless one actor's
  work IS the story.
- **Name the decisions and the risks** the conversation shows: a spec that changed mid-card,
  a card closed with a caveat in its last comment, work that landed without tests.
- Numbers only where they change a decision. "3 de 8 cerradas" is useful; "17 eventos" is not.
- **Invent nothing.** If the dossier does not say why a card is blocked, say it is blocked and
  that the reason is not in the log. A gap named is information; a gap filled in is a lie with
  a timestamp on it.
- No flattery and no editorialising about pace. A generated report that congratulates anybody
  is worth less than no report.

## 4. Commit it

```sh
git add .taskops/reports/$1.md && git commit -m "taskops: report YYYY-MM-DD"
```

Reports are committed on purpose — that is what makes yesterday's report still true tomorrow.

## If the day already moved on

`GET /api/report?date=…` (and the file's own fingerprint) report `stale` when events landed
after the file was generated. A stale report is not wrong, it is SHORT: say so, or regenerate
with `--force` if nothing was narrated yet.
