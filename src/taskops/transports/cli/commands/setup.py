"""`taskops setup` — wire this machine: the project's MCP servers, and the channel alias.

The alias half writes to a file the user owns, so the interaction is built around showing
before doing: `--print` renders the exact block and the exact path and changes nothing, and the
prompt names what it found rather than guessing. `--remove` exists because an installer with no
uninstaller is a guest that moved in.
"""

from __future__ import annotations

import argparse

from ....usecases.mcpfile import MCP_FILE, wire_mcp
from ....usecases.shellrc import (
    block,
    claude_binaries,
    install_alias,
    rc_path,
    remove_alias,
)
from ._shared import add_target, repo_of

__all__ = ["register", "run"]

DEFAULT_ALIAS = "claude-tk"


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("setup", help="wire the MCP servers, and the shell alias that "
                                          "opens a session with the board channel")
    add_target(parser)
    parser.add_argument("--claude", default="",
                        help="which claude binary the alias runs (default: ask)")
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help=f"the alias name "
                                                               f"(default: {DEFAULT_ALIAS})")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="show the block and the file it would go in, and write nothing")
    parser.add_argument("--remove", action="store_true", help="take the block back out")
    parser.add_argument("--no-shell", action="store_true",
                        help="only wire .mcp.json — do not touch any shell file")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where = rc_path()
    if args.remove:
        return (f"removed the taskops block from {where}" if remove_alias(where)
                else f"nothing of ours in {where} — already clean")

    lines = _wire(repo_of(args))
    if args.no_shell:
        return "\n".join([*lines, "shell untouched (--no-shell)"])

    stanza = block(str(args.alias), _claude(args), shell="")
    if args.print_only:
        return "\n".join([*lines, f"\nwould write into {where}:\n", stanza.rstrip()])
    changed = install_alias(where, stanza)
    lines.append(f"{'wrote' if changed else 'already had'} the alias block in {where}")
    lines.append(f"open a new shell, then: {args.alias}")
    return "\n".join(lines)


def _wire(repo: object) -> list[str]:
    """The half that touches only the project. Always runs — it is the part that is safe."""
    from pathlib import Path

    added = wire_mcp(Path(str(repo)))
    if added:
        return [f"wired {', '.join(added)} into {MCP_FILE}"]
    return [f"{MCP_FILE} already names our servers"]


def _claude(args: argparse.Namespace) -> str:
    """Which claude the alias runs — asked, never guessed.

    A machine with `claude` and `claude-jp` on it has two ACCOUNTS, and picking one silently
    would wire a board to the wrong work. Non-interactive callers pass `--claude`; an
    interactive one is shown what is actually on PATH.
    """
    if args.claude:
        return str(args.claude)
    found = claude_binaries() or ["claude"]
    if len(found) == 1:
        return found[0]
    print("which claude should the alias run?")
    for index, name in enumerate(found, start=1):
        print(f"  {index}) {name}")
    answer = input(f"[1-{len(found)}, default 1]: ").strip()
    chosen = int(answer) if answer.isdigit() and 1 <= int(answer) <= len(found) else 1
    return found[chosen - 1]
