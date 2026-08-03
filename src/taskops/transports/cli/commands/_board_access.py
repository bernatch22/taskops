"""`taskops board access` — who can reach this board, answered where the answer lives.

Split out of `_board_render` when a board stopped needing GitHub at all, and the split is the
distinction: that module renders what `create` and `list` DID, this one renders a standing fact
about a board somebody else administers. They also read differently now — a board with a
repository has an access list that revokes itself, and a board without one has a token and a
stack of invite codes, and those are two different sentences to write.

It prints `gh` commands rather than offering its own, which is the design and not a gap: a user
list here would be a copy of the repository's collaborators, and a copy is exactly what goes
stale the day somebody's access is revoked.
"""

from __future__ import annotations

__all__ = ["access_of"]


def access_of(url: str, slug: str) -> str:
    """Who can reach the board, answered where the answer lives.

    It prints the `gh` commands rather than offering its own, and that is the design and not a
    gap: a user list here would be a copy of the repository's collaborators, and a copy is
    exactly what goes stale the day somebody's access is revoked.
    """
    if not slug:
        return (f"{url or 'this board'} is not linked to a GitHub repository — its access is "
                f"its token, and everyone who has the string has all of it.\n"
                f"  link it:  taskops serve link <name> --github owner/repo")
    return "\n".join([
        f"{url or 'this board'} → {slug}",
        "access IS push access to that repository — taskops keeps no user list.",
        "",
        f"  who has it:  gh api repos/{slug}/collaborators --jq '.[] | \"\\(.login)\\t\\(.role_name)\"'",
        f"  grant:       gh repo collaborator add <user> --permission push -R {slug}",
        f"  revoke:      gh repo collaborator remove <user> -R {slug}",
        "",
        "revoking takes effect on their NEXT login — sessions last 7 days.",
    ])
