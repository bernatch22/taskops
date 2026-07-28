"""`taskops serve link <project> --github owner/repo` — who may log into a board.

One file with `owner/repo` in it is the entire access control for a project, and that is the
design rather than a first version of it: the collaborator list already exists on GitHub, is
already maintained by whoever owns the code, and is already the thing that decides who may
change it. Copying it here — a list of logins, a team, a role — would create a second list,
and the second list is the one nobody updates the day somebody leaves.

Linking changes nothing for the machine credential: the project's `token` still opens it, so
push, pull and agents are untouched. A project with no link behaves exactly as before, which
is what makes this safe to add to a server that is already running.
"""

from __future__ import annotations

from pathlib import Path

from ...._errors import TaskopsError
from ....usecases import locate
from ....usecases._ghlink import read_link, remove_link, write_link

__all__ = ["link"]


def link(root: Path, project: str, *, slug: str = "", remove: bool = False) -> str:
    """Set, remove or SHOW the link. No arguments means show — a read is the safe default for
    a command whose write changes who can enter."""
    home = root / project
    _require(root, home, project)
    if remove:
        return _removed(project, remove_link(home))
    if slug:
        return (f"{project} → {write_link(home, slug)}\n"
                f"anyone with push access to that repository can now run "
                f"`taskops login <url>` and open this board")
    return _shown(project, read_link(home))


def _require(root: Path, home: Path, project: str) -> None:
    """It must be a project HERE. `locate` walks UP, so a bare directory under the root
    resolves to some ancestor project — and a link written into that would silently grant
    access to a board nobody named."""
    try:
        found = locate(home)
    except (TaskopsError, OSError):
        found = None
    if found != home:
        raise TaskopsError(f"no project '{project}' under {root} — create it with "
                           f"`taskops serve init {project}`")


def _shown(project: str, slug: str) -> str:
    if not slug:
        return (f"{project} is not linked to a repository — it is open to its token only\n"
                f"link it with `taskops serve link {project} --github owner/repo`")
    return f"{project} → {slug}"


def _removed(project: str, had: bool) -> str:
    if not had:
        return f"{project} was not linked to anything"
    return (f"{project} is no longer linked — its token is again the only way in\n"
            f"sessions already minted keep working until they expire")
