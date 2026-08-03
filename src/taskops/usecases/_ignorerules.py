"""WHAT `taskops init` ignores, and why each line is there. The mechanism is `_gitignore`.

Split when the two together stopped fitting one screen, and the split is the one the budget was
pointing at: this is a LIST with a rationale per entry, and that one is an append-and-upgrade
algorithm with a subtle matcher in it. They change for entirely different reasons — a new file
under `.taskops/` adds a line here and touches nothing there.

The rule the list encodes: everything under `.taskops/` is ignored except the event log — which
is the whole replication story — and it is written out path by path rather than as `.taskops/*`
plus exceptions, so a person reading their own `.gitignore` can see what each line is for.

That explicitness cuts both ways, and the token found the sharp edge first: a new file under
`.taskops/` is TRACKED by default. `remote.json` holds a bearer, and a token in git history is
still a token after the file is deleted — hence `UPGRADES` next door, so a project initialised
by an older taskops gains the rule on its next init rather than being one `git add .` from a
leak. `board.json` is the same mechanism used deliberately: tracked, because it carries no
secret.
"""

from __future__ import annotations

from ..storage import PROJECT_DIR

__all__ = ["MARKER", "BLOCK", "ANNOTATES", "UPGRADES"]

MARKER = "# taskops"

BOARD_NOTE = f"# {PROJECT_DIR}/board.json is COMMITTED — the board's ADDRESS, and no secret"
"""One line from `remote.json`, which is ignored precisely BECAUSE it holds a bearer — so this
note says which of the two is which. Untracking it breaks argument-less `taskops join`."""

REPORTS_NOTE = f"# {PROJECT_DIR}/reports/ is COMMITTED — a written dossier is not derived state"
"""A COMMENT, not a rule, and that is the point. `reports/` is tracked, so the correct entry
is no entry at all — but "no entry" is indistinguishable from an oversight, and the next person
tidying this block would add `{PROJECT_DIR}/*` and untrack every report."""

REMOTE_RULE = f"{PROJECT_DIR}/remote.json"
"""The remote's URL and its BEARER TOKEN. The one line here that guards a secret.

Everything else is ignored because committing it would be noise; this one because committing
it would be a leak that outlives the commit. The file is also written 0600
(`usecases/remote.py`) — belt and braces, on purpose, because the two failures are different:
the mode stops another account on this machine, the ignore stops the whole internet.
"""

GUIDE_NOTE = f"{PROJECT_DIR}/GUIDE.md"
"""Ignored rather than committed, which looks wrong at first.

It is GENERATED: it ships inside the package and init rewrites it every run, so it always
describes the version of taskops actually installed. Tracking a file that a command overwrites
would leave `git status` dirty after every init, and two developers on different versions would
fight over its contents forever. It also removed a real merge conflict: two clones that each ran
`taskops init` could not pull from one another, because the incoming commit carried files both
sides had independently created untracked."""

AGENTS_RULE = ".claude/agents/taskops-*.md"
"""Ours are GENERATED — rewritten by every init to match the installed version, exactly like
GUIDE.md and for the same reason: a stale copy describes tools that no longer exist, and two
developers on different versions would fight over the file forever. Only `taskops-*` is
ignored; a project's own agents are its code and commit normally."""

UI_NOTE = f"{PROJECT_DIR}/ui.json"
"""A pid and a port: where THIS machine's local board listens. Inherited, it would point a
teammate's browser at whatever is on that port on theirs."""

SETTINGS_RULE = ".claude/settings.local.json"
"""Written by `init` and machine-specific: it names the absolute path to `taskops-hook` on
THIS machine. Committing it would hand a teammate five hooks pointing into a directory they do
not have, which fails silently — the worst shape a failure can take."""

BLOCK = f"""
{MARKER} — commit events.jsonl and NOTHING else under {PROJECT_DIR}/
{PROJECT_DIR}/db.sqlite
{PROJECT_DIR}/db.sqlite-wal
{PROJECT_DIR}/db.sqlite-shm
{GUIDE_NOTE}
{PROJECT_DIR}/workers/
{PROJECT_DIR}/trees/
{REMOTE_RULE}
{BOARD_NOTE}
{REPORTS_NOTE}
{PROJECT_DIR}/*.stamp
{PROJECT_DIR}/stop-blocks.json
{UI_NOTE}
{SETTINGS_RULE}
{AGENTS_RULE}
"""

ANNOTATES = {REPORTS_NOTE: f"{PROJECT_DIR}/reports/",
              BOARD_NOTE: f"{PROJECT_DIR}/board.json"}
"""What a COMMENT in the block is about, so it can be skipped with its subject.

The reports note explains why `reports/` has no rule. In a project that ignores `.taskops/`
wholesale it is not merely redundant, it is FALSE — reports are ignored there like everything
else — and a comment that contradicts the file it lives in is worse than no comment.
"""

UPGRADES = (REPORTS_NOTE, BOARD_NOTE, REMOTE_RULE, f"{PROJECT_DIR}/*.stamp",
             f"{PROJECT_DIR}/stop-blocks.json", UI_NOTE, SETTINGS_RULE, AGENTS_RULE)
"""Lines added to the block AFTER projects existed with it. Order is the order they land in."""
