"""Invites: one person, one board, one use — the way in for a board with no GitHub behind it.

Four properties, and each one closes a way this shape usually leaks. They are tested separately
because they fail separately: a code that works twice, a code that never expires, a code that
names nobody, and a code sitting in plain text in a file on the server are four different
incidents with four different blast radii.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.contracts.invite import INVITE_FILE, INVITE_TTL
from taskops.usecases import init
from taskops.usecases._sessions import resolve
from taskops.usecases.invites import offer, pending, redeem, withdraw


@pytest.fixture
def server(tmp_path: Path) -> Path:
    """A server root holding one board, the way `provision` leaves it."""
    init(tmp_path / "probe", install_git_hooks=False)
    return tmp_path


# ---- the four properties


def test_a_redeemed_invite_mints_a_session_naming_the_person(server: Path) -> None:
    """The whole reason not to just share the board token: the board records `ana`, not
    "somebody who had the link"."""
    code = offer(server / "probe", "ana", by="dev:berna")

    got = redeem(server, "probe", code)

    assert got["login"] == "ana"
    assert resolve(server, got["session"]) == {"login": "ana", "projects": ["probe"],
                                               "created": resolve(server, got["session"])["created"]}


def test_a_code_works_exactly_once(server: Path) -> None:
    """A code that works twice is a code that works forever, because it is in a chat log."""
    code = offer(server / "probe", "ana", by="dev:berna")
    redeem(server, "probe", code)

    with pytest.raises(BadRequest):
        redeem(server, "probe", code)
    assert pending(server / "probe") == []


def test_an_expired_invite_is_invisible_and_refused(server: Path) -> None:
    """Pruned on READ, so it stops working the moment it is old enough — on a server nobody
    has written to in a month, with no sweeper and no daemon."""
    code = offer(server / "probe", "ana", by="dev:berna")
    path = server / "probe" / INVITE_FILE
    aged = json.loads(path.read_text(encoding="utf-8"))
    aged[0]["created"] -= INVITE_TTL + 1
    path.write_text(json.dumps(aged), encoding="utf-8")

    assert pending(server / "probe") == []
    with pytest.raises(BadRequest):
        redeem(server, "probe", code)


def test_the_code_is_never_written_down(server: Path) -> None:
    """A leaked `invites.json` should be a list of names, not a set of working keys. The code
    exists in exactly one place: the message the owner sent."""
    code = offer(server / "probe", "ana", by="dev:berna")

    for path in server.rglob("*"):
        if path.is_file():
            assert code not in path.read_bytes().decode("utf-8", errors="replace"), path


# ---- refusals


def test_an_unknown_code_and_an_expired_one_get_the_same_answer(server: Path) -> None:
    """Telling them apart says whether a guessed string was ever real, which is the only thing
    a guesser learns from."""
    with pytest.raises(BadRequest) as refused:
        redeem(server, "probe", "0" * 32)
    assert "used already, withdrawn, or expired" in str(refused.value)


def test_an_invite_is_bound_to_ONE_board(server: Path) -> None:
    init(server / "otro", install_git_hooks=False)
    code = offer(server / "probe", "ana", by="dev:berna")

    with pytest.raises(BadRequest):
        redeem(server, "otro", code)
    assert resolve(server, redeem(server, "probe", code)["session"])["projects"] == ["probe"]


@pytest.mark.parametrize("who", ["", "  ", "dev:ana", "ana/w1"])
def test_a_name_that_is_not_a_bare_handle_is_refused(server: Path, who: str) -> None:
    """The board will write `dev:<who>`, so a prefixed or slashed name would produce an actor
    id nothing can parse — and the refusal comes before a code is minted."""
    with pytest.raises(BadRequest):
        offer(server / "probe", who, by="dev:berna")
    assert pending(server / "probe") == []


# ---- managing them


def test_inviting_the_same_person_twice_replaces_their_code(server: Path) -> None:
    """A person who lost the message needs a working code, not a second live door with their
    name on it."""
    first = offer(server / "probe", "ana", by="dev:berna")
    second = offer(server / "probe", "ana", by="dev:berna")

    assert [i["who"] for i in pending(server / "probe")] == ["ana"]
    with pytest.raises(BadRequest):
        redeem(server, "probe", first)
    assert redeem(server, "probe", second)["login"] == "ana"


def test_an_invite_can_be_withdrawn_before_it_is_spent(server: Path) -> None:
    code = offer(server / "probe", "ana", by="dev:berna")

    assert withdraw(server / "probe", "ana") is True
    assert withdraw(server / "probe", "ana") is False, "and saying so twice is not an error"
    with pytest.raises(BadRequest):
        redeem(server, "probe", code)


def test_the_file_is_0600(server: Path) -> None:
    """Adjacent to a secret even though it holds none: the digests are what an offline guess
    would be run against, and this file sits beside the board's token."""
    offer(server / "probe", "ana", by="dev:berna")
    assert (server / "probe" / INVITE_FILE).stat().st_mode & 0o777 == 0o600
