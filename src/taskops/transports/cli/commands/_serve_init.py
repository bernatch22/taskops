"""`taskops serve init` — one board on this box, and the sentence that describes it.

Thin over `usecases.provision` since `board create` arrived: the person on the box and the
laptop asking over HTTP must get the SAME board, so what a board IS lives in the use case and
what a terminal reads lives here.

This path stays for the two cases the GitHub one cannot serve: a board whose project is not on
GitHub, and a server bootstrapping itself. It is no longer how a team starts — see
`taskops board create`, which needs nobody to log into anything.
"""

from __future__ import annotations

from pathlib import Path

from ....contracts.hosting import TOKEN_FILE
from ....usecases.provision import provision

__all__ = ["create"]


def create(root: Path, project: str) -> str:
    """Provision it and say what happened, printing the token exactly once."""
    return _describe(root / project, project, provision(root, project))


def _describe(home: Path, project: str, token: str) -> str:
    """The token is shown ONCE and the sentence says so, because the alternative — a reader who
    assumes they can ask for it again — is a reader who does not write it down."""
    if not token:
        return (f"{project} already exists at {home}\n"
                f"its token is in {home / TOKEN_FILE} — it is never printed twice")
    return (f"created {project} at {home}\n"
            f"token (shown ONCE, kept in {home / TOKEN_FILE}):\n\n    {token}\n\n"
            f"link it to a repository so your team needs no token at all:\n"
            f"    taskops serve link {project} --github <owner>/<repo>\n\n"
            f"open the board at  http://<host>/{project}/?token={token}")
