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
from taskops.usecases.milestone import open_chapter


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
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "taskops")
    return tmp_path


def a_card_with_a_commit(repo: Path, *, name: str = "hecho.txt",
                         title: str = "Ship it") -> str:
    card = plan(repo, [{"title": title, "spec": "s"}], actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor="agent:uno/w1")
    from taskops.engine import branch_for
    branch = branch_for({"id": card, "title": title})    # type: ignore[arg-type]
    git(repo, "switch", "-qc", branch)
    (repo / name).write_text("el trabajo\n")
    git(repo, "add", name)
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


def shared(repo: Path, tmp_path: Path) -> Path:
    """A BARE origin both clones push to — the only shape a team actually has.

    Cloning one developer's working repository instead was a test artefact that hid a real
    assertion: git refuses a push to a non-bare repository's checked-out branch, so "did this
    reach the remote" could never be answered honestly against it.
    """
    origin = tmp_path / "origin.git"
    # `-b main`: a bare repo created with a different default branch leaves HEAD dangling,
    # and every clone of it comes up with no checkout at all.
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    return origin


def clone_of(origin: Path, where: Path) -> Path:
    subprocess.run(["git", "clone", "-q", str(origin), str(where)], check=True)
    for args in (("config", "user.email", "b@example.com"), ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=where, check=True, capture_output=True)
    return where


def test_the_closer_lands_a_branch_it_has_never_seen(repo: Path, tmp_path: Path) -> None:
    """Peer review means the closer is NOT the author, so the branch was written elsewhere.

    Which is the whole point and was never handled: the reviewer's clone had only `main`, the
    merge named a ref that does not exist there, and the card closed unlanded. Branches are
    published on every commit, so the remote has it — nothing was fetching it.
    """
    card = a_card_with_a_commit(repo)
    from taskops.engine import branch_for
    branch = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]
    origin = shared(repo, tmp_path)
    git(repo, "push", "-q", "origin", branch)

    reviewer = clone_of(origin, tmp_path / "clon-del-revisor")
    assert branch not in git(reviewer, "branch", "--format=%(refname:short)").splitlines()

    done = land(reviewer, branch)
    assert done.ok, done.why
    assert "hecho.txt" in git(reviewer, "ls-tree", "--name-only", "main")
    assert git(origin, "rev-parse", "main") == git(reviewer, "rev-parse", "main"), (
        "landing means the SHARED trunk has it, not this machine's copy")


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


def test_two_developers_landing_at_once_do_not_fork_the_trunk(repo: Path,
                                                              tmp_path: Path) -> None:
    """The failure that ended a run where everything else went right.

    Two developers approving each other's cards is the NORMAL case, and each merges into their
    own copy of the trunk. The second one merged onto a trunk hours old: the merge succeeded
    locally, the push was refused as non-fast-forward, and `land` reported `ok` anyway — so the
    board said a card was in a trunk that had never heard of it, which is "done means an agent
    said so", the one thing this system exists to prevent.

    Both halves are asserted here, because either alone leaves the hole: the trunk is caught up
    before the merge, and the push is verified after it.
    """
    first = a_card_with_a_commit(repo, name="uno.txt", title="Card uno")
    second = a_card_with_a_commit(repo, name="dos.txt", title="Card dos")
    origin = shared(repo, tmp_path)
    from taskops.engine import branch_for
    ramas = {card: branch_for({"id": card, "title": title})    # type: ignore[arg-type]
             for card, title in ((first, "Card uno"), (second, "Card dos"))}
    for branch in ramas.values():
        git(repo, "push", "-q", "origin", branch)

    ana = clone_of(origin, tmp_path / "ana")
    leo = clone_of(origin, tmp_path / "leo")      # both cloned BEFORE either landed

    assert land(ana, ramas[first]).ok
    landed = land(leo, ramas[second])             # leo's trunk is now stale

    assert landed.ok, landed.why
    assert git(origin, "rev-parse", "main") == git(leo, "rev-parse", "main")
    trunk = git(leo, "ls-tree", "--name-only", "main")
    assert "uno.txt" in trunk and "dos.txt" in trunk, "neither developer's work is lost"


def test_already_merged_here_is_not_landed(repo: Path, tmp_path: Path) -> None:
    """The second door the same lie walked through.

    A shortcut answered "is this branch already in the trunk" against the LOCAL one and
    returned `ok` without pushing anything — so a retry of a landing whose push had been
    refused reported success, twice, while the shared trunk had still never seen the work.
    It was found by re-running a real landing to repair a real board: `ok: True`, and the sha
    it named was the old merge nobody else had.

    Landed means the trunk everybody pulls has it. Anything else is a card that reads done.
    """
    card = a_card_with_a_commit(repo)
    from taskops.engine import branch_for
    branch = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]
    origin = shared(repo, tmp_path)
    git(repo, "push", "-q", "origin", branch)
    mine = clone_of(origin, tmp_path / "mio")

    git(mine, "fetch", "-q", "origin", f"{branch}:{branch}")
    git(mine, "merge", "--no-ff", "--no-edit", "-q", branch)     # merged, never pushed
    assert git(origin, "rev-parse", "main") != git(mine, "rev-parse", "main")

    done = land(mine, branch)
    assert done.ok, done.why
    assert git(origin, "rev-parse", "main") == git(mine, "rev-parse", "main"), (
        "the shortcut has to push, not just agree with itself")


def test_a_branch_whose_NAME_drifted_still_lands_by_its_commits(repo: Path) -> None:
    """The failure that stranded five cards on a live board.

    `branch_for` computes the name, and so does the clone that CREATES the branch — and two clones
    on two versions truncated it one character apart: the card was claimed as
    `…-toggle-toll-of-a-c` and the branch that existed was `…-toggle-toll-of-a`. So `land` looked
    for a name nothing answered to, and told the closer that the author had not published it.

    Here the branch is deliberately renamed after the commit, which is exactly that shape: the name
    is gone, the commits are not.
    """
    from taskops.engine import branch_for

    card = a_card_with_a_commit(repo, title="Ship it")
    named = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]
    git(repo, "branch", "-m", named, f"{named}-drifted")

    with_name = land(repo, named)
    assert not with_name.ok, "the computed name alone cannot find it — that is the bug"

    sha = git(repo, "rev-parse", "--short", f"{named}-drifted")
    landed = land(repo, named, shas=(sha,))

    assert landed.ok, landed.why
    assert "hecho.txt" in git(repo, "ls-tree", "--name-only", "main")


def test_the_refusal_names_the_COMMITS_and_never_blames_the_author(repo: Path) -> None:
    """The old message asserted something about somebody else's machine — "the author's machine has
    not published it" — and on the board where this was found it was false, and it sent that person
    to run a command they had already run. A refusal may only say what this clone can see."""
    card = a_card_with_a_commit(repo)
    from taskops.engine import branch_for

    named = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]
    git(repo, "branch", "-D", named)

    refused = land(repo, named, shas=("deadbee",))

    assert not refused.ok
    assert "deadbee" in refused.why, "it says what it looked for"
    assert "author" not in refused.why.lower(), "and asserts nothing about another machine"


def test_several_branches_carrying_one_card_are_REFUSED_and_not_guessed(repo: Path) -> None:
    """Two branches with the same commits is a fact about the repository, and a merge picking one
    would be deciding something the person has not. Named, both, and left to them."""
    from taskops.engine import branch_for

    card = a_card_with_a_commit(repo)
    named = branch_for({"id": card, "title": "Ship it"})    # type: ignore[arg-type]
    sha = git(repo, "rev-parse", "--short", named)
    git(repo, "branch", f"{named}-copia", named)
    git(repo, "branch", "-m", named, f"{named}-otra")

    refused = land(repo, named, shas=(sha,))

    assert not refused.ok
    assert f"{named}-copia" in refused.why and f"{named}-otra" in refused.why
