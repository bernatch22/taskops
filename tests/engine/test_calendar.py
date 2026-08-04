"""Whose midnight a dossier is cut at — the machine's, or the project's.

The incident these pin, from the axion board. 2026-07-30 exists in two generations of the same
file: one written on a machine at UTC-3 counting 8 commits, one written two days later at UTC+2
counting 5, with the other three inside 07-31. Nothing was lost and nothing agreed either, and
because a dossier is a committed FILE the second one replaced the first with no conflict to see.
`max_seq` could not settle it: the poorer copy had the higher seq, because it was generated over
more of the log and over a different window.

So the window is the project's decision (`policy day_zone`), the offset it produced is written
into the stamp, and two copies cut at different offsets refuse to overwrite each other.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import pytest

from taskops._errors import BadRequest
from taskops.contracts.policy import POLICY_KIND, POLICY_TASK
from taskops.engine import record
from taskops.engine.calendar import date_of, day_zone, offset_of, window
from taskops.engine.day import day_report
from taskops.engine.reports import stamp, stamp_for, stamped_offset
from taskops.storage import Store

DATE = "2026-07-30"

MADRID, BUENOS_AIRES = "Europe/Madrid", "America/Argentina/Buenos_Aires"


@pytest.fixture
def in_buenos_aires() -> Iterator[None]:
    """The MACHINE moved, not the project. `tzset` is what makes the process actually believe
    it, and the fixture puts the old zone back so the rest of the suite is unaffected."""
    was = os.environ.get("TZ")
    os.environ["TZ"] = BUENOS_AIRES
    time.tzset()
    yield
    if was is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = was
    time.tzset()


def _zoned(store: Store, zone: str) -> None:
    record(store, task=POLICY_TASK, actor="dev:berna", kind=POLICY_KIND,
           body={"name": "day_zone", "value": zone})


@pytest.mark.usefixtures("in_buenos_aires")
def test_a_named_zone_cuts_the_same_interval_whatever_the_machine_thinks() -> None:
    """The property the whole fix rests on: with a zone named, the window is a fact about the
    project. Without one it is a fact about whoever typed the command."""
    theirs = window(DATE, MADRID)
    del os.environ["TZ"]
    time.tzset()
    assert window(DATE, MADRID) == theirs


def test_the_machine_s_own_zone_is_still_the_default() -> None:
    """Every project that has decided nothing keeps the behaviour it had, byte for byte."""
    start, end = window(DATE)
    assert start == time.mktime((2026, 7, 30, 0, 0, 0, 0, 0, -1))
    assert (end - start) in (82_800.0, 86_400.0, 90_000.0)


def test_the_two_zones_disagree_about_which_day_an_evening_event_belongs_to() -> None:
    """The shape of the three commits that moved: 2026-07-30 22:07 UTC was still the 30th in
    Buenos Aires and already the 31st in Madrid. Below, 23:50 Madrid is the 30th in both, and one
    hour later the two zones disagree. The point is not which is right — it is that they differ
    and only one of them can be the file called `2026-07-30.md`."""
    evening = window("2026-07-31", MADRID)[0] - 600.0            # 23:50 in Madrid
    assert date_of(evening, MADRID) == "2026-07-30"
    assert date_of(evening, BUENOS_AIRES) == "2026-07-30"
    assert date_of(evening + 3_600.0, MADRID) == "2026-07-31"
    assert date_of(evening + 3_600.0, BUENOS_AIRES) == "2026-07-30"


def test_the_project_s_zone_decides_which_day_an_event_is_reported_on(store: Store) -> None:
    """The reproduction, in one assertion: the same event, two policies, two days."""
    late = window("2026-07-31", MADRID)[0] - 600.0               # 23:50 Madrid, 18:50 in ART
    record(store, task="tk-1", actor="dev:berna", kind="commit", ts=late,
           body={"sha": "a" * 40, "subject": "late", "files": ["src/x.py"]})

    _zoned(store, MADRID)
    assert day_report(store, "2026-07-30")["commits_total"] == 1
    assert day_report(store, "2026-07-31")["commits_total"] == 0

    _zoned(store, BUENOS_AIRES)
    assert day_report(store, "2026-07-30")["commits_total"] == 1
    assert day_report(store, "2026-07-31")["commits_total"] == 0

    # And an event three hours later belongs to two different days:
    record(store, task="tk-1", actor="dev:berna", kind="commit", ts=late + 10_800.0,
           body={"sha": "b" * 40, "subject": "after midnight in Madrid", "files": ["src/x.py"]})
    assert day_report(store, "2026-07-30")["commits_total"] == 2, "still the 30th in Argentina"
    _zoned(store, MADRID)
    assert day_report(store, "2026-07-30")["commits_total"] == 1
    assert day_report(store, "2026-07-31")["commits_total"] == 1


def test_no_event_is_counted_twice_or_dropped_whichever_zone_is_chosen(store: Store) -> None:
    """What "nothing was lost" means, made checkable: the two days PARTITION the events, so the
    pair of reports always accounts for every one of them exactly once."""
    midnight = window("2026-07-31", MADRID)[0]
    for hour in range(-6, 6):
        record(store, task="tk-1", actor="dev:berna", kind="commit", ts=midnight + hour * 3600.0,
               body={"sha": f"{hour:040d}", "subject": "x", "files": ["src/x.py"]})
    for zone in (MADRID, BUENOS_AIRES):
        _zoned(store, zone)
        both = sum(day_report(store, date)["commits_total"]
                   for date in ("2026-07-30", "2026-07-31"))
        assert both == 12, f"{zone} lost or duplicated one"


def test_the_stamp_records_the_offset_the_window_was_cut_at(store: Store) -> None:
    """A window nobody can name is a window a reader cannot check — and it is the field the
    push rule needs to see that two copies are not versions of one document."""
    _zoned(store, MADRID)
    assert stamped_offset(stamp_for(store, DATE, DATE, 0.0)) == "+0200"
    _zoned(store, BUENOS_AIRES)
    assert stamped_offset(stamp_for(store, DATE, DATE, 0.0)) == "-0300"


def test_the_offset_is_the_WINDOW_s_and_not_the_moment_of_generation(store: Store) -> None:
    """A January day regenerated in July is still a January day. Stamping today's offset would
    make two copies of one window look like different windows."""
    _zoned(store, MADRID)
    assert stamped_offset(stamp_for(store, "2026-01-15", "2026-01-15", 0.0)) == "+0100"
    assert stamped_offset(stamp_for(store, "2026-07-15", "2026-07-15", 0.0)) == "+0200"


def test_a_report_written_before_the_offset_existed_reads_as_UNKNOWN() -> None:
    """Never as ours. Every dossier in every repository predates this field: reading their
    silence as agreement would resurrect the overwrite, reading it as disagreement would make
    them all unpushable."""
    assert stamped_offset(stamp(DATE, 450, 0.0)) == ""
    assert stamped_offset("# 2026-07-30\n\nWritten by a person.\n") == ""


def test_a_zone_the_machine_does_not_know_is_refused_and_not_silently_local(store: Store) -> None:
    """It reached the log from a newer taskops or a thinner tz database. Falling back to local
    would be the original bug wearing the fix's clothes."""
    _zoned(store, "Mars/Olympus_Mons")
    assert day_zone(store) == "Mars/Olympus_Mons"
    with pytest.raises(BadRequest) as raised:
        window(DATE, day_zone(store))
    assert "day_zone" in str(raised.value)


@pytest.mark.usefixtures("in_buenos_aires")
def test_the_offset_of_a_moment_with_no_zone_is_the_machine_s() -> None:
    assert offset_of(window(DATE)[0]) == "-0300"
