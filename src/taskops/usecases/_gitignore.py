"""The block `taskops init` writes into `.gitignore`, and how it grows without being rewritten.

Its own module because it stopped being a detail of init the moment it started guarding a
SECRET. The rule this file encodes is: everything under `.taskops/` is ignored except the
event log — which is the whole replication story — and the list is written out path by path
rather than as `.taskops/*` plus exceptions, so that a person reading it can see what each
line is for.

That explicitness has a cost the token found first: a new file under `.taskops/` is TRACKED
by default. `remote.json` holds a bearer, and a token in git history is still a token after
somebody deletes the file. Hence `_UPGRADES` — a project initialised by an older taskops must
gain that line the next time init runs, or upgrading in place is one `git add .` from a leak.
"""

from __future__ import annotations

from pathlib import Path

from ..storage import PROJECT_DIR

__all__ = ["ignore"]

MARKER = "# taskops"

REPORTS_NOTE = f"# {PROJECT_DIR}/reports/ is COMMITTED — a written dossier is not derived state"
"""A COMMENT, not a rule, and that is the point.

`reports/` is tracked, so the correct entry here is no entry at all — but "no entry" is
indistinguishable from an oversight, and the next person tidying this block would add
`{PROJECT_DIR}/*` and untrack every report in the project. The line says why the hole exists.
"""

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
fight over its contents forever. It also removed a real merge conflict — two clones that each
ran `taskops init` could not pull from one another, because the incoming commit carried files
both sides had independently created untracked.
"""

AGENTS_RULE = ".claude/agents/taskops-*.md"
"""Ours are GENERATED — rewritten by every init to match the installed version, exactly like
GUIDE.md and for the same reason: a stale copy describes tools that no longer exist, and two
developers on different versions would fight over the file forever. Only `taskops-*` is
ignored; a project's own agents are its code and commit normally."""

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
{REPORTS_NOTE}
{PROJECT_DIR}/*.stamp
{PROJECT_DIR}/stop-blocks.json
{SETTINGS_RULE}
{AGENTS_RULE}
"""

_UPGRADES = (REPORTS_NOTE, REMOTE_RULE, f"{PROJECT_DIR}/*.stamp",
             f"{PROJECT_DIR}/stop-blocks.json", SETTINGS_RULE, AGENTS_RULE)
"""Lines added to the block AFTER projects existed with it. Order is the order they land in."""


def ignore(root: Path) -> None:
    """Write the block, once. Matched on the MARKER rather than on the paths.

    A developer may reformat those lines, and appending a duplicate block on every init is
    how a `.gitignore` becomes forty lines of the same thing.
    """
    path = root / ".gitignore"
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if MARKER in current:
        _upgrade(path, current)
        return
    separator = "" if current.endswith("\n") or not current else "\n"
    path.write_text(current + separator + BLOCK, encoding="utf-8")


def _upgrade(path: Path, current: str) -> None:
    """Append whatever this taskops adds to a block an older one wrote. Idempotent.

    Appending rather than rewriting the block: the developer may have edited those lines, and
    a tool that replaces a file it does not own loses whatever they added.
    """
    missing = [line for line in _UPGRADES if line not in current]
    if not missing:
        return
    separator = "" if current.endswith("\n") else "\n"
    path.write_text(current + separator + "\n".join(missing) + "\n", encoding="utf-8")
