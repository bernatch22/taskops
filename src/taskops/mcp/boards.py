"""Every board this session can reach, opened once and kept.

The host runs ONE MCP server per session, pinned to the directory it opened.
That is right for identity — a session works on a project — and wrong as a
LIMIT: a second project was simply unreachable, and the work left through
`curl` against the HTTP door instead of the tools.

That detour is not equivalent, which is the whole reason this exists. The RPC
door dispatches VERBS (`verbs/`, which may not touch git — `test_architecture`
enforces it); cutting a worktree, stamping a branch and integrating a card live
one layer up, in `mcp/gitmoves.py`. So a board driven over HTTP silently loses
the git half: `assign` hands out a card and prepares nothing, and the worker
discovers it has no worktree. Measured on the first real second board,
2026-08-08.

`http/mounts.py` already holds many boards for one process, for the same reason
and with the same shape. This is that, on the stdio side.

The default stays the board the server started in, so nothing about a
single-project session changes: `repo_path` is an override, never a
requirement.
"""

from __future__ import annotations

from pathlib import Path

from ..board import Board, find_root, open_board


class Boards:
    """`repo_path` → an open board, resolved once per root and cached."""

    def __init__(self, home: Board, repo: Path, actor: str) -> None:
        self.actor = actor
        self.home = repo
        self._open: dict[Path, Board] = {repo: home}

    def at(self, path: str) -> tuple[Board, Path]:
        """The board for `path`, and the repo root it resolved to.

        An empty path is the session's own board — the common case, and the one
        that must cost nothing. Anything else is resolved to its root FIRST, so
        two paths inside one project share a board rather than opening it twice
        and racing each other's writes through two caches.
        """
        if not path:
            return self._open[self.home], self.home
        root = find_root(Path(path).expanduser())
        found = self._open.get(root)
        if found is None:
            # Raises for a directory with no board, and that refusal already
            # names `taskops init` — the tool layer turns it into a result the
            # agent reads, so a wrong path is answerable, never fatal.
            found = open_board(root, self.actor)
            self._open[root] = found
        return found, root

    def close(self) -> None:
        for board in self._open.values():
            board.close()
        self._open.clear()
