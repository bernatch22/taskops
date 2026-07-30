"""The git-side gate, run by REAL git in a REAL repository.

`check_commit` already had a test. What it did not have was a PATH: the verdict was only ever
consulted by Claude Code's PreToolUse hook, so it covered an agent shelling out through the
Bash tool and nothing else — not a script, not a rebase, not another harness. These tests
drive `git commit` itself, because the thing under test is whether git runs our line at all
and what it does with the exit code, and only git can answer that.

The asymmetry is the design and every test here is one half of it: an agent is refused, a
human is warned and passes.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from taskops.transports.mcp.dispatch import call_tool
from taskops.usecases import ask, init, next_task, plan

AGENT = "agent:berna/one"


def git(root: Path, *args: str, env: dict[str, str] | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=check, env=env)


def env_of(**over: str) -> dict[str, str]:
    """The environment a hook will see, with the agent markers explicitly REMOVED first.

    Not paranoia: this suite is itself frequently run from inside Claude Code, which exports
    `CLAUDECODE=1` into pytest and therefore into the git it spawns. Without this line the
    "a human passes" test would silently be a second "an agent is refused" test, and it would
    pass for the wrong reason.
    """
    clean = {k: v for k, v in os.environ.items()
             if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "TASKOPS_ACTOR",
                          "TASKOPS_ALLOW_UNCLAIMED")}
    return {**clean, **over}


def as_agent(**over: str) -> dict[str, str]:
    return env_of(CLAUDECODE="1", TASKOPS_ACTOR=AGENT, **over)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "berna@example.com")
    git(tmp_path, "config", "user.name", "Berna")
    (tmp_path / "README.md").write_text("start\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    init(tmp_path)
    return tmp_path


def stage(repo: Path, name: str = "work.py") -> None:
    (repo / name).write_text(f"# {name}\n", encoding="utf-8")
    git(repo, "add", "-A")


def message_of(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%B").stdout


def branch_of(text: str) -> str:
    found = re.search(r"tk/[\w-]+/[\w.-]+", text)
    if not found:
        raise AssertionError(f"no branch name in:\n{text}")
    return found.group(0)


# ---- the asymmetry


def test_an_agent_committing_with_no_card_is_refused(repo: Path) -> None:
    """THE hole this card exists to close. Before the hook, this commit succeeded."""
    stage(repo)
    done = git(repo, "commit", "-m", "sin card", env=as_agent(), check=False)
    assert done.returncode != 0, "the pre-commit hook let an unclaimed agent commit through"
    assert "taskops_next" in done.stderr, "the refusal must BE the fix, not a complaint"
    assert git(repo, "log", "--oneline").stdout.count("\n") == 1, "the commit still landed"


def test_a_human_committing_with_no_card_passes(repo: Path) -> None:
    """Unchanged behaviour, on purpose. A developer cherry-picking onto main is doing
    something legitimate, and a failed command with no context is how a tool gets uninstalled.
    The warning on stderr is the whole intervention."""
    stage(repo)
    done = git(repo, "commit", "-m", "a human commit", env=env_of(), check=False)
    assert done.returncode == 0, done.stderr
    assert "taskops" in done.stderr, "a human should at least be told"


def test_a_claude_session_with_a_dev_identity_is_still_a_human(repo: Path) -> None:
    """`CLAUDECODE=1` alone does NOT make a committer an agent, and this is the test that
    would have caught believing otherwise.

    That variable is inherited by every descendant of a session — the developer's own shell,
    `pytest`, and the `git` either of them spawns. Trusting it turned five unrelated
    end-to-end tests into "unclaimed agent commits". The identity is the honest signal: with
    no `$TASKOPS_ACTOR` taskops resolves `dev:<git email>`, and refusing an actor it calls a
    developer would be the asymmetry contradicting itself.
    """
    stage(repo)
    done = git(repo, "commit", "-m", "a person inside a session",
               env=env_of(CLAUDECODE="1"), check=False)
    assert done.returncode == 0, done.stderr


def test_the_escape_hatch_lets_an_agent_through(repo: Path) -> None:
    """`TASKOPS_ALLOW_UNCLAIMED=1` for CI and scripted commits. A rule with no honest exit
    gets bypassed by `--no-verify`, and then nothing is recorded at all."""
    stage(repo)
    done = git(repo, "commit", "-m", "ci commit",
               env=as_agent(TASKOPS_ALLOW_UNCLAIMED="1"), check=False)
    assert done.returncode == 0, done.stderr


def test_a_claimed_agent_commits_and_gets_the_trailer(repo: Path) -> None:
    """The allowed path, end to end: the gate passes AND `prepare-commit-msg` stamps the
    trailer, which is what binds the commit after a squash loses the branch name."""
    planned = plan(repo, [{"title": "Add the endpoint", "spec": "x"}], actor=AGENT)
    task_id = planned["created"][0]["id"]
    claimed = next_task(repo, actor=AGENT, session="sess-1")
    git(repo, "switch", "-q", "-c", claimed["claim"]["branch"])

    stage(repo)
    done = git(repo, "commit", "-m", "Add the endpoint", env=as_agent(), check=False)
    assert done.returncode == 0, done.stderr
    assert f"Task: {task_id}" in message_of(repo), "the trailer was not stamped"
    assert len(ask(repo, task_id, actor=AGENT)["commits"]) == 1


# ---- living with the hooks that were already there


def test_an_existing_pre_commit_hook_keeps_running(tmp_path: Path) -> None:
    """Chaining, proven on the hook that can now REFUSE. Deleting somebody's linter to install
    a task tracker would deserve everything that followed."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "berna@example.com")
    git(tmp_path, "config", "user.name", "Berna")
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\ntouch lint-ran\n", encoding="utf-8")
    hook.chmod(0o755)
    init(tmp_path)

    assert "touch lint-ran" in hook.read_text(encoding="utf-8")
    stage(tmp_path)
    git(tmp_path, "commit", "-q", "-m", "human commit", env=env_of(), check=False)
    assert (tmp_path / "lint-ran").is_file(), "the repository's own pre-commit was lost"


def test_re_running_init_is_idempotent(repo: Path) -> None:
    """`taskops init` is the repair path, so it has to be safe to run twice — a hook that
    grew a second copy of our line on every init would run the gate N times."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    before = hook.read_text(encoding="utf-8")
    init(repo)
    after = hook.read_text(encoding="utf-8")
    assert after == before
    assert after.count("precommit") == 1


# ---- what cannot be enforced, stated honestly


def test_no_verify_skips_the_gate_and_the_binding_is_lost(repo: Path) -> None:
    """`--no-verify` skips every git hook and NOTHING in a repository can stop it.

    So this test pins git's behaviour rather than pretending otherwise: the commit lands. What
    it also pins is the size of the remaining hole — `post-commit` is skipped too, so the
    commit is not merely unattributed, it is unseen. `ingest_commit` deliberately refuses to
    guess a task, which is right, but it means there is today no record anywhere that an
    unattributable commit happened. Detection beats a lock you cannot fit, and that detection
    does not exist yet (reported, not invented here).
    """
    planned = plan(repo, [{"title": "T", "spec": "x"}], actor=AGENT)
    stage(repo)
    done = git(repo, "commit", "--no-verify", "-m", "around the gate", env=as_agent(),
               check=False)
    assert done.returncode == 0, done.stderr
    assert ask(repo, planned["created"][0]["id"], actor=AGENT)["commits"] == []


def test_a_repository_taskops_cannot_read_still_commits(tmp_path: Path) -> None:
    """Fail OPEN on taskops' own failures, fail CLOSED on the case the gate exists for.

    A coordination tool that blocks commits because its database was unreadable has broken the
    thing it exists to support.
    """
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "berna@example.com")
    git(tmp_path, "config", "user.name", "Berna")
    init(tmp_path)
    (tmp_path / ".taskops" / "db.sqlite").write_text("not a database", encoding="utf-8")
    stage(tmp_path)
    done = git(tmp_path, "commit", "-m", "x", env=as_agent(), check=False)
    assert done.returncode == 0, done.stderr


# ---- the loop an agent actually runs


def test_the_agent_loop_from_mcp_plan_to_a_guarded_commit(repo: Path) -> None:
    """plan over MCP -> claim -> commit on its branch -> the gate ALLOWS and stamps it.

    The other half of the card was already built; this proves the two halves meet. Every step
    is a real tool call or a real git command — no use case is reached behind MCP's back.
    """
    planned = call_tool("taskops_plan", {"repo_path": str(repo), "actor": AGENT,
                                         "tasks": [{"title": "Ship the loop",
                                                    "spec": "prove it end to end"}]})
    assert not planned.failed, planned.text

    claimed = call_tool("taskops_next", {"repo_path": str(repo), "actor": AGENT})
    assert not claimed.failed, claimed.text
    branch = branch_of(claimed.text)
    git(repo, "switch", "-q", "-c", branch)

    stage(repo, "loop.py")
    done = git(repo, "commit", "-m", "Ship the loop", env=as_agent(), check=False)
    assert done.returncode == 0, done.stderr
    assert f"Task: {branch.split('/')[1]}" in message_of(repo)


def test_a_commit_in_a_worktree_belongs_to_the_lease_holder_not_the_machine(
        repo: Path) -> None:
    """Found in a live run and diagnosed from a card comment, which is the wrong place to find
    out. A worker sub-agent commits through Bash inside its worktree; that Bash carries no
    `$TASKOPS_ACTOR`, so the guard resolved the DEVELOPER — `dev:dev1` instead of
    `agent:dev1/w2` — and waved the commit through with "allowed, you are not an agent". The
    agent rules did not apply to an agent.

    A task branch with a live lease already knows better than git config: whoever holds it is
    by definition the one doing this work.
    """
    from taskops.usecases.guard import check_commit

    card = plan(repo, [{"title": "held by an agent", "spec": "x"}],
                actor="dev:berna")["created"][0]["id"]
    claimed = next_task(repo, task=card, actor="agent:berna/w2")["claim"]
    _switch(repo, claimed["branch"])

    verdict = check_commit(repo, "feat: work done in the worktree")

    assert verdict.allowed, verdict.reason
    assert f"Task: {card}" in verdict.message


def test_a_stated_actor_is_never_overridden_by_the_lease(repo: Path) -> None:
    """The first fence, same as `attributed`: an identity somebody stated is theirs, right or
    wrong. Inferring over it would make a wrong `--actor` impossible to see."""
    from taskops.usecases.guard import check_commit

    card = plan(repo, [{"title": "held", "spec": "x"}], actor="dev:berna")["created"][0]["id"]
    claimed = next_task(repo, task=card, actor="agent:berna/w2")["claim"]
    _switch(repo, claimed["branch"])

    verdict = check_commit(repo, "feat: x", actor="agent:berna/somebody-else")

    assert not verdict.allowed
    assert "holds no live lease" in verdict.reason


def _switch(repo: Path, branch: str) -> None:
    git(repo, "switch", "-c", branch)


def test_the_recorded_commit_names_the_agent_not_the_machine(repo: Path) -> None:
    """Half a fix is its own bug. The guard was taught to attribute a commit to the branch's
    lease holder and the RECORDER was left resolving git config — so a live run produced eight
    commits made by `agent:dev1/w1..w8` and bound every one of them to `dev:dev1`. The board
    then shows a person as the author of work eight agents did, and the fix that was supposed
    to prevent exactly that reads as if it had worked."""
    from taskops.storage import Store
    from taskops.usecases.ingest import ingest_commit

    card = plan(repo, [{"title": "held by an agent", "spec": "x"}],
                actor="dev:berna")["created"][0]["id"]
    claimed = next_task(repo, task=card, actor="agent:berna/w2")["claim"]
    _switch(repo, claimed["branch"])
    (repo / "work.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"feat: x\n\nTask: {card}", "--no-verify")

    ingest_commit(repo)

    with Store(repo) as store:
        bound = store.events.of_task(card, kinds=("commit",))
    assert [event["actor"] for event in bound] == ["agent:berna/w2"]


def test_a_task_branch_publishes_itself(tmp_path: Path) -> None:
    """The deadlock that `reviewer: peer` made fatal, watched live: eight cards implemented on
    eight branches, handed over, and the OTHER developer rejected seven with "no hay codigo".
    Every rejection was false — the commits existed on branches that had never left the first
    machine, and the reviewer was looking at its own checkout of `main`.

    The only person allowed to close was the only person who could not see the work.
    """
    from taskops.usecases.ingest import ingest_commit

    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "clone"
    git_init(repo)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)
    init(repo)
    card = plan(repo, [{"title": "work", "spec": "x"}], actor="dev:berna")["created"][0]["id"]
    claimed = next_task(repo, task=card, actor="agent:berna/w1")["claim"]
    git(repo, "switch", "-c", claimed["branch"])
    (repo / "work.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"feat: x\n\nTask: {card}", "--no-verify")

    ingest_commit(repo)

    landed = subprocess.run(["git", "ls-remote", "--heads", str(origin)],
                            capture_output=True, text=True, check=True).stdout
    assert claimed["branch"] in landed, "a peer on another machine has to be able to fetch it"


def test_main_is_never_published_on_your_behalf(tmp_path: Path) -> None:
    """Only `tk/` branches, which taskops created for exactly this. Pushing anything else would
    be a coordination tool taking a decision about somebody's own work."""
    from taskops.usecases.publish import publish_branch

    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "clone"
    git_init(repo)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)

    assert publish_branch(repo, "main") is False
    assert subprocess.run(["git", "ls-remote", "--heads", str(origin)],
                          capture_output=True, text=True, check=True).stdout.strip() == ""


def git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "b@e.com")
    git(repo, "config", "user.name", "B")
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")
