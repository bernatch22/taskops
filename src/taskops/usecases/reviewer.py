"""Who may close a card — reading the name, and the project's default for it.

A card's reviewer is POLICY, so the two questions it raises are answered here rather than in
the three places that write the field. What a name means (`human`, a person, a registered
specialist) is one answer; what a card gets when nobody said is the other.

**The default is a project DECISION, not a constant.** A team that wants every card read by a
person and a team that wants a `tester` agent are both right, and a constant in the source
could only serve one of them — worse, changing it would be a release. So it is stated the way
every other standing fact about a project is stated, as context:

    taskops context decision "reviewer: tester"

Read once, at CREATION, and written onto the card. Resolving it at close time instead would
make a decision changed today rewrite who was allowed to close work planned last week — and
the card would no longer be able to say who its reviewer is, which is the whole ask.

**A bare name must be registered, a prefixed id must not** — the same split the assign
endpoint already makes, and for the same reason: `reviewer: tsetr` is a card nothing can ever
close and nothing on the board says why, while `dev:ana` addresses a person who was never
going to be in a registry.
"""

from __future__ import annotations

from .._errors import BadRequest
from .._types import HUMAN, PEER
from ..storage import Store
from ..storage.context import facts
from ._contextslice import in_force
from .agents import registry

__all__ = ["named", "for_new", "project_default"]

_DEFAULT_PREFIX = "reviewer:"
"""How a decision announces itself. A decision is free prose, so the marker has to be at the
front where a reader of `taskops context show` sees the same thing the parser does."""


def named(store: Store, value: str) -> str:
    """Validate one reviewer as written, or refuse it naming the specialists this project has.

    "" is legal and means "nobody named" — that is how `tasks edit` clears a reviewer, and it
    is what every card written before this existed already says.

    `none` and `nobody` normalise to it. They exist because "" is what somebody has to type on
    a command line to mean "no reviewer", and `--reviewer ""` reads as a mistake next to
    `--reviewer none`.
    """
    wanted = value.strip()
    if wanted.lower() in ("none", "nobody"):
        return ""
    if not wanted or wanted in (HUMAN, PEER):
        return wanted
    if ":" in wanted:
        # A person or an ad-hoc worker. Left free-form on purpose, exactly as assignment
        # leaves it: the claim fence treats an actor it does not know as unrestricted too.
        return wanted
    known = [spec["name"] for spec in registry(store.root)]
    if wanted not in known:
        raise BadRequest(
            f"`{wanted}` is not a specialist this project registered — it knows "
            f"{', '.join(known) or 'none'}. For a person, use `human`, `dev:<name>` or "
            f"`agent:<dev>/<name>`; for \"anybody but the author\", `peer`.")
    return wanted


def for_new(store: Store, value: str | None) -> str:
    """The reviewer a card is created with: what was ASKED FOR, else the project's decision.

    `None` means the field was absent and the default applies; anything else — including "" —
    was stated and is honoured. That distinction is the whole point: with a project-wide
    `reviewer: human`, a card that could not say "nobody" would have no way to be a text fix,
    and an empty string was indistinguishable from an omission.
    """
    return project_default(store) if value is None else named(store, value)


def _first_word(rest: str) -> str:
    """The reviewer is the FIRST token; everything after it is the reason it was chosen.

    It used to be the whole line, and that quietly disabled the feature the first time somebody
    used it properly: this project asks every decision to carry its why, so the text read
    `reviewer: peer — nobody closes work produced by their own agents`, the whole tail was
    taken as a name, no specialist matched, and the degradation to "" made every card come out
    with no reviewer at all. Silent, and indistinguishable from never having stated it.

    A reviewer is `human`, `peer`, `dev:ana`, `agent:ana/api` or a registered name — none of
    which contain whitespace — so the split is unambiguous and the rest is free prose.
    """
    return rest.strip().split(maxsplit=1)[0] if rest.strip() else ""


def project_default(store: Store) -> str:
    """The `reviewer: <who>` decision in force, or "" for the stock verifier.

    An unparseable or unregistered value degrades to "" rather than raising: a typo in a
    project-wide decision must not make every `plan` call fail, and "" is the behaviour every
    card had before anybody stated one.
    """
    for fact in reversed(in_force(facts(store))["decisions"]):
        text = fact["text"].strip()
        if text.lower().startswith(_DEFAULT_PREFIX):
            wanted = _first_word(text[len(_DEFAULT_PREFIX):])
            try:
                return named(store, wanted)
            except BadRequest:
                return ""
    return ""
