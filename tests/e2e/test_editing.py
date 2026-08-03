"""Rewriting a card, and that rewrite surviving the trip through git to another clone.

A spec that could never be corrected was the gap: the only way to fix a wrong brief was to
cancel the card and plan a new one, which threw away its thread and its commits. These tests
pin the four things that makes true — the row moves, the log says so, another machine ends up
agreeing, and a closed card refuses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.engine import build, record, replay
from taskops.storage import Store, all_events
from taskops.usecases import ask, edit, init, next_task, plan, sync, update
from taskops.usecases.milestone import open_chapter


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True)
    return done.stdout.strip()


@pytest.fixture
def carded(tmp_path: Path) -> tuple[Path, str]:
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    created = plan(tmp_path, [{"title": "Parse the header", "spec": "old brief"}],
                   actor="dev:berna")["created"][0]
    return tmp_path, created["id"]


def kinds_on(root: Path, task_id: str) -> list[str]:
    with Store(root) as store:
        return [e["kind"] for e in store.events.of_task(task_id)]


def test_editing_rewrites_the_row_and_writes_one_event_per_field(
        carded: tuple[Path, str]) -> None:
    """Two fields changed, two `edited` events — a body carrying both would make replay's
    newer-wins rule all-or-nothing across fields nobody edited together."""
    root, task_id = carded
    result = edit(root, task_id, spec="the real brief", priority=0, actor="dev:berna")

    assert result["changed"] == ["spec", "priority"]
    assert result["task"]["spec"] == "the real brief"
    assert result["task"]["priority"] == 0
    assert ask(root, task_id)["task"]["spec"] == "the real brief"
    assert kinds_on(root, task_id).count("edited") == 2


def test_an_edit_that_changes_nothing_records_nothing(carded: tuple[Path, str]) -> None:
    """A no-op event would bump `updated` — the arbitrator replay uses — and so let a
    redundant edit here beat a real edit on another machine."""
    root, task_id = carded
    result = edit(root, task_id, spec="old brief", actor="dev:berna")

    assert result["changed"] == []
    assert "edited" not in kinds_on(root, task_id)


def test_editing_with_no_fields_is_refused(carded: tuple[Path, str]) -> None:
    root, task_id = carded
    with pytest.raises(BadRequest):
        edit(root, task_id, actor="dev:berna")


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_a_closed_card_refuses_to_be_rewritten(carded: tuple[Path, str], status: str) -> None:
    """The log is the record of what was delivered. Rewriting the spec of finished work
    rewrites that record, so the door is shut and the message names the way through."""
    root, task_id = carded
    if status == "done":
        next_task(root, actor="dev:berna")          # `done` needs the lease the machine demands
    update(root, task_id, actor="dev:berna", status=status, comment="Not needed.",
           no_code=True)
    assert ask(root, task_id)["task"]["status"] == status

    with pytest.raises(BadRequest, match="closed cards are history"):
        edit(root, task_id, spec="too late", actor="dev:berna")


def test_an_older_edit_does_not_clobber_a_newer_local_one(carded: tuple[Path, str]) -> None:
    """Newer-wins, from the same arbitrator `_status` uses. Without it, importing a log
    that happened to contain an old edit would silently undo a correction made since."""
    root, task_id = carded
    edit(root, task_id, spec="the newest brief", actor="dev:berna")
    stale = build(task=task_id, actor="dev:ana", kind="edited", ts=1.0,
                  body={"field": "spec", "from": "old brief", "to": "a stale brief"})

    with Store(root) as store:
        assert replay.apply(store, [stale]) == 0
    assert ask(root, task_id)["task"]["spec"] == "the newest brief"


def test_an_edit_travels_to_another_clone_and_both_converge(tmp_path: Path) -> None:
    """The point of an event log: Ana fixes the brief, Berna's board shows the fix.

    Through a real bare remote rather than by copying rows, because the whole path — export,
    git, import, replay — is what was broken when replay knew nothing about a kind.
    """
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(origin))
    ana, berna = tmp_path / "ana", tmp_path / "berna"
    for who, email in ((ana, "ana@example.com"), (berna, "berna@example.com")):
        git(tmp_path, "clone", "-q", str(origin), str(who))
        git(who, "config", "user.email", email)
        git(who, "config", "user.name", who.name)
        init(who)
        open_chapter(who, "the chapter these tests plan into",
                     actor="dev:berna")

    task_id = plan(ana, [{"title": "Parse the header", "spec": "old brief"}],
                   actor="dev:ana")["created"][0]["id"]
    sync(ana)
    git(ana, "add", "-A")
    git(ana, "commit", "-q", "-m", "plan the work")
    git(ana, "push", "-q", "origin", "main")

    git(berna, "fetch", "-q", "origin")
    git(berna, "reset", "-q", "--hard", "origin/main")
    sync(berna)
    assert ask(berna, task_id)["task"]["spec"] == "old brief"

    edit(ana, task_id, title="Parse the header, with continuations", spec="the real brief",
         priority=0, actor="dev:ana")
    sync(ana)
    git(ana, "add", "-A")
    git(ana, "commit", "-q", "-m", "fix the brief")
    git(ana, "push", "-q", "origin", "main")

    git(berna, "fetch", "-q", "origin")
    git(berna, "reset", "-q", "--hard", "origin/main")
    report = sync(berna)

    assert report.applied >= 3, "three fields changed; three events should have landed"
    theirs, mine = ask(ana, task_id)["task"], ask(berna, task_id)["task"]
    assert mine["spec"] == theirs["spec"] == "the real brief"
    assert mine["title"] == theirs["title"] == "Parse the header, with continuations"
    assert mine["priority"] == theirs["priority"] == 0
    assert [e["kind"] for e in all_events(berna)].count("edited") == 3


def test_a_card_planned_before_chapters_existed_can_JOIN_one(tmp_path: Path) -> None:
    """The migration case, and the reason this field is editable at all.

    A board that predates 0.5.0 has cards carrying `""` — the fold that carries its FACTS forward
    was never going to touch them, because attaching a card to whichever chapter happens to be
    open on this clone would invent a fact about the past. So the first chapter such a board opens
    is born empty, and its counts describe none of the work under way. Measured on a real board
    before this existed: 63 cards, 6 of them open, and a brand-new chapter reading `no cards`.
    """
    init(tmp_path)
    # A `created` body with no `milestone` at all — the shape a pre-0.5.0 log actually holds, and
    # the only way to build one: `plan` refuses a board with no chapter, so the orphan cannot be
    # made through the door that exists today. Replay defaults the column to "" from this.
    orphan = "tk-legacy"
    with Store(tmp_path) as store:
        made = record(store, task=orphan, actor="dev:berna", kind="created",
                      body={"title": "planned before chapters", "spec": "s"})
        replay.apply(store, [made])
        assert store.tasks.need(orphan)["milestone"] == "", "it starts with no chapter"

    chapter = open_chapter(tmp_path, "El importador", goal="lo que sea", actor="dev:berna")
    edit(tmp_path, orphan, milestone=chapter["id"][:8], actor="dev:berna")

    with Store(tmp_path) as store:
        assert store.tasks.need(orphan)["milestone"] == chapter["id"]
    assert "edited" in kinds_on(tmp_path, orphan), "and the move is in the log, like any edit"


def test_a_card_cannot_move_into_a_chapter_that_is_CLOSED(carded: tuple[Path, str]) -> None:
    """The one rule this shares with `--carry` rather than with `plan`.

    Planning may name any chapter that exists; MOVING existing work may not, because a reached
    chapter holding an open card is one of two lies — either the chapter was not reached or the
    card is not open. The refusal names both ways out, the way every refusal here has to.
    """
    root, card = carded
    from taskops.usecases.milestone import listing, verify

    closed = listing(root)["milestones"][0]
    second = open_chapter(root, "el que sigue", actor="dev:berna")
    edit(root, card, milestone=second["id"], actor="dev:berna")     # out of the one being closed
    verify(root, closed["id"], actor="dev:berna")

    with pytest.raises(BadRequest) as refusal:
        edit(root, card, milestone=closed["id"], actor="dev:berna")

    assert "reached" in str(refusal.value)
    assert "milestone start" in str(refusal.value), "and it names the way out"


def test_a_chapter_that_does_not_exist_is_refused_by_NAME(carded: tuple[Path, str]) -> None:
    """A typo'd id must not silently land a card in nothing — that is the state this whole card
    exists to get a board out of."""
    root, card = carded

    with pytest.raises(BadRequest) as refusal:
        edit(root, card, milestone="deadbeef", actor="dev:berna")

    assert "deadbeef" in str(refusal.value) and "milestone list" in str(refusal.value)


def test_clearing_a_card_s_chapter_is_refused(carded: tuple[Path, str]) -> None:
    """`--reviewer ""` clears, and this deliberately does not: a card belongs to exactly ONE
    milestone, so "no chapter" is not a state anybody may ask for — it is only the shape a card
    written before chapters existed arrives in."""
    root, card = carded

    with pytest.raises(BadRequest) as refusal:
        edit(root, card, milestone="   ", actor="dev:berna")

    assert "exactly one milestone" in str(refusal.value)


def test_a_CLOSED_card_can_still_be_filed_under_a_chapter(carded: tuple[Path, str]) -> None:
    """The half of the refusal that was too wide, and the reason a migrated board could not be
    tidied: every card it ever finished is closed AND has no chapter, so refusing both left the
    board's one chapter sitting beside a bucket holding all of its history.

    Filing says WHICH chapter the work was delivered in. It rewrites nothing about what was
    delivered, which is what the refusal is actually protecting.
    """
    root, card = carded
    from taskops.usecases.milestone import open_chapter

    next_task(root, task=card, actor="dev:berna")
    update(root, card, status="done", no_code=True, comment="shipped", actor="dev:berna")
    second = open_chapter(root, "el capitulo siguiente", actor="dev:berna")

    edit(root, card, milestone=second["id"], actor="dev:berna")

    with Store(root) as store:
        moved = store.tasks.need(card)
        assert moved["milestone"] == second["id"]
        assert moved["status"] == "done", "and it is STILL closed — filing moves no card back"


def test_a_closed_card_still_refuses_every_OTHER_field(carded: tuple[Path, str]) -> None:
    """The other half, and the one a hurried fix opens by accident. Widening the exemption to the
    whole call would let somebody rewrite the spec of delivered work, which is the record a
    standup and a teammate's clone read back."""
    root, card = carded
    next_task(root, task=card, actor="dev:berna")
    update(root, card, status="done", no_code=True, comment="shipped", actor="dev:berna")

    for field in ({"spec": "rewritten"}, {"title": "renamed"}, {"priority": 0},
                  {"reviewer": "human"}, {"acceptance": "WHEN x THE SYSTEM SHALL y"}):
        with pytest.raises(BadRequest) as refusal:
            edit(root, card, actor="dev:berna", **field)          # type: ignore[arg-type]
        assert "history" in str(refusal.value), field


def test_filing_a_closed_card_and_rewriting_it_in_ONE_call_is_refused_WHOLE(
        carded: tuple[Path, str]) -> None:
    """A call naming both must not half-apply: the spec is refused, so the move goes with it. A
    partial write here would leave the caller told `no` about a card that did change."""
    root, card = carded
    from taskops.usecases.milestone import open_chapter

    next_task(root, task=card, actor="dev:berna")
    update(root, card, status="done", no_code=True, comment="shipped", actor="dev:berna")
    second = open_chapter(root, "el capitulo siguiente", actor="dev:berna")
    before = None
    with Store(root) as store:
        before = store.tasks.need(card)["milestone"]

    with pytest.raises(BadRequest):
        edit(root, card, milestone=second["id"], spec="rewritten", actor="dev:berna")

    with Store(root) as store:
        assert store.tasks.need(card)["milestone"] == before, "nothing moved"
