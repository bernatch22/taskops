"""Fixtures shared by the whole suite.

The suite is fully OFFLINE and never sleeps: leases expire because a test passes a
later `now`, not because it waited. A test that needs a real clock is testing
`time`, not this engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from taskops.storage import LOG_FILE, PROJECT_DIR, Store

CLOCK = 1_800_000_000.0
"""A fixed 'now' every test measures from. A literal rather than `now()`, so a
failure reads the same tomorrow as it did today."""


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every TASKOPS_* setting comes OUT of the environment, for every test.

    The developer's own shell configures this package — an actor identity above
    all — and those leak: a test asserting the resolved default passes on a laptop
    with `TASKOPS_ACTOR` unset and fails on the one that has it exported. A suite
    whose result depends on whose shell ran it is not a suite.
    """
    for name in ("TASKOPS_ACTOR", "TASKOPS_SESSION", "TASKOPS_ROOT"):
        monkeypatch.delenv(name, raising=False)
    # No test may BIND A PORT as a side effect. `SessionStart` offers to start a local board,
    # which is a real web server in a real subprocess — four hook tests began spawning one
    # each the day that landed, and a suite that leaves servers behind is a suite whose next
    # run fails for a reason in the last one. The offer itself is tested by calling it.
    monkeypatch.setenv("TASKOPS_NO_UI", "1")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An initialised project directory, with no git repository in it.

    Separate from the `repo` fixture on purpose: most of the engine has nothing to
    do with git, and a test that spawns `git init` to check a state transition is
    slow for no reason and hides which of the two is broken.
    """
    (tmp_path / PROJECT_DIR).mkdir()
    # The LOG, not just the directory: `.taskops/` alone is what `~/.taskops/sessions.json`
    # also looks like, and a fixture that skipped the log was a fixture agreeing with the bug
    # that made the home directory a project.
    (tmp_path / LOG_FILE).touch()
    return tmp_path


@pytest.fixture
def store(root: Path) -> Iterator[Store]:
    """An open Store on a fresh database. Committed and closed at teardown."""
    with Store(root) as opened:
        yield opened
