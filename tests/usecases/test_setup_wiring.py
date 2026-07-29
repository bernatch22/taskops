"""Wiring a machine: the project's `.mcp.json`, and the one block taskops owns in a shell rc.

Both halves have already failed in production, in different ways, and the tests are shaped by
those failures rather than by the happy path:

- `.mcp.json` said `python3`, which is not the interpreter that has taskops importable on any
  pipx, uv or pyenv machine. The MCP server never started, so a spawned specialist held Read
  and Bash and could not claim the card it had just been handed.
- the shell half has not failed yet because it did not exist — which is exactly when to write
  the tests that keep it from ever appending a second stanza to somebody's `~/.zshrc`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from taskops.usecases.mcpfile import MCP_FILE, wire_mcp
from taskops.usecases.shellrc import (
    CLOSE,
    OPEN,
    alias_line,
    block,
    install_alias,
    rc_path,
    remove_alias,
)


def test_the_mcp_entry_names_an_interpreter_that_has_taskops(tmp_path: Path) -> None:
    """`python3` is whatever is first on PATH; `sys.executable` is the one importing this line,
    which by definition can import the package it is being asked to run."""
    wire_mcp(tmp_path)
    written = json.loads((tmp_path / MCP_FILE).read_text(encoding="utf-8"))
    assert written["mcpServers"]["taskops"]["command"] == sys.executable
    assert written["mcpServers"]["taskops"]["command"] != "python3"


def test_an_existing_mcp_file_is_merged_and_never_replaced(tmp_path: Path) -> None:
    """A repository's `.mcp.json` is shared config — somebody else's server lives there — and a
    tool that rewrote the file would delete a teammate's work to add its own."""
    (tmp_path / MCP_FILE).write_text(
        json.dumps({"mcpServers": {"theirs": {"command": "node", "args": ["x.js"]}}}),
        encoding="utf-8")

    wire_mcp(tmp_path)

    written = json.loads((tmp_path / MCP_FILE).read_text(encoding="utf-8"))
    assert written["mcpServers"]["theirs"] == {"command": "node", "args": ["x.js"]}
    assert "taskops" in written["mcpServers"]


def test_an_entry_somebody_wrote_deliberately_is_left_alone(tmp_path: Path) -> None:
    """Only ADDS. A `taskops` entry pointing somewhere on purpose — a different checkout, a
    wrapper — must survive a re-run, or the tool overrules the person every time they init."""
    theirs = {"command": "/opt/theirs/python", "args": ["-m", "taskops.transports.mcp"]}
    (tmp_path / MCP_FILE).write_text(json.dumps({"mcpServers": {"taskops": theirs}}),
                                     encoding="utf-8")

    assert "taskops" not in wire_mcp(tmp_path)
    written = json.loads((tmp_path / MCP_FILE).read_text(encoding="utf-8"))
    assert written["mcpServers"]["taskops"] == theirs


def test_unreadable_json_is_refused_rather_than_truncated(tmp_path: Path) -> None:
    """A hand-edited file with a missing comma is somebody's work in progress. Overwriting it
    to add our two entries would be the worst possible reading of "wire the project"."""
    (tmp_path / MCP_FILE).write_text('{"mcpServers": {', encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        wire_mcp(tmp_path)


# ---- the shell rc


def test_each_shell_is_pointed_at_the_file_it_actually_reads(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """bash on macOS is the case worth pinning: Terminal.app starts LOGIN shells, which read
    `.bash_profile` and never `.bashrc` — the commonest reason an alias "did not work"."""
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    monkeypatch.delenv("ZDOTDIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert rc_path("/bin/zsh") == tmp_path / ".zshrc"
    assert rc_path("/usr/local/bin/fish") == tmp_path / ".config" / "fish" / "config.fish"

    (tmp_path / ".bash_profile").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert rc_path("/bin/bash") == tmp_path / ".bash_profile"


def test_fish_gets_fish_syntax() -> None:
    """`alias name='...'` is a POSIX line. In `config.fish` it fails at every new terminal,
    with an error most people blame on the last thing they installed."""
    assert "=" not in alias_line("tk", "claude", shell="/usr/local/bin/fish").split(" ", 2)[1]
    assert alias_line("tk", "claude", shell="/bin/zsh").startswith("alias tk='claude ")


def test_the_block_is_written_once_however_many_times_it_runs(tmp_path: Path) -> None:
    """One stanza, marked at both ends. A tool that leaves a trail of them gets uninstalled by
    hand, badly, by somebody who is now annoyed."""
    rc = tmp_path / ".zshrc"
    rc.write_text("export FOO=1\n", encoding="utf-8")

    assert install_alias(rc, block("claude-tk", "claude", shell="/bin/zsh")) is True
    assert install_alias(rc, block("claude-tk", "claude", shell="/bin/zsh")) is False, (
        "an unchanged file must not be rewritten — its mtime is what says nothing happened")
    assert rc.read_text(encoding="utf-8").count(OPEN) == 1


def test_changing_the_alias_replaces_the_block_rather_than_adding_one(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    install_alias(rc, block("claude-tk", "claude", shell="/bin/zsh"))
    install_alias(rc, block("work", "claude-jp", shell="/bin/zsh"))

    written = rc.read_text(encoding="utf-8")
    assert written.count(OPEN) == 1 and written.count(CLOSE) == 1
    assert "claude-jp" in written and "alias claude-tk=" not in written


def test_removing_leaves_the_file_as_it_was(tmp_path: Path) -> None:
    """An installer with no uninstaller is a guest that moved in. Everything outside the
    markers has to survive byte for byte, including the user's own aliases."""
    rc = tmp_path / ".zshrc"
    before = 'export FOO=1\nalias mine="ls"\n'
    rc.write_text(before, encoding="utf-8")

    install_alias(rc, block("claude-tk", "claude", shell="/bin/zsh"))
    assert remove_alias(rc) is True
    assert rc.read_text(encoding="utf-8") == before

    assert remove_alias(rc) is False, "nothing of ours left — say so rather than rewrite"


def test_the_block_names_its_own_uninstall() -> None:
    """Somebody reading their rc file in a year must be able to get rid of this without
    searching for the tool that put it there."""
    assert "taskops setup --remove" in block("claude-tk", "claude", shell="/bin/zsh")
