"""`taskops setup` — wire this machine: the project's MCP servers, and nothing else by default.

The shell half is now behind `--channel`, and the inversion is the point. That alias exists for
exactly one reason — to add `--dangerously-load-development-channels` — and the channel left the
default path when the sweep replaced it (`docs/orchestrator.md`). A setup that still edited
`~/.zshrc` to enable something the project no longer uses would be the most invasive thing in
the package doing it for nothing.

`--remove` still needs no flag: an uninstaller you have to opt into is not one, and somebody
running it wants the block gone whether or not they remember how it got there.

The half that stays writes to a file the user owns, so the interaction is built around showing
before doing: `--print` renders the exact block and the exact path and changes nothing.
"""

from __future__ import annotations

import argparse

from ....usecases.mcpfile import MCP_FILE, wire_mcp
from ....usecases.shellrc import (
    ENV_CLAUDE,
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
    parser = sub.add_parser("setup", help="wire this project's MCP servers (and, with "
                                          "--channel, the opt-in board-channel alias)")
    add_target(parser)
    parser.add_argument("--claude", default="",
                        help=f"pin the binary in the written line (default: defer to "
                             f"${ENV_CLAUDE}, falling back to `claude`)")
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help=f"the alias name "
                                                               f"(default: {DEFAULT_ALIAS})")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="show the block and the file it would go in, and write nothing")
    parser.add_argument("--remove", action="store_true", help="take the block back out")
    parser.add_argument("--channel", action="store_true",
                        help="also install the shell alias for the EXPERIMENTAL board channel "
                             "— off by default; `taskops attention` is what replaced it")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where = rc_path()
    if args.remove:
        return (f"removed the taskops block from {where}" if remove_alias(where)
                else f"nothing of ours in {where} — already clean")

    lines = _wire(repo_of(args))
    if not args.channel:
        return "\n".join([*lines, "shell untouched — pass --channel for the experimental "
                                  "board channel, or open your sessions with "
                                  "`taskops attention`"])

    stanza = block(str(args.alias), str(args.claude), shell="")
    if args.print_only:
        return "\n".join([*lines, f"\nwould write into {where}:\n", stanza.rstrip()])
    changed = install_alias(where, stanza)
    lines.append(f"{'wrote' if changed else 'already had'} the alias block in {where}")
    lines.append(f"open a new shell, then: {args.alias}")
    found = claude_binaries()
    if not args.claude and len(found) > 1:
        # Told, not asked. Which account you want depends on the terminal you are in, so the
        # answer belongs in an env var rather than in a line written the day you installed.
        lines.append(f"this machine has {', '.join(found)} — `export {ENV_CLAUDE}=<one>` "
                     f"in a shell to pick, otherwise it runs `claude`")
    return "\n".join(lines)


def _wire(repo: object) -> list[str]:
    """The half that touches only the project. Always runs — it is the part that is safe."""
    from pathlib import Path

    added = wire_mcp(Path(str(repo)).expanduser().resolve())
    if added:
        return [f"wired {', '.join(added)} into {MCP_FILE}"]
    return [f"{MCP_FILE} already names our servers"]


