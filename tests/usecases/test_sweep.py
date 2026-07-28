"""`report sweep` — the backfill that is safe to run on any schedule, twice.

The assertions here are almost all about what did NOT happen. A sweep's whole claim is that
the trigger does not matter, and the only way to prove that is to count the calls to the one
thing a run costs: `narrate`. A test that checked the files were unchanged would pass just as
happily against a version that re-narrated every day and wrote the same prose back — which is
the version that turns a 9am wake-up into a bill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import taskops.usecases.dossier as dossier
from taskops._clock import now
from taskops._errors import AlreadyNarrating, BadRequest, NarrationFailed
from taskops._ids import event_id
from taskops.contracts import Event
from taskops.engine.day import date_of, shift, window
from taskops.render import NARRATION
from taskops.storage import Store
from taskops.usecases.dossier import report_path
from taskops.usecases.sweep import sweep

PROSE = "The day held one comment and nothing closed."


class Counter:
    """Stands in for `narrate` and remembers being called. The unit the budget is measured in:
    one call is one model invocation, whatever the file on disk ends up looking like."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._raises = raises

    def __call__(self, dossier_text: str, **_: object) -> str:
        self.calls.append(dossier_text)
        if self._raises:
            raise self._raises
        return PROSE


@pytest.fixture
def narrate(monkeypatch: pytest.MonkeyPatch) -> Counter:
    """Nothing in this suite spawns `claude`. The seam is the engine function `digest` calls,
    so the dossier is still written for real and the idempotence being tested is the real one."""
    counter = Counter()
    monkeypatch.setattr(dossier, "narrate", counter)
    return counter


def yesterday() -> str:
    return shift(date_of(now()), days=-1)


def log(root: Path, *days: str) -> None:
    """One shared event per named day — enough to make the day exist in the log."""
    with Store(root) as store:
        for day in days:
            body = {"text": f"work on {day}"}
            ts = window(day)[0] + 3600.0
            store.events.append(Event(
                id=event_id(task="tk-1", actor="dev:ana", kind="comment", body=body, ts=ts),
                task="tk-1", actor="dev:ana", kind="comment", body=body, ts=ts))


def test_a_day_with_events_and_no_report_gets_narrated(root: Path, narrate: Counter) -> None:
    day = yesterday()
    log(root, day)
    done = sweep(root)
    assert done["narrated"] == [day]
    assert len(narrate.calls) == 1
    assert PROSE in report_path(root, day).read_text(encoding="utf-8")


def test_the_second_sweep_spends_nothing(root: Path, narrate: Counter) -> None:
    """THE card. Not "the file is unchanged" — the model was never asked."""
    log(root, yesterday())
    sweep(root)
    spent = len(narrate.calls)
    again = sweep(root)
    assert again == {"narrated": [], "skipped": [], "pushed": 0, "truncated": 0}
    assert len(narrate.calls) == spent


def test_today_is_never_narrated(root: Path, narrate: Counter) -> None:
    """A day is not narrated until it has ended: a report written at 3pm would be missing the
    evening forever, because the next sweep sees a file that already carries prose."""
    log(root, date_of(now()))
    assert sweep(root)["narrated"] == []
    assert narrate.calls == []


@pytest.mark.usefixtures("narrate")
def test_the_hole_is_filled_oldest_first(root: Path) -> None:
    """A machine that was away a week fills the week in the order the week happened."""
    days = [shift(date_of(now()), days=-n) for n in (3, 2, 1)]
    log(root, *days)
    assert sweep(root)["narrated"] == days


@pytest.mark.usefixtures("narrate")
def test_a_deleted_report_comes_back(root: Path) -> None:
    """Selection reads the LOG, not the reports directory. A day whose file somebody removed
    is a day that still happened, and a filesystem-driven sweep would call it done."""
    day = yesterday()
    log(root, day)
    sweep(root)
    report_path(root, day).unlink()
    assert sweep(root)["narrated"] == [day]


def test_a_day_narrated_elsewhere_counts_as_narrated(root: Path, narrate: Counter) -> None:
    """A report pulled down from a teammate is prose in a file — carrying THEIR fingerprint,
    or none at all. Where it was written was never part of the question, and re-narrating it
    would burn a model call to overwrite work somebody else already paid for."""
    day = yesterday()
    log(root, day)
    path = report_path(root, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {day}\n\n{NARRATION}\n\nAna's machine wrote this.\n", encoding="utf-8")
    assert sweep(root)["narrated"] == []
    assert narrate.calls == []


@pytest.mark.usefixtures("narrate")
def test_a_hand_written_narration_is_never_replaced(root: Path) -> None:
    day = yesterday()
    log(root, day)
    sweep(root)
    edited = report_path(root, day).read_text(encoding="utf-8").replace(PROSE, "Ana's own words.")
    report_path(root, day).write_text(edited, encoding="utf-8")
    sweep(root)
    assert "Ana's own words." in report_path(root, day).read_text(encoding="utf-8")


def test_force_redoes_exactly_one_named_day(root: Path, narrate: Counter) -> None:
    day = yesterday()
    log(root, day, shift(day, days=-1))
    sweep(root)
    spent = len(narrate.calls)
    assert sweep(root, date=day, force=True)["narrated"] == [day]
    assert len(narrate.calls) == spent + 1


def test_force_without_a_date_is_refused(root: Path, narrate: Counter) -> None:
    """"Redo whatever you think is stale" over a fortnight of edited prose is not a command
    anybody means, and it cannot be undone once it has run."""
    log(root, yesterday())
    with pytest.raises(BadRequest) as raised:
        sweep(root, force=True)
    assert "--date" in str(raised.value)
    assert narrate.calls == []


def test_a_concurrent_run_is_reported_not_raised(root: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Two sweeps racing is a cron entry plus an impatient human. One narrates; the other says
    so and carries on — a traceback in a cron log is nobody's answer."""
    day = yesterday()
    log(root, day)
    monkeypatch.setattr(dossier, "narrate", Counter(AlreadyNarrating("busy")))
    done = sweep(root)
    assert done["narrated"] == []
    assert done["skipped"] == [{"label": day, "why": "another run is narrating it right now"}]


def test_a_failed_narration_does_not_abandon_the_rest(root: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    days = [shift(date_of(now()), days=-n) for n in (2, 1)]
    log(root, *days)
    monkeypatch.setattr(dossier, "narrate", Counter(NarrationFailed("claude is not logged in")))
    done = sweep(root)
    assert [row["label"] for row in done["skipped"]] == days
    assert "not logged in" in done["skipped"][0]["why"]


def test_the_limit_caps_the_run_and_says_it_did(root: Path, narrate: Counter) -> None:
    """A silent cap reads exactly like "everything is written up", which is the one thing it
    must never be mistaken for on a repository with a year of history."""
    days = [shift(date_of(now()), days=-n) for n in (3, 2, 1)]
    log(root, *days)
    done = sweep(root, limit=1)
    assert done["narrated"] == [days[0]]
    assert done["truncated"] == 2
    assert len(narrate.calls) == 1


@pytest.mark.usefixtures("narrate")
def test_a_project_with_no_remote_says_so_instead_of_failing(root: Path) -> None:
    log(root, yesterday())
    done = sweep(root, push=True)
    assert done["pushed"] == 0
    assert done["skipped"] == [{"label": "push", "why": "this project has no remote — run "
                                                        "`taskops remote add` or drop --push"}]


@pytest.mark.usefixtures("narrate")
def test_nothing_to_narrate_never_touches_the_wire(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A push is a round trip. A sweep that wrote nothing has nothing to send, and a cron job
    dialling a server every hour to say so is the cost this whole design exists to avoid."""
    # `sys.modules` and not `import taskops.usecases.sweep as module`: the package re-exports
    # the FUNCTION under the module's own name — as it does for `plan`, `update` and the rest —
    # so the dotted import binds the callable and patching it would silently do nothing.
    module = sys.modules["taskops.usecases.sweep"]

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("a sweep that narrated nothing must not push")

    monkeypatch.setattr(module, "push_remote", refuse)
    assert sweep(root, push=True)["pushed"] == 0
