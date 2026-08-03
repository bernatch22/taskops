"""Where a LOCAL project's board is listening, and starting one when it is not.

The behaviour under test is a note on disk and a liveness check, both of which are pure enough
to drive from literals — so nothing here binds a port except the one test that says it does, and
that one is the seam: a note nobody verified is a browser pointed at whatever now owns that port.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Iterator

import pytest

from taskops.usecases.localui import (
    UI_FILE,
    forget_ui,
    local_ui,
    note_ui,
    running_ui,
    start_ui,
)

PROJECT = ".taskops"


def note(root: Path, **fields: object) -> None:
    (root / PROJECT / UI_FILE).write_text(json.dumps(fields), encoding="utf-8")


# ---- the note


def test_a_project_with_no_note_is_not_running(root: Path) -> None:
    assert running_ui(root) == 0
    assert local_ui(root, start=False) == ""


def test_a_dead_pid_is_not_a_running_board(root: Path) -> None:
    """The common case for a stale file, and the cheap half of the check: a board killed with
    `-9` leaves its note behind, and following it would open a page nothing serves."""
    note(root, pid=999_999, port=2140)

    assert running_ui(root) == 0


def test_a_live_pid_on_a_dead_port_is_not_one_either(root: Path) -> None:
    """THE reason there are two checks. A pid the kernel has since handed to something else is
    alive and answers signal 0 — so trusting it alone points a browser at a port that may now
    belong to another program entirely. `os.getpid()` is guaranteed to be a live pid that is
    not serving a board."""
    note(root, pid=os.getpid(), port=1)      # port 1 is privileged and nothing here binds it

    assert running_ui(root) == 0


def test_a_note_that_is_not_json_reads_as_nothing_running(root: Path) -> None:
    """Truncated by a crash mid-write. It must read as "no board", never raise: every caller
    is a hook or a greeting, and neither may fail over a cache file."""
    (root / PROJECT / UI_FILE).write_text("{oops", encoding="utf-8")

    assert running_ui(root) == 0


def test_forgetting_a_board_that_was_never_noted_is_fine(root: Path) -> None:
    forget_ui(root)


# ---- the switch


def test_the_env_var_turns_the_offer_off(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`TASKOPS_NO_UI=1`, the sibling of `TASKOPS_NO_SWEEP=1`. Somebody who does not want a
    hook starting processes on their machine must not have to uninstall the hook to say so —
    and it is what keeps this suite from binding ports."""
    monkeypatch.setenv("TASKOPS_NO_UI", "1")

    assert start_ui(root) == 0
    assert local_ui(root) == ""


@pytest.fixture
def listening() -> Iterator[int]:
    """A real bound port, so `running_ui`'s connect succeeds against a live pid.

    An actual socket and not a stub: the whole point of that second check is that it touches
    the network stack, and a fake would test the mock. Closed at teardown — a suite that leaks
    listeners is a suite whose next run fails for a reason in the last one.
    """
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        yield int(held.getsockname()[1])


def test_a_board_somebody_else_started_is_still_reported_with_the_offer_off(
        root: Path, listening: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """The flag disables STARTING, not looking. A `taskops ui` the person ran themselves is a
    board that exists, and refusing to name it would make the flag mean something it does not."""
    monkeypatch.setenv("TASKOPS_NO_UI", "1")
    note_ui(root, listening)

    assert local_ui(root) == f"http://127.0.0.1:{listening}/"
