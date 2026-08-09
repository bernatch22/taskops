"""Who a credential lets you speak as. The rows live in `store/creds.py`.

One rule, and it is what makes `agent:berna/w1` in a brief mean something: a
credential may act as itself, and a dev may act as its own agents — nobody
else's. v1 had five identity resolvers and an inference step, and a worker
that forgot its actor silently became the human who spawned it.
"""

from __future__ import annotations

from ..verbs import NO_KEY
from .._errors import Refused
from ..core.types import ANON, role_of
from ..store.creds import Credential, Credentials

__all__ = ["Credential", "Credentials", "ANONYMOUS", "anonymous", "authorize", "token_in"]

NO_CREDENTIAL = "no credential — run: taskops join <url with ?token= or ?invite=>"
"""What a PRIVATE board says to a caller with no token — unchanged, word for
word, from before public boards existed. A private board must be refused
*exactly* as it always was: the day the wall moved, the sentence that tells
somebody the wall is there must not move with it."""

ANONYMOUS = Credential(id="", subject=ANON, board="*", caps=frozenset({"read"}), once=False)
"""The credential nobody holds. It is a real `Credential` and not a `None` the
router special-cases, so every door downstream keeps ONE type and one code path
— `rpc.answered` does not learn what anonymous means, it just gets a subject
that may only read. `caps` is `{"read"}` alone, which is a second wall behind
the registry's: even if a write verb were ever mis-declared `read`, this
credential could not carry it."""


def anonymous(public: bool, need: str) -> Credential:
    """The ONE place a request with no credential is let in, and only then.

    Three conditions and no fourth: no token at all, the board says PUBLIC, and
    the verb is a READ. Anything else refuses — a write with the sentence that
    names how a key gets registered, a private board with the sentence it has
    always used. There is no anonymous-write grace and no third visibility.
    """
    if not public:
        raise Refused(NO_CREDENTIAL)
    if need != "read":
        raise Refused(NO_KEY)
    return ANONYMOUS


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
    if subject == ANON and actor != ANON:
        # BEFORE the `machine:`/`invite:` pass-through below, which returns for
        # any subject outside the dev/agent grammar — `anon` is one of those, so
        # without this line a reader with no credential could name `actor=dev:berna`
        # in the body and every write verb would judge it as berna. The anonymous
        # actor is the only one anonymous may claim.
        raise Refused(f"this credential is anonymous; it may not act as {actor}. {NO_KEY}")
    if subject == actor or not subject.startswith(("dev:", "agent:")):
        return
    owner = subject.partition(":")[2]
    if actor.startswith(f"agent:{owner}/"):
        return
    raise Refused(f"this credential is {subject}; it may not act as {actor}")
