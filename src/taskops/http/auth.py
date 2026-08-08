"""Who a credential lets you speak as. The rows live in `store/creds.py`.

One rule, and it is what makes `agent:berna/w1` in a brief mean something: a
credential may act as itself, and a dev may act as its own agents — nobody
else's. v1 had five identity resolvers and an inference step, and a worker
that forgot its actor silently became the human who spawned it.
"""

from __future__ import annotations

from .._errors import Refused
from ..core.types import role_of
from ..store.creds import Credential, Credentials

__all__ = ["Credential", "Credentials", "authorize", "token_in"]


def token_in(header: str, path: str) -> str:
    """The bearer token, from the Authorization header or the query string.

    Both, and in that order, because the same door is opened three ways: an
    agent's client sends a header, a browser follows a link (`?token=`), and a
    newcomer redeems an invite (`?invite=`). One extractor, so a door added
    later — /feed, /git — cannot accidentally invent a second way in.
    """
    token = header.removeprefix("Bearer ").strip()
    if token:
        return token
    for part in path.partition("?")[2].split("&"):
        if part.startswith(("token=", "invite=")):
            return part.partition("=")[2]
    return ""


def authorize(credential: Credential, actor: str) -> None:
    """A credential may act as itself, and a dev may act as its own agents.

    That single rule is what makes `agent:berna/w1` in a brief meaningful: a
    worker spawned by berna cannot claim to be somebody else's worker.
    """
    role_of(actor)  # grammar first: a malformed actor never reaches a verb
    subject = credential.subject
    if subject == actor or not subject.startswith(("dev:", "agent:")):
        return
    owner = subject.partition(":")[2]
    if actor.startswith(f"agent:{owner}/"):
        return
    raise Refused(f"this credential is {subject}; it may not act as {actor}")
