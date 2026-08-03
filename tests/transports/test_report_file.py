"""`report day --write` — the dossier as a file, and the fingerprint that keeps it honest.

The written report is the one artifact taskops produces that is NOT regenerated on demand, so
every test here is about that difference: it must refuse to overwrite itself, it must say when
the day outran it, and `init` must leave it tracked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskops._errors import AlreadyWritten
from taskops.render import NARRATION, PENDING
from taskops.transports.cli.main import main
from taskops.transports.http._wire import Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import board as ask_board
from taskops.usecases import init, plan, read_report, report_path, update, write_report
from taskops.usecases._ignorerules import BOARD_NOTE, REPORTS_NOTE


@pytest.fixture
def project(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    init(repo, install_git_hooks=False)
    plan(repo, [{"title": "A day's work", "spec": "x"}], actor="dev:berna")
    return repo


def _first_task(repo: Path) -> str:
    """The card the fixture planned. Read back rather than remembered, so a test that adds a
    second card still talks about the one it means."""
    cards = [c for column in ask_board(repo)["columns"] for c in column["cards"]]
    return str(cards[0]["task"]["id"])


def written(repo: Path, date: str) -> str:
    return report_path(repo, date).read_text(encoding="utf-8")


def today_of(repo: Path) -> str:
    return read_report(repo)["date"]


# ---- writing


def test_the_file_lands_under_the_project_and_carries_a_fingerprint(project: Path) -> None:
    """The header is what every staleness answer later is computed from — without it the
    file is prose, and nothing can tell a complete report from a report of half a day."""
    path = write_report(project)
    date = today_of(project)
    assert path == project / ".taskops" / "reports" / f"{date}.md"
    first = written(project, date).splitlines()[0]
    assert first.startswith(f"<!-- taskops:report date={date} max_seq=")
    assert "generated=" in first and first.endswith("-->")


def test_the_fingerprint_records_the_log_position_not_zero(project: Path) -> None:
    """A stamp of 0 on a project with events would make every report permanently stale."""
    write_report(project)
    line = written(project, today_of(project)).splitlines()[0]
    seq = int(line.split("max_seq=")[1].split()[0])
    assert seq > 0


def test_the_report_carries_the_dossier_and_an_empty_narration(project: Path) -> None:
    write_report(project)
    text = written(project, today_of(project))
    assert "closed" in text and "in flight" in text
    assert text.rstrip().endswith(PENDING)
    assert text.index(NARRATION) > text.index("# ")


def test_writing_twice_is_refused(project: Path) -> None:
    """The file may already carry a narration nobody can regenerate."""
    write_report(project)
    with pytest.raises(AlreadyWritten):
        write_report(project)


def test_force_regenerates_and_says_nothing_quietly(project: Path) -> None:
    date = today_of(project)
    write_report(project)
    report_path(project, date).write_text("narrated by hand\n", encoding="utf-8")
    write_report(project, force=True)
    assert "narrated by hand" not in written(project, date)


# ---- the CLI


def test_the_cli_writes_and_prints_the_path(project: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    """The path and not the dossier: what the caller does next is read or commit that file."""
    assert main(["report", "day", "--repo", str(project), "--write"]) == 0
    out = capsys.readouterr().out
    assert "wrote " in out and ".taskops/reports/" in out
    assert report_path(project, today_of(project)).is_file()


def test_the_cli_refuses_a_second_write_without_force(project: Path,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    main(["report", "day", "--repo", str(project), "--write"])
    capsys.readouterr()
    assert main(["report", "day", "--repo", str(project), "--write"]) != 0
    assert "--force" in capsys.readouterr().err


def test_the_cli_accepts_force(project: Path) -> None:
    main(["report", "day", "--repo", str(project), "--write"])
    assert main(["report", "day", "--repo", str(project), "--write", "--force"]) == 0


def test_write_is_refused_on_a_report_that_is_not_a_day(project: Path,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    """Silently ignoring the flag would print a standup and let the caller believe it saved
    one — every other report is a moving window and cannot be filed under a date."""
    assert main(["report", "standup", "--repo", str(project), "--write"]) != 0
    assert "report day" in capsys.readouterr().err


def test_printing_a_day_still_does_not_write_anything(project: Path) -> None:
    assert main(["report", "day", "--repo", str(project)]) == 0
    assert not (project / ".taskops" / "reports").exists()


# ---- reading, and staleness


def test_a_day_nobody_wrote_up_still_answers_with_a_dossier(project: Path) -> None:
    """A reader never gets an empty screen and a button as the only content."""
    answer = read_report(project)
    assert answer["exists"] is False and answer["stale"] is False
    assert answer["missing_events"] == 0
    assert "# " in answer["dossier_md"]


def test_a_fresh_report_is_not_stale(project: Path) -> None:
    write_report(project)
    answer = read_report(project)
    assert answer["exists"] is True and answer["stale"] is False


def test_an_event_inside_the_day_makes_the_report_stale(project: Path) -> None:
    write_report(project)
    task = read_report(project)  # the date, resolved the same way everywhere
    update(project, _first_task(project), comment="something happened after", actor="dev:berna")
    answer = read_report(project, task["date"])
    assert answer["stale"] is True and answer["missing_events"] >= 1


def test_a_hand_written_report_is_never_called_stale(project: Path) -> None:
    """No fingerprint means staleness is UNKNOWN, and nagging about a file taskops did not
    write is noise nobody can act on."""
    date = today_of(project)
    path = report_path(project, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 2026-07-27\n\nWritten by a person.\n", encoding="utf-8")
    answer = read_report(project, date)
    assert answer["exists"] is True and answer["stale"] is False


def test_the_written_narration_survives_a_read(project: Path) -> None:
    """`dossier_md` is the FILE when there is one — regenerating it here would silently drop
    the paragraph a human wrote, which is the whole reason the file is committed."""
    date = today_of(project)
    write_report(project)
    path = report_path(project, date)
    path.write_text(path.read_text(encoding="utf-8").replace(PENDING, "Un día tranquilo."),
                    encoding="utf-8")
    assert "Un día tranquilo." in read_report(project, date)["dossier_md"]


# ---- the HTTP endpoint


def test_the_endpoint_serves_the_shape_the_ui_expects(project: Path) -> None:
    route = build(project, Policy())
    reply = route(Request(method="GET", path="/api/report", query={}, headers={}))
    payload = json.loads(reply.body)
    assert set(payload) == {"date", "path", "dossier_md", "exists", "stale", "missing_events"}


def test_the_endpoint_reports_stale_after_an_event_lands(project: Path) -> None:
    import json

    write_report(project)
    update(project, _first_task(project), comment="later that day", actor="dev:berna")
    route = build(project, Policy())
    reply = route(Request(method="GET", path="/api/report", query={}, headers={}))
    payload = json.loads(reply.body)
    assert payload["exists"] is True and payload["stale"] is True


def test_the_endpoint_refuses_a_date_it_cannot_read(project: Path) -> None:
    route = build(project, Policy())
    reply = route(Request(method="GET", path="/api/report",
                          query={"date": "last tuesday"}, headers={}))
    assert reply.status == 400


# ---- init


def test_init_does_not_gitignore_the_reports(project: Path) -> None:
    """The reports are committed: that is what makes yesterday's report still true tomorrow."""
    ignored = (project / ".gitignore").read_text(encoding="utf-8")
    assert "reports/" in ignored  # only ever as the comment saying they are committed
    for line in ignored.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert "reports" not in stripped, f"{stripped!r} would untrack the reports"


def test_init_is_idempotent_about_the_notes(project: Path) -> None:
    """Every explaining COMMENT appears exactly once, however many times init runs.

    Counted per note rather than by the shared phrase `is COMMITTED`, which is what this
    asserted while there was only one of them. A second note made that count read 2 and say
    nothing — a duplicated `reports/` line and a correctly-written `board.json` one are
    indistinguishable to it, and the duplicate is the failure this exists to catch.
    """
    init(project, install_git_hooks=False)
    init(project, install_git_hooks=False)
    ignored = (project / ".gitignore").read_text(encoding="utf-8")

    for note in (REPORTS_NOTE, BOARD_NOTE):
        assert ignored.count(note) == 1, f"{note!r} appears {ignored.count(note)} times"


def test_an_older_project_gains_the_note_on_re_init(tmp_path: Path) -> None:
    """A `.gitignore` written before reports existed carries the marker, so the block is not
    rewritten — the note has to be appended, or the next tidy-up untracks every report."""
    repo = tmp_path / "old"
    repo.mkdir()
    (repo / ".gitignore").write_text("# taskops\n.taskops/db.sqlite\n", encoding="utf-8")
    init(repo, install_git_hooks=False)
    assert "is COMMITTED" in (repo / ".gitignore").read_text(encoding="utf-8")
