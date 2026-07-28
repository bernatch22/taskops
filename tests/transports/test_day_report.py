"""`report day` on the two surfaces that serve it, and the two kinds that no longer exist.

The removal is worth a test of its own. `fleet` and `burndown` were advertised in the MCP
schema for months — one answering a question agents stopped having, the other replying with a
sentence saying it was not implemented — and a kind that disappears from the enum but still
falls through to the board would hand an agent a report about something else with no way to
tell.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from taskops.contracts.tools import ReportParams
from taskops.transports.cli.main import main
from taskops.transports.mcp import listing, respond
from taskops.usecases import init, plan


def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    reply = respond({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": arguments}})
    return reply["result"] if reply else {}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    init(repo, install_git_hooks=False)
    plan(repo, [{"title": "A day's work", "spec": "x"}], actor="dev:berna")
    return repo


def test_the_cli_prints_a_dossier_for_a_day(project: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    """Today, because a card was just planned into it — the header proves the window
    resolved rather than falling back to an empty report for some other date."""
    assert main(["report", "day", "--repo", str(project)]) == 0
    out = capsys.readouterr().out
    assert "closed" in out and "in flight" in out


def test_the_cli_refuses_a_date_it_cannot_read(project: Path,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    """Strict rather than defaulting to today: a dossier quietly covering the wrong day is
    worse than an error, because it looks right."""
    assert main(["report", "day", "--repo", str(project), "--date", "last tuesday"]) != 0
    assert "yesterday" in capsys.readouterr().err


def test_yesterday_is_a_date_the_cli_accepts(project: Path) -> None:
    assert main(["report", "day", "--repo", str(project), "--date", "yesterday"]) == 0


def test_the_mcp_serves_day_as_text(project: Path) -> None:
    result = call("taskops_report", {"repo_path": str(project), "kind": "day"})
    assert "# " in str(result["content"][0]["text"])


def test_the_report_schema_offers_exactly_four_kinds() -> None:
    """The enum IS the documentation an agent reads before it guesses a value."""
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_report")
    assert schema["properties"]["kind"]["enum"] == ["board", "standup", "day", "range"]
    assert "date" in schema["properties"]
    for field in ("last", "from_date", "to"):
        assert field in schema["properties"], f"kind=range cannot be aimed without {field}"
    assert "kind" not in ReportParams.__required_keys__


def test_a_removed_kind_is_refused_rather_than_silently_given_a_board(project: Path) -> None:
    """Falling through would answer a question nobody asked and call it success."""
    for gone in ("fleet", "burndown"):
        result = call("taskops_report", {"repo_path": str(project), "kind": gone})
        assert result.get("isError"), f"{gone} was answered instead of refused"
        assert "board" in str(result["content"][0]["text"])


# ---- a range, and the whole project


def test_the_cli_reports_a_range_and_labels_it_by_its_ends(project: Path,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    """The label is the heading AND the file name, so a report and its path cannot drift."""
    assert main(["report", "range", "--repo", str(project), "--last", "7d"]) == 0
    assert ".." in capsys.readouterr().out.splitlines()[0]


def test_report_all_covers_the_project_and_is_called_all(project: Path,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    """The answer to "si quiero evaluar todo, no solo un dia, como hago?" — one command,
    no dates to work out, and a file called `all.md` that stays the same file."""
    assert main(["report", "all", "--repo", str(project), "--write"]) == 0
    assert main(["report", "all", "--repo", str(project)]) == 0
    out = capsys.readouterr().out
    assert "reports/all.md" in out and "# all — " in out


def test_a_range_with_no_window_is_refused_rather_than_guessed(project: Path,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", "range", "--repo", str(project)]) != 0
    assert "--last" in capsys.readouterr().err


def test_a_span_the_cli_cannot_read_names_the_legal_forms(project: Path,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    """`--last 3fortnights` is refused, never silently widened to something plausible."""
    assert main(["report", "range", "--repo", str(project), "--last", "3fortnights"]) != 0
    assert "7d" in capsys.readouterr().err


def test_a_day_may_not_borrow_the_range_flags(project: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    """`report day --last 7d` means one of two things and the caller would not notice which
    one won — so neither does taskops."""
    assert main(["report", "day", "--repo", str(project), "--last", "7d"]) != 0
    assert "report range" in capsys.readouterr().err


def test_last_and_from_together_are_refused(project: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", "range", "--repo", str(project), "--last", "7d",
                 "--from", "2026-07-22"]) != 0
    assert "pick" in capsys.readouterr().err


def test_the_mcp_serves_a_range_and_defaults_it_to_everything(project: Path) -> None:
    """`kind=range` with no window is the WHOLE project: an agent asked to evaluate what was
    done here gets everything rather than an empty report for a window it failed to guess."""
    result = call("taskops_report", {"repo_path": str(project), "kind": "range"})
    assert "# all" in str(result["content"][0]["text"])
    aimed = call("taskops_report", {"repo_path": str(project), "kind": "range",
                                    "last": "7d"})
    assert ".." in str(aimed["content"][0]["text"])
