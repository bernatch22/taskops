"""What counts as a project, and the home directory that used to.

`find_root` walks up looking for `.taskops/`. That was one character too loose: the SESSION
file lives at `~/.taskops/sessions.json`, so every machine that has ever run `taskops login`
has a `.taskops/` in its home directory — and every repository underneath it that had not been
initialised resolved its root to `~`.

Found in the worst way it could be: `taskops init` in a fresh scratch repo printed a hook
warning about `/Users/berna/.git`, and wrote the guide, the cache and the event log into the
home directory instead of the project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.storage import LOG_FILE, PROJECT_DIR, find_root, is_project
from taskops.usecases import init


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory with a login session in it and nothing else — the real shape."""
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    (tmp_path / PROJECT_DIR).mkdir()
    (tmp_path / PROJECT_DIR / "sessions.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_a_session_file_does_not_make_a_directory_a_project(home: Path) -> None:
    """The distinction the whole fix rests on: the LOG is what a project is."""
    assert not is_project(home)
    assert find_root(home) is None


def test_the_log_is_what_makes_it_one(home: Path) -> None:
    project = home / "work" / "thing"
    project.mkdir(parents=True)
    (project / PROJECT_DIR).mkdir()
    (project / LOG_FILE).touch()
    assert find_root(project / "src" / "deep") == project


def test_a_scratch_repo_under_home_becomes_its_own_project(home: Path) -> None:
    """The exact failure, end to end: init in a fresh directory must create a project THERE
    and leave the home directory untouched."""
    scratch = home / "experiments" / "fake-project"
    scratch.mkdir(parents=True)

    report = init(scratch, install_git_hooks=False)

    assert report.root == scratch
    assert (scratch / LOG_FILE).is_file()
    assert not (home / LOG_FILE).exists(), "the home directory was written into"


def test_initialising_the_home_directory_itself_is_refused(home: Path) -> None:
    """The one case the log check cannot catch on its own — standing in `~` and typing the
    command would CREATE the log and make it true. Nobody means this, and the person who
    does has `$TASKOPS_ROOT`."""
    with pytest.raises(BadRequest, match="home directory"):
        init(home, install_git_hooks=False)


def test_a_real_project_that_happens_to_be_home_is_still_usable(home: Path) -> None:
    """The refusal is on CREATING one, not on using one that already exists — otherwise a
    machine somebody deliberately set up that way would stop working after an upgrade."""
    (home / LOG_FILE).touch()
    assert find_root(home) == home
    assert init(home, install_git_hooks=False).root == home
