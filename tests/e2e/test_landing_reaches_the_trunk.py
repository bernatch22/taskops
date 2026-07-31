"""The step after `done`: the work is where a person looks for it.

Every failure pinned here came from one live run in which four cards closed, four branches were
pushed, and `main` stayed on the seed commit — the exact hole `usecases/land.py` was written to
close, reopened by three unrelated details that only appear when a real clone talks to a real
server. None of them was in `land` itself, which is why none of the existing tests caught them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops.usecases import init, next_task, plan, update
from taskops.usecases.land import _has_board, _trunk, land


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "seed.txt").write_text("seed\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "seed")
    init(tmp_path)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "taskops")
    return tmp_path


def a_card_with_a_commit(repo: Path) -> str:
    card = plan(repo, [{"title": "Ship it", "spec": "s"}], actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor="agent:uno/w1")
    from taskops.engine import branch_for
    branch = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]
    git(repo, "switch", "-qc", branch)
    (repo / "hecho.txt").write_text("el trabajo\n")
    git(repo, "add", "hecho.txt")
    git(repo, "commit", "-qm", f"[{card}] hecho")
    git(repo, "switch", "-q", "main")
    return card


def test_an_untracked_file_does_not_make_a_repository_unlandable(repo: Path) -> None:
    """The one that broke every joined clone.

    `taskops join` leaves an untracked `.mcp.json` and `.taskops/` behind forever, so a check
    for "any change at all" reported a dirty tree on every card in every repository that had
    ever joined a board — and nothing ever landed. A checkout cannot lose an untracked file:
    git refuses outright when the trunk carries one by the same name, and that failure is
    reported like any other.
    """
    card = a_card_with_a_commit(repo)
    (repo / "sin-seguir.json").write_text("{}\n")

    from taskops.engine import branch_for
    done = land(repo, branch_for({"id": card, "title": "Ship it"}))  # type: ignore[arg-type]
    assert done.ok, done.why
    assert "hecho.txt" in git(repo, "ls-tree", "--name-only", "main")


def test_a_board_that_is_not_in_git_cannot_be_lost_by_a_checkout(repo: Path) -> None:
    """The precondition asked the wrong question.

    It refused unless the log was committed on the trunk — correct when the log is a tracked
    file, and nonsense for every project with a remote, where the board lives on the server and
    `.taskops/` is a gitignored cache. The trunk of course did not carry a file deliberately
    kept out of git, so landing was refused on exactly the boards that have two developers.
    """
    git(repo, "rm", "-r", "-q", "--cached", ".taskops")
    (repo / ".gitignore").write_text(".taskops/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the board is a cache here")

    assert _trunk(repo) == "main"
    assert _has_board(repo, "main"), "nothing tracked means nothing to lose"


def test_the_server_never_tries_to_merge(repo: Path) -> None:
    """`local=True` is the SERVER's flag, and the server has state and no checkout.

    It ran the merge anyway: git failed at every step, the failure was misread as a clean tree,
    and the card was recorded "not in the trunk — no main or master branch in this repository",
    naming a repository that does not exist. Four cards in one run, and the board's own LAND
    group then pointed at a problem nobody could act on.
    """
    card = a_card_with_a_commit(repo)
    update(repo, card, status="review", comment="listo", actor="agent:uno/w1")
    update(repo, card, status="done", comment="revisada", actor="dev:dos",
           local=True, evidence="")

    from taskops.storage import Store
    with Store(repo) as store:
        assert not store.events.of_task(card, kinds=("landed",)), (
            "the server must record no landing at all — a lie is worse than a silence")


def test_the_closer_lands_a_branch_it_has_never_seen(repo: Path, tmp_path: Path) -> None:
    """Peer review means the closer is NOT the author, so the branch was written elsewhere.

    Which is the whole point and was never handled: the reviewer's clone had only `main`, the
    merge named a ref that does not exist there, and the card closed unlanded. Branches are
    published on every commit, so the remote has it — nothing was fetching it.
    """
    card = a_card_with_a_commit(repo)
    from taskops.engine import branch_for
    branch = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]

    reviewer = tmp_path / "clon-del-revisor"
    subprocess.run(["git", "clone", "-q", str(repo), str(reviewer)], check=True)
    for args in (("config", "user.email", "b@example.com"), ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=reviewer, check=True, capture_output=True)
    assert branch not in git(reviewer, "branch", "--format=%(refname:short)").splitlines()

    done = land(reviewer, branch)
    assert done.ok, done.why
    assert "hecho.txt" in git(reviewer, "ls-tree", "--name-only", "main")


def test_a_modified_gitignore_does_not_block_every_landing_forever(repo: Path) -> None:
    """`taskops join` rewrites `.gitignore` and never commits it, so a blanket "is the tree
    dirty" check refused every landing on every board that has ever been joined — which is
    every board with two developers. Git refuses precisely what is unsafe (`switch` and
    `merge` both name the file they would overwrite) and that refusal is reported like any
    other, so the guarantee survives without the false negative."""
    card = a_card_with_a_commit(repo)
    (repo / ".gitignore").write_text("*.pyc\n# lo que join agrega\n.taskops/db.sqlite\n")

    from taskops.engine import branch_for
    done = land(repo, branch_for({"id": card, "title": "Ship it"}))  # type: ignore[arg-type]
    assert done.ok, done.why
