"""Finding and reading a Claude Code session transcript. Every line here was verified on disk.

**`$CLAUDE_CONFIG_DIR` is honoured, and that is not a nicety.** On the machine this was written on it
is `~/.claude-jp`, so a hardcoded `~/.claude` found a different installation's projects and reported
that the workers had left no transcript at all. They had; it was in the other home.

**A transcript is located by DIRECTORY, not by searching for a session id.** Claude Code names the
directory after the working directory with every separator turned into a dash, so a dispatched worker
running in `<repo>/.taskops/trees/tk-856f45` gets a directory of its own — one per CARD. That makes the
lookup a path computation rather than a scan, and it works retroactively on transcripts written before
taskops knew it would ever read them.

**`gitBranch` verifies what the path suggests.** Every entry carries it, so an entry can be confirmed
to belong to the card's branch rather than assumed. That is what makes reading the main project's
directory safe too, where many cards' sessions are mixed together.

The format is NOT documented as stable — the Agent SDK offers `get_session_messages()` for this, which
is a supported contract — so everything here degrades to "nothing found" rather than raising, and an
entry shape this version does not recognise is passed through as `other` instead of dropped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator, cast

__all__ = ["home", "slug_for", "directories_for", "read_entries", "ENV_HOME"]

ENV_HOME = "CLAUDE_CONFIG_DIR"

_MAX_TEXT = 4000
"""Characters kept per entry. A single assistant turn can run to tens of thousands, and a viewer
needs the shape of the conversation more than the whole of one message."""


def home() -> Path:
    """Claude Code's config directory. `$CLAUDE_CONFIG_DIR` wins, else `~/.claude`."""
    forced = os.environ.get(ENV_HOME, "").strip()
    return Path(forced).expanduser() if forced else Path.home() / ".claude"


def slug_for(path: Path) -> str:
    """A working directory -> the transcript directory name Claude Code uses.

    Every separator becomes a dash, including the leading one, so `/Users/b/x` becomes `-Users-b-x`
    and a worktree at `/Users/b/x/.taskops/trees/tk-1` becomes `-Users-b-x--taskops-trees-tk-1` — the
    doubled dash is the dot of `.taskops`, which is where the encoding stops being guessable and starts
    being something to verify. It was.
    """
    return str(path.resolve()).replace("/", "-").replace(".", "-")


def directories_for(root: Path, tree: Path) -> list[Path]:
    """Where this card's transcripts could be: its worktree's directory, then the project's.

    The worktree's comes FIRST and is per-card, so it needs no filtering. The project's is shared by
    every session anybody ran in the repository, which is why callers filter it by branch.
    """
    base = home() / "projects"
    found = [base / slug_for(tree), base / slug_for(root)]
    return [path for path in found if path.is_dir()]


def read_entries(directory: Path, *, branch: str = "",
                 sessions: tuple[str, ...] = ()) -> Iterator[dict[str, Any]]:
    """Every raw entry in every transcript in `directory`, oldest file first.

    Two filters, and the second is what rescues the ordinary case. `branch` matches the entry's own
    `gitBranch`, which is how the shared project directory can be read without mixing in other cards'
    conversations — but it only works for an agent that made a branch. A person who claimed a card and
    worked on `main` produces entries the branch filter throws away, so `sessions` names transcripts
    directly: a file whose stem is a recorded session id belongs to the card by record, and its entries
    are taken whatever branch they were on.

    Both empty means take everything, which is correct for a per-card worktree directory.
    """
    for path in sorted(directory.glob("*.jsonl"), key=_mtime):
        named = path.stem in sessions
        for entry in _lines(path):
            if branch and not named and entry.get("gitBranch") not in (branch, None):
                continue
            yield entry


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _lines(path: Path) -> Iterator[dict[str, Any]]:
    """Parsed lines, skipping anything unreadable.

    A malformed line is skipped rather than fatal, for the same reason it is in the event log: this
    file is written by whatever Claude Code version was installed, and one bad line must not make a
    conversation unreadable.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parsed = _parse(line)
                if parsed is not None:
                    yield parsed
    except OSError:
        return


def _parse(line: str) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        found: Any = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, Any]", found) if isinstance(found, dict) else None


def clip(text: str) -> str:
    """One entry's text, bounded. Says it was cut rather than trailing off."""
    flat = text.strip()
    if len(flat) <= _MAX_TEXT:
        return flat
    return flat[:_MAX_TEXT] + f"\n… (+{len(flat) - _MAX_TEXT} more characters)"
