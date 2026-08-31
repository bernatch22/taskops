"""The ONE way this package runs a command — git, and `ssh-keygen` beside it.

`(code, out, err)` — always all three, and **stderr is never discarded**. In v1
one of four different subprocess wrappers returned `None` on any failure, so
"refusing to update checked out branch" was reported as "somebody landed while
this ran", in an infinite retry loop. Whatever git says, the caller gets.

This is also the only module in the package allowed to import `subprocess`,
and `tests/test_architecture.py` enforces it. That rule is why `tool()` exists:
the ssh login (`gitwork/sig.py`) shells out to OpenSSH's own `ssh-keygen -Y
sign/verify`, and a second wrapper next to it is exactly the shape that cost v1
its swallowed stderr. One runner, one place that knows a process can be absent.
"""

from __future__ import annotations

import os
import subprocess
from typing import IO, Callable, NamedTuple
from pathlib import Path
from threading import Thread

from .._errors import Refused, TaskopsError

TIMEOUT = 120.0
CHUNK = 64 * 1024


class Result(NamedTuple):
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def tool(
    name: str,
    *args: str,
    stdin: str = "",
    cwd: Path | None = None,
    timeout: float = TIMEOUT,
    missing: str = "",
) -> Result:
    """Run a program and come back with everything it said. Never raises on exit
    code — an absent binary DOES raise, because that is a machine to fix and not
    an answer to interpret, and `missing=` is the sentence that names the fix."""
    try:
        done = subprocess.run(  # noqa: S603 — arguments are ours, never a shell string
            [name, *args],
            cwd=str(cwd) if cwd else None,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as err:
        raise TaskopsError(missing or f"{name} is not on PATH") from err
    except subprocess.TimeoutExpired as err:
        raise TaskopsError(f"{name} {' '.join(args)} took longer than {timeout}s") from err
    return Result(done.returncode, done.stdout.strip(), done.stderr.strip())


def git(*args: str, cwd: Path | None = None, timeout: float = TIMEOUT) -> Result:
    """Run git and come back with everything it said. Never raises on exit code."""
    return tool(
        "git",
        *args,
        cwd=cwd,
        timeout=timeout,
        missing="git is not on PATH — taskops needs it for worktrees",
    )


def must(*args: str, cwd: Path | None = None, why: str = "") -> str:
    """Run git, or refuse with git's own words in the message."""
    result = git(*args, cwd=cwd)
    if not result.ok:
        detail = result.err or result.out or f"exit {result.code}"
        head = why or f"git {' '.join(args)} failed"
        raise Refused(f"{head}\n  git said: {detail}")
    return result.out


def stream(
    args: list[str],
    stdin: bytes,
    sink: Callable[[bytes], None],
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run git with BYTE pipes: feed `stdin` whole, hand stdout to `sink` chunk
    by chunk, come back with `(code, stderr)` — stderr still never discarded.

    This lives HERE and not beside the socket that wants it, because the ban on
    `subprocess` outside this module is about who may start a process, not about
    what shape its pipes are. The smart-HTTP door (`http/gitpack.py`) serves a
    pack `git upload-pack` is still producing — buffering it whole would put a
    clone-sized allocation behind every fetch — so the ONE runner grows a
    streaming mode instead of the door growing a second runner, which is exactly
    the v1 shape (four wrappers, one swallowed stderr) the module docstring
    exists to prevent. `tool()` stays the answer for everything that fits in a
    string; nothing outside an HTTP response body should need this.

    `env` is ADDED to the inherited environment (git needs PATH and HOME); the
    door passes the client's `Git-Protocol` header through as `GIT_PROTOCOL`,
    which is how protocol v2 survives stateless-rpc. stdin is written from its
    own thread so a process that talks before it finishes reading cannot
    deadlock the pipe pair; stderr is drained the same way. The wait is bounded
    by TIMEOUT once stdout closes — the transfer itself is not, deliberately:
    its pace is the network peer's, and the cap on what a peer may SEND is the
    door's (`gitpack.CAP`)."""
    try:
        proc = subprocess.Popen(  # noqa: S603 — arguments are ours, never a shell string
            ["git", *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **env} if env else None,
        )
    except FileNotFoundError as err:
        raise TaskopsError("git is not on PATH — taskops needs it for worktrees") from err
    caught: list[bytes] = []
    feeders = [Thread(target=_feed, args=(proc.stdin, stdin), daemon=True)]
    feeders.append(Thread(target=lambda: caught.append(_drain(proc.stderr)), daemon=True))
    for thread in feeders:
        thread.start()
    if proc.stdout is not None:
        while chunk := proc.stdout.read(CHUNK):
            sink(chunk)
        proc.stdout.close()
    for thread in feeders:
        thread.join(TIMEOUT)
    try:
        code = proc.wait(TIMEOUT)
    except subprocess.TimeoutExpired as err:
        proc.kill()
        raise TaskopsError(f"git {' '.join(args)} took longer than {TIMEOUT}s") from err
    return code, b"".join(caught).decode(errors="replace").strip()


def _feed(pipe: IO[bytes] | None, data: bytes) -> None:
    """Write and close, tolerating a process that stopped reading — git closes
    stdin early on a refused push, and that is its answer, not a fault here."""
    if pipe is None:
        return
    try:
        if data:
            pipe.write(data)
    except (BrokenPipeError, OSError):
        pass
    finally:
        pipe.close()


def _drain(pipe: IO[bytes] | None) -> bytes:
    if pipe is None:
        return b""
    try:
        return pipe.read()
    finally:
        pipe.close()


def is_repo(path: Path) -> bool:
    return git("rev-parse", "--git-dir", cwd=path).ok


def branch_at(path: Path) -> str:
    """The branch checked out in a worktree. Empty on a detached HEAD."""
    result = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=path)
    return result.out if result.ok else ""


def has_branch(repo: Path, name: str) -> bool:
    return git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}", cwd=repo).ok


def dirty(path: Path) -> list[str]:
    """Uncommitted paths, for the note a recovered card carries."""
    result = git("status", "--porcelain", cwd=path)
    return [line[3:] for line in result.out.splitlines() if line[3:]] if result.ok else []
