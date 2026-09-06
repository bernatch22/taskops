"""One file of a worktree, read for the screen: text or "binary", capped, and
the lines that moved since the branch base — as gutter marks, or as a patch.

The WORKING COPY is the subject, not a commit: the Editor (ARCHITECTURE.md §22)
shows what a worker's directory holds right now, saved and unsaved-to-git
alike, which is exactly what `patch.show` (a committed file at a sha) cannot
say. So the bytes come off the disk, and "what changed" is `git diff <base> --
<path>` run INSIDE the tree, which git reads as "this commit against the
working copy as the index sees it". An untracked file is not in the index and
that diff is empty for it; `--no-index` against `/dev/null` is what git itself
offers for "a file that is all addition", and it is the one exception spelled
out here rather than a synthetic patch assembled by hand.

The BASE is a merge-base, never the ref itself, for the reason `diff.py`
argues at length: a card's chapter has moved on since the card branched, and
diffing against its tip would draw every sibling's work as this file's
change. No ref given means HEAD — "what did this directory change since its
last commit" — which is the right question for the checkout itself.

The file cap is `patch.CAP`, the one number every capped answer in this
package states, and a cut file SAYS it was cut. Binary is decided on the
first `PROBE` bytes: a NUL, or bytes that are not UTF-8, and the answer is
"binary, N bytes" with no text at all — never a screen of replacement glyphs.
"""

from __future__ import annotations

import re
from typing import NamedTuple
from pathlib import Path

from . import run, diff, patch

CAP = patch.CAP
PROBE = 8192

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
"""A hunk header: only the NEW side's start is read — every mark is a fact
about the file on screen — and the counts come from the body, because with
zero context git folds a changed line and the lines added right after it into
ONE hunk, and the header's two counts cannot say which is which."""

ADDED, MODIFIED, DELETED = "added", "modified", "deleted"


class Read(NamedTuple):
    text: str
    binary: bool
    truncated: bool
    size: int
    mtime: float


class Base(NamedTuple):
    ref: str  # what was asked for: a branch name, or HEAD
    sha: str  # what was diffed against: the merge-base, 40-hex


class Mark(NamedTuple):
    start: int  # 1-based, inclusive, on the file as it stands
    end: int
    kind: str  # ADDED | MODIFIED | DELETED (something was removed after `start`)


def read(path: Path, cap: int = CAP) -> Read:
    """The bytes on disk, decided text or binary and capped. `path` has passed
    `inhabited.inside` — this function trusts it and resolves nothing."""
    found = path.stat()
    with path.open("rb") as handle:
        head = handle.read(cap + 1)
    if _binary(head[:PROBE]):
        return Read("", True, False, found.st_size, found.st_mtime)
    cut = len(head) > cap
    text = head[:cap].decode("utf-8", "ignore") if cut else head.decode("utf-8", "replace")
    return Read(text, False, cut, found.st_size, found.st_mtime)


def base_of(tree: Path, ref: str) -> Base | None:
    """The commit the working copy is compared against, or None when `ref`
    names nothing this tree can see. Both names pass `diff.resolve`, the
    package's one door from a string to a sha."""
    head = diff.resolve(tree, "HEAD")
    if head is None:
        return None
    if not ref:
        return Base("HEAD", head)
    left = diff.resolve(tree, ref)
    if left is None:
        return None
    got = run.git("merge-base", left, head, cwd=tree)
    sha = got.out.strip()
    return Base(ref, sha if got.ok and re.fullmatch(r"[0-9a-f]{40}", sha) else left)


def tracked(tree: Path, rel: str) -> bool:
    """Is this path in the index? `--error-unmatch` makes git say so by exit
    code, which is the whole answer."""
    return run.git("ls-files", "--error-unmatch", "--", rel, cwd=tree).ok


def marks(tree: Path, sha: str, rel: str, *, is_tracked: bool, lines: int) -> list[Mark]:
    """Which lines of the file ON SCREEN differ from `sha`, from a zero-context
    diff, paired POSITIONALLY inside each hunk the way `ui/src/components/card/
    split.ts` pairs a patch: the first `+` lines opposite `-` lines are
    modifications, the `+` lines past them are additions, and a hunk with no
    `+` at all is a deletion after its anchor line."""
    if not is_tracked:
        return [Mark(1, lines, ADDED)] if lines else []
    found: list[Mark] = []
    opened, start, minus, plus = False, 0, 0, 0
    for line in _diff(tree, sha, rel, context=0, is_tracked=True).splitlines():
        hunk = HUNK.match(line)
        if hunk is not None:
            if opened:
                found.extend(_marks_of(start, minus, plus))
            opened, start, minus, plus = True, int(hunk.group(1)), 0, 0
        elif opened and line.startswith("-"):  # before the first `@@` the file
            minus += 1  # headers `---`/`+++` are not lines of anybody's file
        elif opened and line.startswith("+"):
            plus += 1
    if opened:
        found.extend(_marks_of(start, minus, plus))
    return found


def _marks_of(start: int, minus: int, plus: int) -> list[Mark]:
    """One hunk's marks, positionally paired."""
    if plus == 0:
        anchor = max(start, 1)  # `+0,0`: the deletion sits at the very top
        return [Mark(anchor, anchor, DELETED)]
    paired = min(minus, plus)
    found = [Mark(start, start + paired - 1, MODIFIED)] if paired else []
    if plus > paired:
        found.append(Mark(start + paired, start + plus - 1, ADDED))
    return found


def patch_of(tree: Path, sha: str, rel: str, *, is_tracked: bool, cap: int = CAP) -> tuple[str, bool]:
    """(text, truncated) — the same unified patch the Worktrees page draws,
    for one file of the working copy against `sha`."""
    return patch.capped(_diff(tree, sha, rel, context=3, is_tracked=is_tracked), cap)


def _diff(tree: Path, sha: str, rel: str, *, context: int, is_tracked: bool) -> str:
    """`git diff` exits 1 when the two sides differ — that is an answer, not a
    failure, so both codes are read and anything else is an empty patch."""
    if is_tracked:
        raw = run.git("diff", "--no-color", f"-U{context}", sha, "--", rel, cwd=tree)
    else:
        raw = run.git("diff", "--no-color", f"-U{context}", "--no-index", "--", "/dev/null", rel, cwd=tree)
    return raw.out if raw.code in (0, 1) else ""


def _binary(probe: bytes) -> bool:
    """A NUL says binary outright. Bytes that are not UTF-8 say so too — unless
    the failure sits in the last three bytes, where a codepoint the probe cut in
    half looks exactly like one."""
    if b"\0" in probe:
        return True
    try:
        probe.decode("utf-8")
    except UnicodeDecodeError as err:
        return err.start < len(probe) - 3
    return False
