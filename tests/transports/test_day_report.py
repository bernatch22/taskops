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


def test_the_report_schema_offers_exactly_three_kinds() -> None:
    """The enum IS the documentation an agent reads before it guesses a value."""
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_report")
    assert schema["properties"]["kind"]["enum"] == ["board", "standup", "day"]
    assert "date" in schema["properties"]
    assert "kind" not in ReportParams.__required_keys__


def test_a_removed_kind_is_refused_rather_than_silently_given_a_board(project: Path) -> None:
    """Falling through would answer a question nobody asked and call it success."""
    for gone in ("fleet", "burndown"):
        result = call("taskops_report", {"repo_path": str(project), "kind": gone})
        assert result.get("isError"), f"{gone} was answered instead of refused"
        assert "board" in str(result["content"][0]["text"])
