"""`taskops status` — the facts it assembles, and the two ways it draws them.

Three promises are pinned here, because all three are the reason the command exists:

* it is LOCAL. A status that opened a socket would be slow exactly when the network is
  bad, which is when somebody runs it twice — so a test replaces `socket.socket` with an
  explosion and the whole read still passes.
* `rich` is OPTIONAL. taskops is installed into every agent's environment on every
  machine, so the suite has to prove the command works with the library ABSENT — hidden
  here by poisoning `sys.modules`, which is what an uninstalled package looks like.
* the two painters show the SAME facts. A pretty version that knows something the plain
  one does not is two commands wearing one name.
"""

from __future__ import annotations

import re
import socket
import sys
from pathlib import Path

import pytest

from taskops._clock import now
from taskops.contracts import Lease, Task
from taskops.render.status import render_status
from taskops.storage import Store
from taskops.usecases.status import status

ME = "dev:berna"
THEM = "agent:berna/polecat-1"
ESCAPES = re.compile("\033\\[[0-9;]*m")


def _task(store: Store, task_id: str, state: str = "ready", *, age_days: float = 0.0,
          title: str = "") -> None:
    stamp = now() - age_days * 86400.0
    store.tasks.insert(Task(id=task_id, title=title or f"Work {task_id}", spec="",
                            status=state, priority=2, parent=None, labels=[], files=[],
                            assignee="", reviewer="", created_by=ME, created=stamp, updated=stamp))


def _lease(store: Store, task_id: str, actor: str, *, left: float = 900.0) -> None:
    store.leases.acquire(Lease(task=task_id, actor=actor, session="s", branch="b",
                               acquired=now(), expires=now() + left))


def _hide_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    """What an uninstalled `rich` looks like to an import — including the submodules
    another test may already have pulled into `sys.modules` and left cached there."""
    for name in [n for n in list(sys.modules) if n == "rich" or n.startswith("rich.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "rich", None)


@pytest.fixture
def project(root: Path) -> Path:
    """A small board: one card claimed by me, one by somebody else, one blocker."""
    with Store(root) as store:
        _task(store, "tk-mine", "in_progress", title="The card I am on")
        _task(store, "tk-theirs", "in_progress")
        _task(store, "tk-stuck", "ready", title="The blocker")
        _task(store, "tk-old", "ready", age_days=30.0)
        _lease(store, "tk-mine", ME)
        _lease(store, "tk-theirs", THEM)
        for waiting in ("tk-mine", "tk-theirs", "tk-old"):
            store.deps.add("tk-stuck", waiting)
    return root


def test_status_never_opens_a_socket(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Speed is the feature. Without `--fetch` there is no network call to make, so the
    cheapest way to prove it is to make one impossible and read the board anyway."""

    def explode(*_: object, **__: object) -> None:
        raise AssertionError("status opened a socket")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    assert status(project, actor=ME)["total"] == 4


def test_your_cards_and_theirs_are_told_apart(project: Path) -> None:
    """The one distinction the whole screen is organised around: a claim I hold is work
    in progress, and the identical row under somebody else's name is a collision."""
    found = status(project, actor=ME)
    assert [c["task"] for c in found["mine"]] == ["tk-mine"]
    assert [(w["actor"], w["task"]) for w in found["others"]] == [(THEM, "tk-theirs")]


def test_a_lease_running_out_is_marked_before_it_lapses(root: Path) -> None:
    """`expiring` is decided in the use case so that no renderer may pick its own
    threshold — two screens disagreeing about which claim is in trouble is worse than
    neither of them saying so."""
    with Store(root) as store:
        _task(store, "tk-soon", "in_progress")
        _lease(store, "tk-soon", ME, left=30.0)
    claim = status(root, actor=ME)["mine"][0]
    assert claim["expiring"] and claim["left"] < 60.0


def test_the_bottleneck_is_the_card_the_most_others_wait_on(project: Path) -> None:
    """The DAG is already there, so the one card worth doing first is a max, not a guess."""
    stuck = status(project, actor=ME)["bottleneck"]
    assert stuck is not None
    assert (stuck["task"], stuck["blocks"]) == ("tk-stuck", 3)


def test_nothing_blocking_anything_is_None_rather_than_a_zero(root: Path) -> None:
    with Store(root) as store:
        _task(store, "tk-alone")
    assert status(root, actor=ME)["bottleneck"] is None


def test_cards_nobody_has_touched_are_counted(project: Path) -> None:
    """A board of green columns hides the card somebody half-did and never reopened."""
    found = status(project, actor=ME, idle_days=7)
    assert (found["idle"], found["idle_days"]) == (1, 7)


def test_a_project_with_no_remote_is_local_only_and_not_an_error(project: Path) -> None:
    """Most projects never configure one. Zeroes and an empty host, never a raise."""
    assert status(project, actor=ME)["sync"] == {"host": "", "ahead": 0, "last_sync": 0.0}


def test_a_goal_nobody_has_set_yet_renders_as_nothing(project: Path) -> None:
    """It ships in a parallel card. Empty renders as NOTHING — never a placeholder row
    that teaches a reader to skip the line forever."""
    found = status(project, actor=ME)
    assert found["objective"] == ""
    assert "objective" not in render_status(found, colour=False)


def test_the_whole_command_works_with_rich_absent(project: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """`None` in `sys.modules` is what an uninstalled package looks like to an import.

    The extra is optional on purpose, so this is the path most machines take: every fact
    the panel would show has to survive the fallback, or the plain output is a lesser
    command wearing the same name.
    """
    _hide_rich(monkeypatch)
    text = render_status(status(project, actor=ME), colour=True)
    for fact in ("tk-mine", "tk-theirs", "tk-stuck", "4 card(s)", "local only"):
        assert fact in ESCAPES.sub("", text)


def test_colour_off_emits_no_escape_codes_at_all(project: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """A status piped into a file with escapes in it is a bug — pinned on BOTH painters,
    since the fallback and the panel decide it in completely different code."""
    found = status(project, actor=ME)
    assert "\033" not in render_status(found, colour=False)
    _hide_rich(monkeypatch)
    assert "\033" not in render_status(found, colour=False)


def test_yesterdays_write_up_is_reported_as_missing_rather_than_assumed(project: Path) -> None:
    """The habit slips one day at a time, so the question is about YESTERDAY: today's
    report is not late yet, and asking about it would cry wolf every morning."""
    reports = status(project, actor=ME)["reports"]
    assert reports["yesterday_written"] is False
    assert reports["yesterday"] < reports["today"]
