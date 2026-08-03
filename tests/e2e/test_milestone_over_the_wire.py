"""A chapter on a board with a REMOTE — the seam, and the one place this could break silently.

Twelve bugs in three days here lived between two machines and every test in the suite ran one
repo, one process, one store. A milestone is the worst possible thing to get that wrong about: it
is the only thing on a board that ENDS, so a move applied locally is a chapter that closed on one
machine and stayed open on every other, and nothing anywhere says so — a worker on the second
machine keeps reading rules from a chapter its board has already shipped.

The bug this file was written after is exactly that shape and it was not a logic bug: the rpc row
for `milestone_create` named a function that does not exist (`ms.open_wrapped`), so creating a
chapter from a clone raised `AttributeError` on the server. Every single-store test passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.storage import Store
from taskops.storage.milestone import active, milestones
from taskops.usecases import milestone as ms
from taskops.usecases._contextviews import show
from taskops.usecases.context import state

from .test_agentwire import TOKEN, Serving


@pytest.fixture()
def hub(tmp_path: Path) -> "object":
    """A server whose board has NO chapter — the clone opens it, which is the point."""
    from taskops.usecases import init

    root = tmp_path / "hub"
    init(root, install_git_hooks=False)
    running = Serving(root)
    try:
        yield running
    finally:
        running.close()


def machine(where: Path, url: str) -> Path:
    """A developer's checkout that writes through `url` — and with NO chapter of its own.

    Deliberately unlike the one in `test_agentwire`: that fixture opens a chapter locally so its
    cards have a home, and here a chapter in the clone's own log is the very thing that must not
    be mistaken for the board's.
    """
    from taskops.usecases import add_remote, init

    init(where, install_git_hooks=False)
    add_remote(where, url, TOKEN)
    return where


def _on_the_server(root: Path) -> list[dict]:  # type: ignore[type-arg]
    with Store(root) as store:
        return [dict(m) for m in milestones(store)]


def test_a_chapter_created_from_a_clone_exists_on_the_SERVER(tmp_path: Path,
                                                             hub: Serving) -> None:
    """THE bug, asserted where it lived. The clone's own sqlite is a cache: if the chapter were
    written there instead, everything the clone reads would agree with itself and no other machine
    would have heard of it.
    """
    mine = machine(tmp_path / "mine", hub.url)
    made = ms.open_chapter(mine, "que una clienta suba su CSV", horizon="2026-09-01",
                           actor="dev:berna")

    (found,) = _on_the_server(hub.root)
    assert found["title"] == "que una clienta suba su CSV"
    assert found["id"] == made["id"], "the clone's id must be the server's"
    assert found["horizon"] == "2026-09-01", "the whole body crosses, not four fields"


def test_a_chapter_verified_from_a_clone_closes_on_the_SERVER(tmp_path: Path,
                                                              hub: Serving) -> None:
    """Every move routes, and `reached` is the one that must: a chapter closed in a replica is a
    board that disagrees with itself about what has shipped."""
    mine = machine(tmp_path / "mine", hub.url)
    chapter = ms.open_chapter(mine, "el importador", actor="dev:berna")
    ms.hand_over(mine, chapter["id"], note="las dos cards cerradas", actor="agent:berna/w1")
    ms.verify(mine, chapter["id"], actor="dev:berna")

    (found,) = _on_the_server(hub.root)
    assert found["state"] == "reached"
    assert found["closed_by"] == "dev:berna", "who VERIFIED it, never who reported it"
    with Store(hub.root) as store:
        assert active(store) == [], "and it is out of force for every reader of that board"


def test_an_agent_on_a_clone_is_refused_by_the_SERVER(tmp_path: Path, hub: Serving) -> None:
    """The guard lives in the engine, so it holds wherever the write lands. A rule enforced in the
    caller is a rule a second implementation can walk around — and here the second implementation
    is the same code running on another machine."""
    # `TaskopsError` and not `BadRequest`: a refusal decided on the server arrives as a 400 and is
    # re-raised by the wire client, which keeps the SENTENCE and cannot keep the class. That is the
    # contract worth pinning — the message is what a caller acts on, here and locally alike.
    from taskops._errors import TaskopsError

    mine = machine(tmp_path / "mine", hub.url)
    chapter = ms.open_chapter(mine, "el importador", actor="dev:berna")
    with pytest.raises(TaskopsError) as refused:
        ms.verify(mine, chapter["id"], actor="agent:berna/w1")
    assert "verifying is not reporting" in str(refused.value)
    (found,) = _on_the_server(hub.root)
    assert found["state"] == "in_force", "and nothing moved"


def test_a_fact_stated_on_a_clone_joins_the_chapter_on_the_SERVER(tmp_path: Path,
                                                                  hub: Serving) -> None:
    """The chapter is resolved where the log is, never by the caller. A clone that guessed would
    file the fact under a chapter id that machine happens to know about — and a fact in the wrong
    chapter reaches the wrong cards with nothing saying so."""
    mine = machine(tmp_path / "mine", hub.url)
    chapter = ms.open_chapter(mine, "el importador", actor="dev:berna")
    state(mine, "decision", "el CSV se lee en streaming", actor="dev:berna")

    seen = show(hub.root)
    assert [f["text"] for f in seen["decisions"]] == ["el CSV se lee en streaming"]
    assert seen["decisions"][0]["milestone"] == chapter["id"]


def test_reading_the_chapters_from_a_clone_answers_with_the_servers(tmp_path: Path,
                                                                    hub: Serving) -> None:
    """`milestone_list` answers an OBJECT with a list inside it. A verb that answered a bare array
    decodes to `{}` with no error anywhere — three verbs did it at once, and `search` found zero
    tasks on every board with a remote."""
    mine = machine(tmp_path / "mine", hub.url)
    ms.open_chapter(mine, "el importador", actor="dev:berna")
    ms.open_chapter(mine, "la facturacion", planned=True, actor="dev:berna")

    listed = ms.listing(mine)
    assert [m["title"] for m in listed["milestones"]] == ["el importador", "la facturacion"]
    assert "counts" in listed
