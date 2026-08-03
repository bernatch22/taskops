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
    assert alias_line("tk", "claude", shell="/bin/zsh").startswith('alias tk="claude ')


def test_the_alias_defers_to_the_env_var_rather_than_baking_a_choice() -> None:
    """Which claude you want depends on the terminal you are in, not on what you answered the
    day you installed this. So setup stopped asking: the line reads the var at RUN time, falls
    back to plain `claude`, and a work shell exports its own."""
    posix = alias_line("tk", shell="/bin/zsh")
    assert "${TASKOPS_CLAUDE:-claude}" in posix

    fishy = alias_line("tk", shell="/usr/local/bin/fish")
    assert "${TASKOPS_CLAUDE:-claude}" not in fishy, "fish has no such expansion"
    assert "TASKOPS_CLAUDE" in fishy and fishy.startswith("alias tk '")


def test_a_pinned_binary_still_overrides_everything() -> None:
    """For a machine with one account and no interest in the var, or a per-project rc."""
    assert "TASKOPS_CLAUDE" not in alias_line("tk", "claude-jp", shell="/bin/zsh")
    assert "claude-jp " in alias_line("tk", "claude-jp", shell="/bin/zsh")


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


def test_every_path_written_is_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative path in a config is resolved against the cwd of whoever READS it, and the
    reader is an MCP server Claude Code spawned from somewhere neither of us chose. Written as
    `.` — the default `--repo` — the channel started `taskops ui --repo .`, served a different
    repository entirely, found the port taken and attached to that. Two symptoms, one dot."""
    from taskops.usecases.mcpfile import servers_for

    monkeypatch.setenv("TASKOPS_CHANNEL", "1")
    entry = servers_for(Path("."))["taskops-channel"]
    assert Path(entry["env"]["TASKOPS_REPO"]).is_absolute()
    assert entry["env"]["TASKOPS_REPO"] != "."
    assert all(Path(arg).is_absolute() for arg in entry["args"])


def test_two_projects_never_share_a_port(tmp_path: Path) -> None:
    """The second channel to start would find the first one's UI listening, attach to it, and
    serve somebody else's board — silently, because attaching is the correct behaviour when the
    port really is yours."""
    from taskops.usecases.mcpfile import port_for

    one, two = tmp_path / "alpha", tmp_path / "beta"
    assert port_for(one) != port_for(two)


def test_a_project_keeps_its_port_across_runs(tmp_path: Path) -> None:
    """Derived, not random: `hash()` is salted per process, so the same checkout would get a
    different port every session and every channel would spawn a UI beside the last one's."""
    from taskops.usecases.mcpfile import port_for

    assert port_for(tmp_path) == port_for(tmp_path)
    assert 1024 < port_for(tmp_path) < 65535


def test_the_channel_is_not_wired_by_default(tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """It pushed board events into an open session so the session could react to them — and
    every one of those reactions turned out to be idempotent and derivable from state, which
    `report kind=attention` reads in one call. What was left was echoes: a session notified
    about the dispatch it had just made. The code stays; the default does not."""
    monkeypatch.delenv("TASKOPS_CHANNEL", raising=False)
    wire_mcp(tmp_path)
    written = json.loads((tmp_path / MCP_FILE).read_text(encoding="utf-8"))
    assert "taskops" in written["mcpServers"]
    assert "taskops-channel" not in written["mcpServers"]


def test_the_channel_is_still_there_for_anybody_who_wants_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in, not deleted. It is 1 200 tested lines and the one deployment it was written for
    — several machines writing to one board — is the one where a push still beats a sweep."""
    monkeypatch.setenv("TASKOPS_CHANNEL", "1")
    wire_mcp(tmp_path)
    written = json.loads((tmp_path / MCP_FILE).read_text(encoding="utf-8"))
    assert "taskops-channel" in written["mcpServers"]


def test_init_wires_the_claude_hooks_into_the_project(tmp_path: Path) -> None:
    """The failure this exists for: two developers joined a board, worked it, and both left
    their cards dead in `review` — because the hooks that prevent exactly that ship in the
    taskops PLUGIN, the plugin was not installed, and nothing said so. They had the MCP tools
    and the git hooks, so the setup looked complete and was missing its whole feedback loop.

    A plugin is a per-machine, per-person install. These hooks belong to the PROJECT: joining
    a board is what should turn a checkout into one whose sessions know their role.
    """
    from taskops.usecases import init
    from taskops.usecases.claudefile import SETTINGS_FILE

    init(tmp_path, install_git_hooks=False)

    written = json.loads((tmp_path / SETTINGS_FILE).read_text(encoding="utf-8"))["hooks"]
    assert set(written) == {"PreToolUse", "PostToolUse", "SessionStart", "Stop", "SubagentStop"}
    command = written["SessionStart"][0]["hooks"][0]["command"]
    assert command.endswith("session-start")
    assert Path(command.split()[0]).is_absolute(), "a hook runs from a cwd nobody chose"


def test_a_hook_somebody_configured_by_hand_survives(tmp_path: Path) -> None:
    """Shared config, merged never replaced — the same rule `.mcp.json` follows, for the same
    reason: a tool that rewrote the file would delete a teammate's work to add its own."""
    from taskops.usecases import init
    from taskops.usecases.claudefile import SETTINGS_FILE

    theirs = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "make lint"}]}]}}
    (tmp_path / ".claude").mkdir()
    (tmp_path / SETTINGS_FILE).write_text(json.dumps(theirs), encoding="utf-8")

    init(tmp_path, install_git_hooks=False)

    written = json.loads((tmp_path / SETTINGS_FILE).read_text(encoding="utf-8"))["hooks"]
    assert written["Stop"] == theirs["hooks"]["Stop"], "their Stop hook, untouched"
    assert "SessionStart" in written, "and ours, added beside it"


def test_the_hook_wiring_is_never_committed(tmp_path: Path) -> None:
    """It names the absolute path to `taskops-hook` on THIS machine. Committed, it hands a
    teammate five hooks pointing into a directory they do not have — and hooks fail silently,
    which is the worst shape a failure can take. So it goes in the personal settings file and
    `init` puts that file in the ignore block; a clone that joins writes its own."""
    from taskops.usecases import init
    from taskops.usecases.claudefile import SETTINGS_FILE

    init(tmp_path, install_git_hooks=False)

    assert SETTINGS_FILE in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    written = json.loads((tmp_path / SETTINGS_FILE).read_text(encoding="utf-8"))
    assert Path(written["hooks"]["Stop"][0]["hooks"][0]["command"].split()[0]).is_absolute()


def test_init_writes_the_specialists_where_claude_code_reads_them(tmp_path: Path) -> None:
    """`Agent type 'taskops-worker' not found` — the third rendering of the same failure
    (.mcp.json, then the hooks, now the agents), each one a piece the project needed that
    lived in a plugin nobody installs. Worst of the three: by then SessionStart was ORDERING
    sessions to dispatch a specialist that did not exist, and every one fell back to
    general-purpose — a verifier without the sonnet/read-only constraints spent twenty
    minutes building venvs to check three calendar functions."""
    from taskops.usecases import init

    init(tmp_path, install_git_hooks=False)

    agents = tmp_path / ".claude" / "agents"
    assert (agents / "taskops-worker.md").is_file()
    verifier = (agents / "taskops-verifier.md").read_text(encoding="utf-8")
    # `opus`, y este assert decia `sonnet` con el mensaje "the constraint that makes
    # verification fast". Era cierto MIENTRAS el worker tambien estaba clavado en sonnet: los
    # dos al mismo nivel, y el barato alcanzaba. El worker ahora NO fija modelo — hereda el de
    # la sesion, porque quien despacha la card es el unico que leyo la spec — asi que un
    # verifier clavado abajo queda estructuralmente mas debil que lo que audita, y un
    # verificador mas facil de convencer que el worker es un sello de goma con pasos extra.
    #
    # Lo que se fija es la ASIMETRIA, que es la politica entera, no el nombre del modelo.
    assert "model: opus" in verifier, "the verifier may never be weaker than the worker"
    # El FRONTMATTER, no el archivo: el cuerpo del worker explica en prosa por que no fija
    # modelo, asi que buscar la cadena en todo el texto encuentra la explicacion y no el campo.
    worker = (agents / "taskops-worker.md").read_text(encoding="utf-8")
    front = worker.split("---")[1]
    assert "model:" not in front, (
        "the worker inherits: pinning one would overpay for a typo or underpay a state machine")
    assert ".claude/agents/taskops-*.md" in (tmp_path / ".gitignore").read_text(
        encoding="utf-8"), "generated like GUIDE.md, ignored like GUIDE.md"


def test_a_projects_own_agents_survive_init(tmp_path: Path) -> None:
    """Only `taskops-*` is ours. A project's own specialist is its code."""
    from taskops.usecases import init

    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "db-migrator.md").write_text("---\nname: db-migrator\n---\ntheirs",
                                           encoding="utf-8")

    init(tmp_path, install_git_hooks=False)

    assert (agents / "db-migrator.md").read_text(encoding="utf-8").endswith("theirs")


def test_the_plugin_and_the_package_carry_the_same_agents() -> None:
    """Two copies exist on purpose — the plugin still ships them — and two copies of one
    concept is three bugs unless something pins them together. This is the something."""
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[2]
    assets = repo / "src" / "taskops" / "assets" / "agents"
    plugin = repo / "plugin" / "agents"
    for spec in sorted(assets.glob("taskops-*.md")):
        assert (plugin / spec.name).read_bytes() == spec.read_bytes(), \
            f"{spec.name} drifted between plugin/ and assets/"
