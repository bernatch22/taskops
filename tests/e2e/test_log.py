"""Reading an agent's conversation back from a card.

Every fact these tests assert was verified against a REAL transcript first — a dispatched worker's
198 KB session in axion-v3 — and the synthetic fixtures here reproduce the shapes that file actually
contained, including the two that were surprising:

- **`$CLAUDE_CONFIG_DIR`.** The machine this was built on has TWO Claude Code homes, and the active one
  is `~/.claude-jp`. Reading a hardcoded `~/.claude` found a different installation and reported that
  the workers had left no transcript at all. They had.
- **Redacted thinking.** A `thinking` block keeps its `signature` and carries an EMPTY `thinking`
  string, so rendering it produced a blank line before every assistant turn — half the log saying
  nothing, and looking like a failure to read rather than nothing to read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taskops.engine.transcript import ENV_HOME, slug_for
from taskops.engine.worker import worktree_for
from taskops.usecases import init, plan, session_log


def entry(kind: str, content: Any, *, branch: str = "", when: str = "2026-07-27T19:00:00Z",
          session: str = "sess-1") -> str:
    """One raw transcript line, in the shape Claude Code writes."""
    payload: dict[str, Any] = {"type": kind, "sessionId": session, "timestamp": when,
                               "gitBranch": branch,
                               "message": {"role": kind, "content": content}}
    return json.dumps(payload)


def write_transcript(home: Path, cwd: Path, lines: list[str], name: str = "s1.jsonl") -> Path:
    """Put a transcript where Claude Code would have put it for a session run in `cwd`."""
    directory = home / "projects" / slug_for(cwd)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv(ENV_HOME, str(tmp_path / "claude-home"))
    init(repo, install_git_hooks=False)
    plan(repo, [{"title": "Watched work", "spec": "x"}], actor="dev:berna")
    return repo


def only_task(project: Path) -> str:
    from taskops.usecases import board

    return next(c["task"]["id"] for column in board(project)["columns"]
                for c in column["cards"])


def test_the_config_dir_env_var_decides_where_to_look(project: Path,
                                                      tmp_path: Path) -> None:
    """THE bug that made the first version find nothing: two Claude Code homes on one machine, and
    the active one is not `~/.claude`."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree,
                     [entry("user", "do the thing")])

    log = session_log(project, task)
    assert [e["text"] for e in log["entries"]] == ["do the thing"]


def test_a_worktree_transcript_is_found_without_any_bookkeeping(project: Path,
                                                               tmp_path: Path) -> None:
    """No session id is stored anywhere: `dispatch` puts each worker in a per-card directory, and
    Claude Code names its transcript directory after the working directory. So the lookup is a path
    computation — which is why it worked on transcripts written before taskops could read them."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree, [
        entry("user", "the brief"),
        entry("assistant", [{"type": "text", "text": "on it"}]),
    ])

    log = session_log(project, task)
    assert [e["kind"] for e in log["entries"]] == ["prompt", "text"]
    assert log["sessions"] == ["sess-1"]


def test_redacted_thinking_is_dropped_not_rendered_blank(project: Path,
                                                         tmp_path: Path) -> None:
    """Extended thinking is REDACTED in the transcript: the block keeps a `signature` and its
    `thinking` is the empty string. Rendering it put a blank line before every assistant turn."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree, [
        entry("assistant", [{"type": "thinking", "thinking": "", "signature": "abc"},
                            {"type": "text", "text": "the answer"}]),
    ])

    log = session_log(project, task)
    assert [e["kind"] for e in log["entries"]] == ["text"]


def test_thinking_that_IS_present_survives(project: Path, tmp_path: Path) -> None:
    """The rule is "empty", not "thinking" — a model that does return its reasoning must be shown."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree, [
        entry("assistant", [{"type": "thinking", "thinking": "weighing two options"}]),
    ])

    assert session_log(project, task)["entries"][0]["kind"] == "thinking"


def test_a_tool_call_is_one_line_naming_what_it_touched(project: Path,
                                                        tmp_path: Path) -> None:
    """A dashboard printing the full `input` of every Edit is one nobody scrolls — the diff is in git,
    and what a reader wants is which file."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree, [
        entry("assistant", [{"type": "tool_use", "name": "Edit",
                             "input": {"file_path": "/x/parser.py",
                                       "old_string": "a" * 5000, "new_string": "b" * 5000}}]),
    ])

    found = session_log(project, task)["entries"][0]
    assert found["kind"] == "tool" and found["tool"] == "Edit"
    assert found["text"] == "/x/parser.py"
    assert "aaaa" not in found["text"], "the payload leaked into the summary"


def test_claude_codes_own_bookkeeping_is_skipped(project: Path, tmp_path: Path) -> None:
    """Mode switches, generated titles and undo snapshots were a THIRD of a real 1018-line
    transcript. Keeping them buries the entries a person wants."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree, [
        entry("mode", "plan"), entry("ai-title", "Some title"),
        entry("file-history-snapshot", "…"), entry("user", "the real prompt"),
    ])

    assert [e["text"] for e in session_log(project, task)["entries"]] == ["the real prompt"]


def test_the_repository_directory_is_filtered_by_branch(project: Path,
                                                        tmp_path: Path) -> None:
    """The project's own transcript directory is shared by every session anybody ran there, so an
    entry has to prove it belongs to this card — which `gitBranch` does, on every line."""
    task = only_task(project)
    from taskops.engine import branch_for

    branch = branch_for({"id": task, "title": "Watched work"})   # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", project, [
        entry("user", "mine", branch=branch),
        entry("user", "somebody else's", branch="main"),
    ])

    assert [e["text"] for e in session_log(project, task)["entries"]] == ["mine"]


def test_truncation_keeps_the_END_and_says_so(project: Path, tmp_path: Path) -> None:
    """A person opening a card's log is usually asking how it WENT, and the answer is in the last
    turns. Silence about the cut would be a lie about the ending."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    write_transcript(tmp_path / "claude-home", tree,
                     [entry("user", f"turn {i}", when=f"2026-07-27T19:{i:02d}:00Z")
                      for i in range(30)])

    log = session_log(project, task, limit=5)
    assert log["truncated"] is True
    assert [e["text"] for e in log["entries"]] == [f"turn {i}" for i in range(25, 30)]


def test_no_transcript_says_where_it_looked(project: Path) -> None:
    """An empty pane cannot distinguish "the agent said nothing" from "taskops looked in the wrong
    place" — and the second has a fix, which is usually the config dir."""
    from taskops.render import render_log

    log = session_log(project, only_task(project))
    assert log["entries"] == []
    text = render_log(log)
    assert "no conversation found" in text
    assert ENV_HOME in text, "the reply must name what to check"


def test_a_malformed_line_does_not_lose_the_conversation(project: Path,
                                                         tmp_path: Path) -> None:
    """The file is written by whatever Claude Code version is installed, and the format is not
    documented as stable."""
    task = only_task(project)
    tree = worktree_for(project, {"id": task})       # type: ignore[arg-type]
    directory = tmp_path / "claude-home" / "projects" / slug_for(tree)
    directory.mkdir(parents=True)
    (directory / "s1.jsonl").write_text(
        "{not json at all\n" + entry("user", "still here") + "\n", encoding="utf-8")

    assert [e["text"] for e in session_log(project, task)["entries"]] == ["still here"]


def test_an_interactive_card_is_found_by_its_RECORDED_session(project: Path,
                                                             tmp_path: Path) -> None:
    """The branch filter alone loses the most ordinary case there is.

    A person who claims a card in their own terminal usually never leaves `main`, so every entry they
    produce fails the `gitBranch` test and the pane comes up empty — which is exactly how this was
    reported. The card therefore remembers WHICH sessions worked it: the PostToolUse hook stamps the
    session id onto the lease on every tool call, and a transcript named by a recorded id is read whole,
    whatever branch it was on.
    """
    from taskops.usecases import next_task, track

    task = next_task(project, actor="dev:berna")["claim"]["view"]["task"]["id"]   # type: ignore[index]
    track(project, summary="Edit parser.py", actor="dev:berna", session="sess-int")
    write_transcript(tmp_path / "claude-home", project,
                     [entry("user", "worked on main", branch="main", session="sess-int")],
                     name="sess-int.jsonl")

    assert [e["text"] for e in session_log(project, task)["entries"]] == ["worked on main"]


def test_a_found_but_empty_directory_says_WHICH_kind_of_nothing_it_is(project: Path,
                                                                     tmp_path: Path) -> None:
    """"No conversation found" plus a path reads as a broken viewer, and was reported as one.

    Two different situations end up here and only one of them is a problem: nobody ever worked this card
    in a session (nothing to show, and completely normal for a card still in `ready`), versus somebody
    did and the entries cannot be attributed. The reader can act on the second and should not go looking
    for a fix to the first.
    """
    task = only_task(project)
    write_transcript(tmp_path / "claude-home", project,
                     [entry("user", "another card's work", branch="main")])

    assert "no Claude Code session is recorded" in session_log(project, task)["source"]
