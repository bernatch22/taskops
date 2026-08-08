"""`taskops hook claude` — the delivery hook, run for real against a board.

Each test is one of the four properties the module's own docstring promises,
for each of the two things it delivers — a MENTION to anybody, and MERGE /
REVIEW / STALLED to a `dev:` only. The hook is driven in-process (stdin swapped,
stdout captured): the routing from `taskops.cli.main` is one `if` and the
properties live in `deliver()`.
"""

from __future__ import annotations

import io
import json
from typing import Any, Iterator
from pathlib import Path

import pytest

from taskops.cli import claude
from taskops.board import LocalBoard
from taskops._errors import Refused
from taskops.gitwork import install
from taskops.cli.claude import STAMP

pytestmark = pytest.mark.usefixtures("clock")


@pytest.fixture()
def board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LocalBoard]:
    """A repo with a board, one card assigned to w1, and a mention waiting for it."""
    monkeypatch.delenv("TASKOPS_ACTOR", raising=False)
    (tmp_path / ".taskops").mkdir()
    # What `init` writes: the board AND the address file that marks a project.
    (tmp_path / ".taskops" / "board.json").write_text("{}\n", encoding="utf-8")
    dev = LocalBoard(tmp_path / ".taskops" / "board", "dev:berna")
    dev.call("plan", {"milestone": "m", "goal": "g", "tasks": [{"title": "t", "spec": "s"}]})
    card = dev.call("board", {})["groups"]["take"][0]["id"]
    dev.call("assign", {"tasks": [card], "workers": ["w1"]})
    dev.call("update", {"task": card, "comment": "¿Decimal?", "mentions": ["agent:berna/w1"]})
    yield dev
    dev.close()


def fire(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    **payload: Any,
) -> str:
    body = {"hook_event_name": "PostToolUse", "cwd": str(repo), **payload}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(body)))
    assert claude.deliver(repo) == 0  # ALWAYS — this is the entire error policy
    return capsys.readouterr().out


def card_of(board: LocalBoard) -> str:
    groups: dict[str, list[dict[str, Any]]] = board.call("board", {})["groups"]
    return next(row["id"] for rows in groups.values() for row in rows)


def test_a_worker_named_only_by_its_worktree_path_gets_its_mention(
    tmp_path: Path, board: LocalBoard, capsys: Any, monkeypatch: Any
) -> None:
    """The chain that makes sub-agent delivery possible at all: the hook has no
    worker env, but the path names the card and the card names its owner."""
    card = card_of(board)
    tool = {"file_path": f"{tmp_path}/.taskops/trees/{card}/game.py"}
    out = json.loads(fire(tmp_path, capsys, monkeypatch, tool_input=tool))
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "agent:berna/w1" in context and card in context and "¿Decimal?" in context
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_answering_on_the_card_is_what_silences_the_hook(
    tmp_path: Path, board: LocalBoard, capsys: Any, monkeypatch: Any
) -> None:
    """No ack verb, no read flag: the reply IS the clearing."""
    card = card_of(board)
    w1 = LocalBoard(tmp_path / ".taskops" / "board", "agent:berna/w1")
    w1.call("update", {"task": card, "comment": "Decimal"})
    w1.close()
    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/w1")
    assert fire(tmp_path, capsys, monkeypatch) == ""


def test_the_second_look_inside_the_throttle_is_silent(
    tmp_path: Path, board: LocalBoard, capsys: Any, monkeypatch: Any, clock: Any
) -> None:
    """One look per reader per 30s — a round trip per Edit is v1's latency bug.
    The mention is still pending both times; only the SECOND look is spared."""
    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/w1")
    assert "✉" in fire(tmp_path, capsys, monkeypatch)
    clock(claude.THROTTLE - 1)
    assert fire(tmp_path, capsys, monkeypatch) == ""
    clock(2)  # past the window: due again, and the mention is still there
    assert "✉" in fire(tmp_path, capsys, monkeypatch)


def test_every_failure_is_silence_and_exit_zero(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    """A mention system that can break a turn is worse than no mention system."""
    assert fire(tmp_path, capsys, monkeypatch) == ""  # a repo with no board
    monkeypatch.setattr("sys.stdin", io.StringIO("this is not json"))
    assert claude.deliver(tmp_path) == 0
    assert capsys.readouterr().out == ""


def test_joining_twice_writes_the_delivery_hook_once_and_keeps_foreign_ones(
    tmp_path: Path,
) -> None:
    """Same non-clobbering contract as `write_mcp`: the settings file is the
    user's, and the only thing we recognise as ours is our own command string."""
    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir()
    theirs = {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}
    path.write_text(json.dumps(theirs), encoding="utf-8")
    assert install.write_claude_hooks(tmp_path, "py") == ["PostToolUse", "UserPromptSubmit"]
    assert install.write_claude_hooks(tmp_path, "py") == []  # a no-op, not a duplicate
    settings = json.loads(path.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entries in settings["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    assert commands.count("mine.sh") == 1 and commands.count(install.claude_command("py")) == 2

    # ...and re-joining from a DIFFERENT interpreter REPLACES ours, never adds a
    # second: the real repo had one entry per python and the hook fired twice
    # per tool call. Ours is recognised by the module, not by the whole command.
    assert install.write_claude_hooks(tmp_path, "/other/python") == []
    settings = json.loads(path.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entries in settings["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    assert commands.count(install.claude_command("py")) == 0
    assert commands.count(install.claude_command("/other/python")) == 2
    assert commands.count("mine.sh") == 1  # somebody else's is still untouched


def test_the_mentions_read_renews_nothing(
    tmp_path: Path, board: LocalBoard, clock: Any
) -> None:
    """The hook fires on tool calls the reader did not make, so its read must
    not be a heartbeat: renewing here would keep a dead worker's card out of
    STALLED forever — a stored `doing` grown back by the side door."""
    card = card_of(board)
    w1 = LocalBoard(tmp_path / ".taskops" / "board", "agent:berna/w1")
    w1.call("take", {"task": card})
    lease = w1.stores.live.lease(card, 0)
    assert lease is not None
    clock(10)  # a renewal would now move `expires`; a frozen clock would hide it
    w1.call("mentions", {})
    after = w1.stores.live.lease(card, 0)
    assert after is not None and after["expires"] == lease["expires"]
    w1.close()


def test_the_orchestrator_is_told_the_three_groups_it_is_sitting_on(
    tmp_path: Path, board: LocalBoard, capsys: Any, monkeypatch: Any
) -> None:
    """The incident this half exists for: two cards dispatched, no worker ever
    spawned, twelve minutes of `stalled` nobody read. One line per group, in the
    board's own ranking (merge · review · stalled), each with the count and the
    call that clears it — a reader must not have to open anything to act."""
    dev, other = board, tmp_path / ".taskops" / "board"
    stalled = card_of(board)  # the fixture's: assigned to w1, never taken
    dev.call("plan", {"tasks": [{"title": "a", "spec": "s"}, {"title": "b", "spec": "s"}]})
    ready = [row["id"] for row in dev.call("board", {})["groups"]["take"]]
    dev.call("update", {"task": ready[1], "review": True})
    w2 = LocalBoard(other, "agent:berna/w2")
    w2.call("take", {"task": ready[0]})
    w2.call(
        "update",
        {"task": ready[0], "status": "done", "no_code": True, "comment": "c", "note": "n"},
    )
    w2.call("take", {"task": ready[1]})
    w2.call("update", {"task": ready[1], "status": "review", "comment": "c", "note": "n"})
    w2.close()

    out = json.loads(fire(tmp_path, capsys, monkeypatch))["hookSpecificOutput"]
    lines = out["additionalContext"].splitlines()
    assert [line.split(" — ")[0] for line in lines] == [
        "◆ taskops: 1 done, not in the trunk",
        "◆ taskops: 1 handed in, nobody checking",
        "◆ taskops: 1 owned, nobody running them",
    ]
    assert "one taskops_merge task= each: " + ready[0] in lines[0]
    assert "taskops_review task=): " + ready[1] in lines[1]
    assert "taskops_assign tasks=[…]" in lines[2] and stalled in lines[2]


def test_a_worker_is_told_nothing_about_the_orchestrators_groups(
    tmp_path: Path, board: LocalBoard, capsys: Any, monkeypatch: Any
) -> None:
    """A worker neither merges nor dispatches, so these are noise it cannot act
    on — and noise is how a hook gets deleted. Its ✉ still arrives."""
    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/w1")
    delivered = fire(tmp_path, capsys, monkeypatch)
    assert "✉" in delivered and "◆" not in delivered


def test_the_two_halves_are_throttled_apart(
    tmp_path: Path, board: LocalBoard, capsys: Any, monkeypatch: Any, clock: Any
) -> None:
    """A stalled card is not urgent within a turn the way a mention is, so the
    orchestrator's groups have their own, longer interval AND their own key in
    the stamp: repeating them every 30s is what would make this noise."""
    assert "◆" in fire(tmp_path, capsys, monkeypatch)
    clock(claude.THROTTLE + 1)  # the ✉ half is due again; this half is not
    assert fire(tmp_path, capsys, monkeypatch) == ""
    clock(claude.WAITING)
    assert "◆" in fire(tmp_path, capsys, monkeypatch)


def test_the_waiting_read_renews_nothing(
    tmp_path: Path, board: LocalBoard, clock: Any
) -> None:
    """Same property as `mentions`, and the same reason: the hook reads on a
    tool call the holder did not make. Renewing here — or stamping presence —
    would keep a dead worker's card out of STALLED forever."""
    card = card_of(board)
    w1 = LocalBoard(tmp_path / ".taskops" / "board", "agent:berna/w1")
    w1.call("take", {"task": card})
    lease = w1.stores.live.lease(card, 0)
    assert lease is not None
    clock(10)  # a renewal would now move `expires`; a frozen clock would hide it
    seen = dict(board.stores.live.present(0))
    board.call("waiting", {})
    after = w1.stores.live.lease(card, 0)
    assert after is not None and after["expires"] == lease["expires"]
    assert dict(board.stores.live.present(0)) == seen
    w1.close()


def test_a_worker_may_not_ask_what_the_orchestrator_is_sitting_on(
    tmp_path: Path, board: LocalBoard
) -> None:
    """The role gate is the verb's, not the hook's — the hook merely does not
    ask. A refusal names the call that works."""
    w1 = LocalBoard(tmp_path / ".taskops" / "board", "agent:berna/w1")
    with pytest.raises(Refused, match="taskops_board"):
        w1.call("waiting", {})
    w1.close()


def test_the_hook_never_creates_a_board_where_there_is_none(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    """A read that writes is not a read. `Stores` makes its directories on
    open, so the guard has to be "is there a board", not "is there a folder
    called .taskops" — v1 left one of those in every HOME it ever ran in, and
    the hook quietly built a board inside it."""
    (tmp_path / ".taskops").mkdir()
    (tmp_path / ".taskops" / "sessions.json").write_text("{}", encoding="utf-8")
    assert fire(tmp_path, capsys, monkeypatch) == ""
    assert not (tmp_path / ".taskops" / "board").exists()
    assert not (tmp_path / ".taskops" / STAMP).exists()  # not even the throttle stamp
