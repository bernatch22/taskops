"""Writing the ignore block into `.gitignore`, and growing it without rewriting it.

Its own module because it stopped being a detail of init the moment it started guarding a
SECRET, and separate from `_ignorerules` — which is WHAT is ignored — because this is HOW: an
append-only upgrade with a matcher in it that took two goes to get right.
"""

from __future__ import annotations

from pathlib import Path

from ._ignorerules import ANNOTATES, BLOCK, MARKER, UPGRADES

__all__ = ["ignore"]


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

    "Missing" is asked of GIT, not of the text. The literal test was wrong in the one way that
    matters: a project ignoring `.taskops/` wholesale does not contain the string
    `.taskops/remote.json`, so every `init` and `join` appended four rules that changed nothing
    and left the clone permanently dirty — and a modified tracked file is what `land` and
    `git switch` refuse on, so nothing could ever reach the trunk.
    """
    missing = [line for line in UPGRADES
               if line not in current and not _already_ignored(path.parent, line)]
    if not missing:
        return
    separator = "" if current.endswith("\n") else "\n"
    path.write_text(current + separator + "\n".join(missing) + "\n", encoding="utf-8")


def _already_ignored(root: Path, line: str) -> bool:
    """Does a rule THAT TRAVELS WITH THE REPOSITORY already ignore what this line names?

    `check-ignore` is the only correct matcher — it knows wildcards, directory rules, negations
    and every `.gitignore` above this one, and reimplementing it here would be a second matcher
    able to disagree with the one that decides what actually gets committed.

    But its plain answer is the wrong question, and a test caught me shipping it: a personal
    global ignore already covered `.taskops/remote.json` here, so taskops skipped writing the
    rule guarding a bearer — and the repository would have reached a teammate with no such file
    and nothing protecting the secret. Hence `-v`, and only a `.gitignore` inside the repository
    counts: a global ignore is somebody's preference, not a property of the project.

    A comment is judged by its SUBJECT: the reports note exists to explain a missing rule, so
    where that path is already ignored the note would contradict the file it sits in.
    """
    if line.startswith("#"):
        subject = ANNOTATES.get(line)
        return bool(subject) and _already_ignored(root, subject)
    import subprocess

    try:
        done = subprocess.run(["git", "check-ignore", "-v", line.rstrip("/")],
                              cwd=root, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    source = done.stdout.split(":", 1)[0] if done.returncode == 0 else ""
    return source.endswith(".gitignore") and not source.startswith(("/", "~"))
