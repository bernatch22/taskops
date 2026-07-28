"""`commit` — may this commit proceed? The verdict, as an exit code.

Was `taskops guard commit`. The name is now the thing being decided, because the caller is a
hook line asking about a commit, not a person reaching for a noun.

Claude Code's hook protocol is the reason this subcommand returns an int instead of text:

```
exit 0  -> allow. stdout is shown to the user, not to the model.
exit 2  -> DENY. stderr goes to the MODEL, which is how the agent learns the reason.
other   -> a non-blocking error; the tool call proceeds.
```

So a refusal must be written to STDERR with code 2, and anything else — including a crash in
taskops itself — must let the commit through. That last part is deliberate: a coordination
tool that blocks commits because its database was locked has broken the thing it exists to
support, and there is a `post-commit` hook that will record the commit anyway.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..._errors import TaskopsError
from ...render import render_verdict
from ...usecases import Verdict, check_commit
from ._args import add_target, committer_is_agent, repo_of, unclaimed_is_allowed

__all__ = ["register", "DENY", "ALLOW", "BLOCK"]

DENY = 2
ALLOW = 0
BLOCK = 1
"""What git reads as "abort". Not 2: that number is Claude Code's, and it means DENY on a
protocol git has never heard of. Any non-zero stops a commit, so the honest code for the git
door is the ordinary failure code."""


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("commit", help="decide whether a commit may proceed")
    add_target(parser)
    parser.add_argument("--message", default="", help="the commit message being written")
    parser.set_defaults(run=run)

    gate = sub.add_parser("precommit", help="the git-side gate (pre-commit, prepare-commit-msg)")
    add_target(gate)
    gate.add_argument("--message-file", default="",
                      help="the file prepare-commit-msg was handed; absent in pre-commit")
    gate.set_defaults(run=run_precommit)


def run(args: argparse.Namespace) -> int:
    """The verdict, as an exit code. Prints the amended message on stdout when allowed.

    Every unexpected failure ALLOWS. Fail-open is the right default for a guard in the commit
    path: the cost of wrongly allowing one commit is a missing association that `post-commit`
    will usually add anyway, and the cost of wrongly blocking is a developer who cannot commit
    and a tool they will uninstall.
    """
    try:
        verdict = check_commit(repo_of(args), str(args.message), actor=str(args.actor))
    except (TaskopsError, OSError) as err:
        print(f"taskops guard could not run ({err}) — allowing the commit", file=sys.stderr)
        return ALLOW
    if not verdict.allowed:
        print(render_verdict(verdict), file=sys.stderr)
        return DENY
    if verdict.message and verdict.message != args.message:
        print(verdict.message)
    return ALLOW


def run_precommit(args: argparse.Namespace) -> int:
    """The same verdict, reached through git instead of through Claude Code.

    ONE judgement, two doors: `check_commit` is the only thing that decides, here as in
    `run`. Two doors onto "may this commit run" that each judged for themselves would start
    disagreeing, and the disagreement would surface as a commit one door allowed and the
    other denied — with no way to tell which was right.

    Two hook lines share this verb. `pre-commit` has no message to show for it (git has not
    composed one yet: `.git/COMMIT_EDITMSG` does not even exist at that point), so it is the
    door that REFUSES. `prepare-commit-msg` is handed the message file and can rewrite it, so
    it is the door that STAMPS the trailer — and it never refuses, because pre-commit already
    had that conversation and because prepare-commit-msg also fires on merges, where aborting
    would break a `git pull` that has nothing to do with anybody's lease.
    """
    try:
        message = _message(str(args.message_file))
        verdict = check_commit(repo_of(args), message, actor=str(args.actor))
    except Exception as err:  # noqa: BLE001 — see below
        # BROADER than the `commit` verb above, and deliberately so. That one answers Claude
        # Code, where an unexpected exception still reaches the agent as text. This one is
        # wired into `git commit` for every commit in the repository, including a stranger's,
        # so ANY failure of ours — a corrupt sqlite file, a half-written schema, a bug — has
        # to end in the commit happening. A typed-only catch is a promise to fail open that
        # only covers the failures we already thought of; a corrupt database walked straight
        # through it and blocked git with a traceback.
        print(f"taskops could not run ({err}) — allowing the commit", file=sys.stderr)
        return ALLOW
    if verdict.allowed:
        return _stamp(str(args.message_file), message, verdict.message)
    return ALLOW if args.message_file else _refuse(verdict, str(args.actor))


def _refuse(verdict: Verdict, actor: str) -> int:
    """ASYMMETRIC on purpose: an agent is stopped, a human is told.

    `usecases.hooks.HOOKS` records why `pre-commit` was left out for years, and that reason is
    about PEOPLE — a refusal reaches a human as a failed command with no context, and a
    developer cherry-picking onto main is doing something legitimate. It still holds, so a
    human gets one line on stderr and their commit. An agent gets the opposite: it reads
    stderr, it can act on it, and the refusal names the exact call that fixes it.
    """
    if committer_is_agent(actor) and not unclaimed_is_allowed():
        print(render_verdict(verdict), file=sys.stderr)
        return BLOCK
    print(f"taskops: {verdict.reason} (allowed — you are not an agent)", file=sys.stderr)
    return ALLOW


def _message(path: str) -> str:
    return Path(path).read_text(encoding="utf-8") if path else ""


def _stamp(path: str, current: str, wanted: str) -> int:
    """Write the trailer back into the message file. Never fails the commit.

    An allowed commit that could not be stamped is a commit `post-commit` will still bind by
    its branch — losing a trailer is a smaller harm than refusing work the guard just approved.
    """
    try:
        if path and wanted and wanted != current:
            Path(path).write_text(wanted, encoding="utf-8")
    except OSError as err:
        print(f"taskops could not write the trailer ({err})", file=sys.stderr)
    return ALLOW
