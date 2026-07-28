"""Installing the git hooks, without destroying the ones already there.

Three decisions carry this file.

**The command is the WIRING transport, not the developer's CLI.** `taskops` is what a person
types; `python -m taskops.transports.hooks` is what git runs. They were the same binary until
the separation the project declares turned out to be cosmetic, and a shared door is a door
whose surface is decided by the wrong audience.

**The interpreter is absolute, not `taskops` on PATH.** Git hooks run with whatever
environment git had, and that is routinely not the shell's: a virtualenv that is not active,
a GUI client with a minimal PATH, a `git commit` from an editor. A bare `taskops` there
resolves to nothing and the hook does nothing — silently, because every line ends in
`|| true`. Embedding `sys.executable -m taskops...` binds the hook to the interpreter that
installed it, which is the one that definitely has taskops in it. (Found by the end-to-end
test, where `git commit` could not see the venv that pytest was running from.)

**Existing hooks are CHAINED, never overwritten.** A repository's `post-commit` may already
run something somebody depends on, so an existing script is kept and our line is appended
under a marker — which is also how a re-install finds the line it wrote last time and
REWRITES it. That refresh is what repairs a repository initialised before the wiring moved
out of the CLI: its hook names a command that no longer exists, and `|| true` means it says
nothing about it. `taskops init` again is the whole repair.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

__all__ = ["install_hooks", "HOOKS", "BLOCKING", "MARKER", "runner"]

MARKER = "# >>> taskops >>>"

HOOKS: dict[str, str] = {
    "post-commit": "ingest commit HEAD",
    "post-checkout": "ingest branch",
    "post-merge": "sync",
    "pre-commit": "precommit",
    "prepare-commit-msg": 'precommit --message-file "$1"',
}
"""Why these, and what changed.

- **post-commit** catches every commit, including the ones the PreToolUse guard never saw —
  a human's terminal commit, a `--no-verify`, a rebase landing on a task branch.
- **post-checkout** records the branch on the lease, so the board can show where an agent is
  working without asking it to report that separately.
- **post-merge** imports what a `git pull` just brought in. That is the moment another
  developer's events become visible, and the only automatic sync point that matters.
- **pre-commit** refuses an AGENT's commit that no lease covers, and **prepare-commit-msg**
  writes the trailer onto the ones it allows (the only hook git hands the message file to).

`pre-commit` was deliberately absent here, and the reason it was absent is still TRUE: "a
refusal reaches a human as a failed command with no context, and a developer cherry-picking
onto main is doing something legitimate". That reasoning was about HUMANS. What it never
covered was the agent committing through a script, a rebase, or a harness that is not Claude
Code — the PreToolUse guard sees a Bash tool call and nothing else, so every other path was
unguarded. So the hook is ASYMMETRIC: an agent is refused, a human is warned and passes.
That asymmetry lives in `transports/hooks/commit.py`; the judgement itself is still the one
use case, `usecases.guard.check_commit`, reached through a second door.
"""

BLOCKING = frozenset({"pre-commit", "prepare-commit-msg"})
"""The hooks whose exit code MEANS something, so their line may not end in `|| true`.

Every other line is silenced and forced to succeed, because a recorder that broke somebody's
commit would be a bug with no upside. These two are the opposite: the exit code IS the
product, and stderr is where the fix is printed, so neither may be swallowed.
"""


def runner() -> str:
    """The command prefix a hook uses: this interpreter, running the wiring transport.

    Renaming this is the change that breaks in TOTAL silence — every hook line ends in
    `|| true`, so a module that no longer exists just stops binding commits to cards and
    nothing anywhere says so. `tests/e2e/test_hook_wiring.py` commits in a real repository and
    asserts the binding happened; that test is the only thing standing between a rename and a
    board that quietly loses its commits.
    """
    return f"{sys.executable} -m taskops.transports.hooks"


def install_hooks(root: Path) -> tuple[list[str], list[str]]:
    """Install into `.git/hooks`. Returns (installed, skipped-with-reason).

    Skipping rather than raising: this runs inside `init`, and a directory that is not a git
    repository yet is an ordinary state — `git init` then `taskops init` again is the fix, and
    the report says so.
    """
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return [], [f"{root}/.git/hooks does not exist — not a git repository yet"]
    installed: list[str] = []
    skipped: list[str] = []
    for name, verb in HOOKS.items():
        problem = _install_one(hooks_dir / name, _line(name, verb))
        (skipped if problem else installed).append(f"{name}: {problem}" if problem else name)
    return installed, skipped


def _line(name: str, verb: str) -> str:
    """The shell line a hook runs. Two shapes, and the difference is the exit code.

    `|| exit $?` rather than a bare call so the intent is legible in the file a developer
    opens when they wonder what stopped their commit — and so an appended line cannot be read
    as decoration next to the `|| true` ones above it.
    """
    if name in BLOCKING:
        return f"{runner()} {verb} || exit $?"
    return f"{runner()} {verb} >/dev/null 2>&1 || true"


def _install_one(path: Path, command: str) -> str:
    """"" on success, else the reason. Appends under the marker if a hook already exists."""
    try:
        if path.is_file() and MARKER in path.read_text(encoding="utf-8"):
            return "" if _refresh(path, command) else "already installed"
        if path.is_file():
            _append(path, command)
        else:
            path.write_text(f"#!/bin/sh\n{MARKER}\n{command}\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    except OSError as err:
        return str(err)
    return ""


def _refresh(path: Path, command: str) -> bool:
    """Rewrite OUR line when it no longer says what it should. True if anything changed.

    Everything above the marker is the repository's own script and is kept byte for byte;
    everything below it is ours, and ours is the only part that is allowed to move. Without
    this, `init` on an already-initialised repository reports "already installed" over a hook
    line pointing at a module that was renamed — the silent failure this file warns about,
    reached through the command that is supposed to be the repair.
    """
    current = path.read_text(encoding="utf-8")
    head, _, ours = current.partition(MARKER)
    if ours.strip() == command:
        return False
    path.write_text(f"{head}{MARKER}\n{command}\n", encoding="utf-8")
    return True


def _append(path: Path, command: str) -> None:
    """Add our line to an existing hook, keeping what was there.

    Appended rather than prepended: the existing script is what the repository's owner put
    there, and it gets to decide the exit code. Our line cannot fail anyway — it ends in
    `|| true`.
    """
    current = path.read_text(encoding="utf-8").rstrip("\n")
    path.write_text(f"{current}\n\n{MARKER}\n{command}\n", encoding="utf-8")
