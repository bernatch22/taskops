"""mcp/ — the tools an agent actually sees, and what comes back in the text."""

from __future__ import annotations

import io
import json
import threading
from typing import Any, Callable, Iterator
from pathlib import Path

import pytest

from taskops import _clock
from taskops.mcp import hello, tools, server
from taskops.board import LocalBoard, RemoteBoard
from tests.conftest import T0
from tests.test_git import repo as git_repo
from taskops._errors import Refused, BadRequest
from taskops.gitwork import run, trees, remote as remote_mod, landing
from taskops.mcp.schema import SCHEMAS
from taskops.http.server import BoardServer, serve as http_serve

BERNA = "dev:berna"
W1 = "agent:berna/w1"
W2 = "agent:berna/w2"
REMOTE_BOARD = "facturador"

pytestmark = pytest.mark.usefixtures("clock")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".taskops").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def boards(repo: Path) -> Iterator[Callable[[str], LocalBoard]]:
    """Open as many client boards as the test needs; all of them get closed."""
    opened: list[LocalBoard] = []

    def factory(actor: str) -> LocalBoard:
        board = LocalBoard(repo / ".taskops" / "board", actor)
        opened.append(board)
        return board

    yield factory
    for board in opened:
        board.close()


def call(board: LocalBoard, repo: Path, name: str, **args: Any) -> str:
    return tools.call(board, repo, name, args, _clock.now())


def seeded(open_board: Callable[[str], LocalBoard]) -> tuple[LocalBoard, list[dict[str, Any]]]:
    """The worked example, with the whole card: spec, criteria, labels, an epic."""
    dev = open_board(BERNA)
    out = dev.call(
        "plan",
        {
            "milestone": "MVP facturador",
            "goal": "read a bank CSV and issue invoices with VAT",
            "tasks": [
                {
                    "title": "invoice model",
                    "spec": "S" * 4000,
                    "files": ["src/models.py"],
                    "criteria": ["amounts are Decimal, never float", "round half up, 2 places"],
                    "labels": ["backend", "money"],
                },
                {"title": "VAT", "spec": "compute it", "files": ["src/tax.py"], "after": 0},
                {
                    "title": "the reduced rate",
                    "spec": "10% for food",
                    "files": ["src/tax.py"],
                    "parent": 1,
                },
            ],
        },
    )
    return dev, out["cards"]


# ── the surface ─────────────────────────────────────────────────────────────


def test_there_are_exactly_eleven_tools_and_each_has_a_schema() -> None:
    """The count is a DOC that expires: eleven since the reports chapter added
    taskops_activity (the chapter-wide read) and taskops_filed (registering a
    committed narration). It is asserted so that `mcp/tools.py`'s docstring,
    ARCHITECTURE §6 and the README cannot drift from the table below them."""
    assert len(tools.TOOLS) == 11
    assert set(tools.BY_NAME) == set(SCHEMAS)
    for tool in tools.TOOLS:
        assert tool.schema["additionalProperties"] is False  # no silent extra arguments
        assert tool.description and tool.description[0].isupper()


def test_an_argument_the_schema_does_not_declare_can_never_be_sent() -> None:
    """`additionalProperties: False` is a wall in both directions: an argument
    the verb accepts but the schema omits is refused by the host, and the board
    never hears about it."""
    assert "mentions" in SCHEMAS["taskops_comment"]["properties"]
    # ...and saying something is NOT an update: the two tools stay apart, or a
    # card ends up with half its conversation filed as status reasons.
    assert "mentions" not in SCHEMAS["taskops_update"]["properties"]
    assert "comment" not in SCHEMAS["taskops_update"]["properties"]


def test_the_instructions_carry_the_whole_protocol() -> None:
    """This is layer 1 of the context injection — the replacement for five hooks."""
    text = server.INSTRUCTIONS
    for needed in ("ORCHESTRATOR", "WORKER", "taskops_take", "released", "never git switch"):
        assert needed in text
    # the ✉ has to be readable without a second document: what it means and
    # that answering on the card is what clears it. (Needles follow the 08-07
    # compression — the host truncates instructions at ~3.1k, so the protocol
    # had to shrink to leave the panorama room. Contract, not wording, pinned.)
    for mention in ("✉", "answer on that card and it clears", "no mark-as-read"):
        assert mention in text
    # The seam rule, delivered where planning happens rather than filed:
    # the seams land serialized BEFORE a fan-out, because a parallel worker
    # branches before they exist and its (correct) search finds nothing.
    for seam in ("ONE serialized card", "search finds nothing"):
        assert seam in text
    # …and its sibling (fan-out.md §11): a committed BUILD OUTPUT is rebuilt by
    # one card at the end, because N cards regenerating one artifact is N-1
    # guaranteed conflicts no matter how disjoint their sources are.
    for bundle in ("GENERATED artifact", "ONE card rebuilds it at the end"):
        assert bundle in text
    # …and the whole handshake must fit UNDER the measured truncation, panorama
    # included: hello.CAP is the ceiling and the protocol may not eat all of it.
    assert len(text) + 300 + 2 <= hello.CAP, "INSTRUCTIONS grew past the cap — the panorama dies"


# ── the dossier ─────────────────────────────────────────────────────────────


def test_the_card_carries_everything_v1_carried(repo: Path, boards: Any) -> None:
    """spec · acceptance criteria · labels · the epic RESOLVED · commits with their
    subjects · time worked. A card that shows less is a worker guessing more."""
    dev, cards = seeded(boards)
    subtask = cards[2]
    dev.call(
        "bind",
        {
            "task": subtask["id"],
            "sha": "a3f9c21beef",
            "subject": "feat: reduced rate",
            "files": ["src/tax.py"],
        },
    )
    dev.call("assign", {"tasks": [cards[1]["id"]]})  # somebody is now on src/tax.py too
    worker = boards(W1)
    text = call(worker, repo, "taskops_take", task=subtask["id"])

    assert "## Part of" in text and "VAT" in text and "compute it" in text  # the epic, resolved
    assert "a3f9c21b  feat: reduced rate  (src/tax.py)" in text  # not a column of hashes
    assert "## ⚠ Also touching these files" in text and cards[1]["id"] in text

    full = call(worker, repo, "taskops_card", task=cards[0]["id"])
    assert "## Acceptance criteria" in full
    assert "1. amounts are Decimal, never float" in full
    assert "#backend #money" in full


def test_the_sections_are_in_the_order_that_survives_skimming(repo: Path, boards: Any) -> None:
    """v1, verbatim: a collision warning below a long spec is a section an agent
    skims past, and the cost of missing it is two agents rewriting each other."""
    dev, cards = seeded(boards)
    dev.call("assign", {"tasks": [cards[1]["id"]]})  # somebody else is in src/tax.py
    first = boards("agent:berna/w9")
    first.call("take", {"task": cards[2]["id"]})
    first.call(
        "update",
        {"task": cards[2]["id"], "status": "released", "comment": "got to the rate table"},
    )
    worker = boards(W1)
    text = call(worker, repo, "taskops_take", task=cards[2]["id"])
    order = [
        text.index("## ⚠ Also touching these files"),
        text.index("## Resume"),
        text.index("## Part of"),
        text.index("## Spec"),
        text.index("## History"),
        text.index("## Your world"),
    ]
    assert order == sorted(order), "the spec must not bury what changes what you do first"


def test_take_renders_the_goal_the_spec_and_the_worktree(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    dev.call("assign", {"tasks": [cards[0]["id"]]})
    worker = boards(W1)
    text = call(worker, repo, "taskops_take", task=cards[0]["id"])

    assert "read a bank CSV" in text  # the milestone's goal travels with the card
    assert text.count("S" * 100) >= 1 and "S" * 4000 in text  # never truncated
    assert f".taskops/trees/{cards[0]['id']}" in text
    assert "Never `git switch`" in text
    assert text.strip().endswith("─")  # the pulse line closes every result


def test_the_previous_workers_note_is_shown_on_the_next_take(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    first = boards(W1)
    call(first, repo, "taskops_take", task=cards[0]["id"])
    call(
        first,
        repo,
        "taskops_update",
        task=cards[0]["id"],
        status="released",
        comment="got to rounding, the reduced rate is left",
    )
    second = boards("agent:berna/w2")
    text = call(second, repo, "taskops_take", task=cards[0]["id"])
    assert "Resume — where the last worker stopped" in text
    assert "the reduced rate is left" in text


def test_the_board_groups_read_as_moves(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    text = call(dev, repo, "taskops_board")
    assert "TAKE — ready → taskops_assign" in text
    assert "BLOCKED — waiting on a dependency" in text
    assert cards[0]["id"] in text


def test_a_mention_arrives_through_both_context_layers(repo: Path, boards: Any) -> None:
    """Layer 2 says which card and what was asked; layer 3 makes it impossible
    to miss without opening the board at all. Neither one is a hook."""
    dev, cards = seeded(boards)
    assert "✉" not in call(dev, repo, "taskops_board")  # silence when nothing is owed

    worker = boards(W1)
    worker.call("take", {"task": cards[0]["id"]})
    worker.call(
        "update",
        {"task": cards[0]["id"], "comment": "Decimal or float?", "mentions": [BERNA]},
    )

    text = call(dev, repo, "taskops_board")
    assert "MENTIONS — addressed to you, not yet answered" in text
    named = text[text.index("MENTIONS") : text.index("TAKE —")]
    assert cards[0]["id"] in named and W1 in named and "Decimal or float?" in named
    assert "invoice model" in named  # which card, by name — an id is not recognisable
    assert "✉ 1 mention for you" in text
    # …and on a result that is not the board: any call, any turn
    assert "✉ 1 mention for you" in call(dev, repo, "taskops_card", task=cards[1]["id"])


def test_mentions_are_ranked_above_the_card_that_went_quiet(repo: Path, boards: Any) -> None:
    """A question addressed to you by name usually cannot wait a turn; a card
    going quiet can."""
    dev, cards = seeded(boards)
    dev.call("assign", {"tasks": [cards[0]["id"]]})  # owned, nobody running it → STALLED
    worker = boards(W1)
    worker.call("update", {"task": cards[2]["id"], "comment": "which rate?", "mentions": [BERNA]})
    text = call(dev, repo, "taskops_board")
    assert text.index("MENTIONS —") < text.index("STALLED —")


def test_with_two_chapters_open_the_board_names_both(repo: Path, boards: Any) -> None:
    """Picking one would be a coin toss — v1 answered it differently in three places."""
    dev, _ = seeded(boards)
    dev.call(
        "plan",
        {"milestone": "Reports", "goal": "monthly numbers", "tasks": [{"title": "the report"}]},
    )
    text = call(dev, repo, "taskops_board")
    assert "2 open milestones" in text
    assert "MVP facturador" in text and "Reports" in text
    assert "pass milestone=<id> to focus one" in text


def waving(dev: Any) -> list[dict[str, Any]]:
    """Two ready cards that name the same concept with disjoint declared files —
    the two `gitwork/remote.py` cards of ARCHITECTURE.md §16, reproduced."""
    out = dev.call(
        "plan",
        {
            "milestone": "the forge",
            "goal": "link out to github",
            "tasks": [
                {"title": "links", "spec": "check `git remote get-url origin`", "files": ["a.py"]},
                {"title": "pushes", "spec": "we check `git remote get-url origin`", "files": ["b.py"]},
            ],
        },
    )
    return list(out["cards"])


def test_the_board_names_the_wave_under_take(repo: Path, boards: Any) -> None:
    """Advice where the fan-out is decided, not per-take after the dispatch."""
    dev = boards(BERNA)
    first, second = waving(dev)
    text = call(dev, repo, "taskops_board", milestone="the forge")
    listed = text[text.index("TAKE —") : text.index("─ ◆")]
    assert f"▸ safe to dispatch together: {first['id']}" in listed
    assert f"held: {second['id']} (names git remote get-url origin with {first['id']})" in listed


def test_one_ready_card_draws_no_wave_line(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    dev.call("assign", {"tasks": [cards[0]["id"]]})  # leaves exactly one ready card
    assert "safe to dispatch together" not in call(dev, repo, "taskops_board")


def test_an_assign_the_wave_holds_apart_warns_and_proceeds(repo: Path, boards: Any) -> None:
    """Rule 1 of the chapter: a warning is never a lock. The briefs carry the
    sentence, and both cards are assigned all the same."""
    dev = boards(BERNA)
    first, second = waving(dev)
    text = call(
        dev, repo, "taskops_assign", tasks=[first["id"], second["id"]], worktrees=False
    )
    assert f"⚠ the wave holds this apart from {first['id']}" in text
    assert "the same concept — git remote get-url origin" in text
    assert "nothing is blocked" in text
    # …and it went through: two briefs, two owners on the board.
    assert text.count("spawn one sub-agent with this") == 2
    cards = dev.call("board", {"milestone": "the forge"})["groups"]
    assert [row["assignee"] for row in cards["stalled"]] == ["agent:berna/w1", "agent:berna/w2"]


def test_an_assign_the_wave_leaves_alone_carries_no_warning(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    text = call(dev, repo, "taskops_assign", tasks=[cards[0]["id"]], worktrees=False)
    assert "the wave holds this apart" not in text


def test_dispatch_returns_a_self_contained_brief(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    text = call(dev, repo, "taskops_assign", tasks=[cards[0]["id"]], worktrees=False)
    for needed in (
        # identity travels IN the calls: the export only reaches the git hooks
        "Pass actor=agent:berna/w1 on EVERY taskops call",
        "export TASKOPS_ACTOR=agent:berna/w1",
        f"taskops_take task={cards[0]['id']} actor=agent:berna/w1",
        "status=released",
        "Never: git switch",
    ):
        assert needed in text


def test_a_take_carries_the_chapters_rules_and_the_room(repo: Path, boards: Any) -> None:
    """Everything an agent must know before its first edit, in ONE call: the
    milestone's goal AND its rules, the card, the whole thread, and who else is
    working right now. A rule read after building is a rewrite, so it sits
    ABOVE the spec — and the order is what this asserts, not just the presence.
    """
    dev = boards(BERNA)
    dev.call(
        "plan",
        {
            "milestone": "MVP",
            "goal": "invoice a bank CSV",
            "rules": ["Decimal, never float", "no migrations in this milestone"],
            "tasks": [{"title": "VAT", "spec": "the whole tax"}, {"title": "PDF", "spec": "render"}],
        },
    )
    mine, theirs = (c["id"] for c in dev.call("board", {})["groups"]["take"])
    dev.call("assign", {"tasks": [mine], "workers": ["w1"]})
    dev.call("assign", {"tasks": [theirs], "workers": ["w2"]})
    boards("agent:berna/w2").call("take", {"task": theirs})  # somebody else, live
    dev.call("update", {"task": mine, "comment": "start with the reduced rate"})

    text = call(boards(W1), repo, "taskops_take", task=mine)

    assert "invoice a bank CSV" in text  # the milestone's goal
    assert "Decimal, never float" in text  # ...and its rules
    assert "agent:berna/w2" in text and theirs in text  # who is working right now
    assert "start with the reduced rate" in text  # the thread, whoever wrote it
    # The ORDER is the design: both land above the spec, or an agent that stops
    # reading early has already started building against neither.
    assert text.index("Decimal, never float") < text.index("## Spec")
    assert text.index("Working right now") < text.index("## Spec")
    # ...and the room is the OTHERS. Your own card is the thing you are reading;
    # listing it back as "somebody is working on this" is noise that reads as a
    # collision. (A mutation check caught that nothing pinned this.)
    room = text[text.index("Working right now") : text.index("## Spec")]
    assert mine not in room and theirs in room


def test_saying_something_is_a_different_tool_from_changing_the_card(
    repo: Path, boards: Any
) -> None:
    """One verb underneath, two tools on top. An agent that wants to talk should
    not have to read about `no_code` and `after` to find out how, and a `note=`
    with no status would be a comment filed as a status reason."""
    dev, cards = seeded(boards)
    card = cards[0]["id"]
    w1 = boards(W1)

    # a worker says something on a card that is not its own, addressed to the dev
    call(w1, repo, "taskops_comment", task=card, text="I am in src/tax.py too", mentions=[BERNA])
    thread = call(dev, repo, "taskops_card", task=card)
    assert "I am in src/tax.py too" in thread

    # ...and the dev sees the ✉ without asking for it
    assert "mention" in call(dev, repo, "taskops_board")

    # update refuses to be used as a second door into that thread
    with pytest.raises(BadRequest, match="taskops_comment"):
        call(dev, repo, "taskops_update", task=card, note="just chatting")


# ── identity is per call, not per process ──────────────────────────────────


def test_a_spawned_worker_speaks_through_actor_on_the_call(repo: Path, boards: Any) -> None:
    """THE bug that froze the first real dispatch: sub-agents share the session's
    one MCP server, whose identity is the orchestrator's — the brief's `export`
    never reaches that process, so without actor= a worker can never take."""
    dev, cards = seeded(boards)
    dev.call("assign", {"tasks": [cards[0]["id"]], "workers": ["w1"]})

    # the same board the ORCHESTRATOR's server holds open, now speaking as w1
    text = call(dev, repo, "taskops_take", task=cards[0]["id"], actor=W1)
    assert "## Your world" in text
    assert dev.stores.live.holder(cards[0]["id"], _clock.now()) == W1  # w1's claim, not the dev's

    # ...and the whole worker cycle goes through the same door
    dev.call("bind", {"task": cards[0]["id"], "sha": "a1b2", "subject": "feat: model"})
    done = call(dev, repo, "taskops_update", task=cards[0]["id"], actor=W1,
                status="done", note="model + tests")
    assert "done" in done


def test_without_actor_the_refusal_says_to_pass_it(repo: Path, boards: Any) -> None:
    dev, cards = seeded(boards)
    with pytest.raises(Refused, match=r"actor=agent:<dev>/<name>"):
        call(dev, repo, "taskops_take", task=cards[0]["id"])


def test_every_tool_advertises_the_actor_argument() -> None:
    """The schema is how a worker DISCOVERS the override — a fix the tool hides
    is a fix only the person who wrote it can use."""
    for tool in tools.TOOLS:
        assert "actor" in tool.schema["properties"], tool.name


def test_merge_refuses_before_git_ever_runs_when_the_card_is_not_done(
    repo: Path, boards: Any
) -> None:
    """The old order merged FIRST and let the server refuse the record after —
    code integrated into ms/* that the board never said was merged."""
    dev, cards = seeded(boards)
    with pytest.raises(Refused, match="not done"):
        call(dev, repo, "taskops_merge", task=cards[0]["id"])
    assert not (repo / ".taskops" / "trees").exists()  # git never even started


def behind_by_one(
    repo: Path, boards: Any, *, card_file: str = "card.py"
) -> tuple[LocalBoard, str, str, str, Path]:
    """A done card with a commit of its own, one commit behind its chapter.

    The chapter adds `shared.py`; the card writes `card_file` — its own file in
    the clean case, `shared.py` in the conflicting one. That name is the ONLY
    difference between the two.
    """
    dev, cards = seeded(boards)
    card = cards[0]["id"]
    dev.call("assign", {"tasks": [card], "workers": ["w1"]})
    w1 = boards(W1)
    w1.call("take", {"task": card})
    dev.call("bind", {"task": card, "sha": "a1b2c3", "subject": "feat: model"})
    w1.call("update", {"task": card, "status": "done", "comment": "model + tests"})

    dossier = dev.call("card", {"task": card})
    stone_branch = str(dossier["milestone"]["branch"])
    card_branch = str(dossier["branch"])

    run.must("init", "-q", "-b", "main", str(repo))
    run.must("config", "user.email", "test@example.com", cwd=repo)
    run.must("config", "user.name", "Test", cwd=repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run.must("add", "README.md", cwd=repo)
    run.must("commit", "-q", "-m", "first", cwd=repo)

    # the chapter moves on; the card's branch is cut from where main was
    tree = trees.ensure_card(repo, card, card_branch, stone_branch)
    if card_file:
        (tree / card_file).write_text("VAT = 10\n", encoding="utf-8")
        run.must("add", "-A", cwd=tree)
        run.must("commit", "-q", "-m", "the card's own line", cwd=tree)
    integration = trees.integration_tree(repo, stone_branch)
    (integration / "shared.py").write_text("VAT = 21\n", encoding="utf-8")
    run.must("add", "-A", cwd=integration)
    run.must("commit", "-q", "-m", "chapter moves", cwd=integration)
    assert landing.behind(repo, stone_branch, card_branch) == 1
    return dev, card, stone_branch, card_branch, tree


def test_a_behind_but_clean_card_integrates_itself_in_one_call(
    repo: Path, boards: Any
) -> None:
    """The board used to DIAGNOSE this and refuse, printing two commands the
    human then executed unchanged — ~9 times in two days. When the diagnosis and
    the remedy are both the board's, refusing is toil, so the catch-up runs
    here: one taskops_merge call, no human git, and the chapter branch ends up
    carrying both the catch-up and the --no-ff integration merge."""
    dev, card, stone_branch, card_branch, tree = behind_by_one(repo, boards)

    out = call(dev, repo, "taskops_merge", task=card)

    assert stone_branch in out
    # the catch-up happened in the CARD's own worktree, unasked
    assert (tree / "shared.py").exists()
    card_log = run.must("log", "--format=%s", card_branch, cwd=repo).splitlines()
    assert any(line.startswith(f"Merge branch '{stone_branch}'") for line in card_log)
    # ...and the chapter carries the integration merge on top of it
    integration = trees.integration_tree(repo, stone_branch)
    assert (integration / "card.py").exists()
    assert f"merge {card}" in run.must("log", "--format=%s", cwd=integration).splitlines()
    assert any(  # the board recorded the integration, not just git
        e.get("kind") == "merged" for e in dev.call("events", {"task": card}).get("events", [])
    )


def test_a_catch_up_that_conflicts_names_both_the_distance_and_gits_own_words(
    repo: Path, boards: Any
) -> None:
    """Merged blind, a stale branch comes back as a conflict about a FILE with
    the real cause nowhere in it — that is why the refusal existed and why it
    still carries the behind-count. What it adds is git's own conflict list, and
    what it guarantees is that the worktree is left aborted-clean: no MERGE_HEAD
    for the worker to walk into."""
    dev, card, stone_branch, _branch, tree = behind_by_one(repo, boards, card_file="shared.py")

    with pytest.raises(Refused) as refusal:
        call(dev, repo, "taskops_merge", task=card)

    said = str(refusal.value)
    assert f"{card} is 1 commit behind {stone_branch}" in said  # counted, not just "behind"
    assert "shared.py" in said  # git's own conflict file
    assert f"cd {trees.card_tree(repo, card)} && git merge {stone_branch}" in said
    assert f"taskops_merge task={card} again" in said
    assert not _merging(tree)  # aborted clean
    assert run.git("status", "--porcelain", cwd=tree).out == ""


def test_a_conflict_refusal_names_the_worktree_not_a_departed_worker(
    repo: Path, boards: Any
) -> None:
    """It used to say "only the worker can resolve this, in its own worktree" —
    and by the time a card is done and its chapter has moved on, the worker is
    gone: the ORCHESTRATOR is the one holding the refusal. The move is the same
    either way, so the text names the PLACE (the card's worktree) and both roles
    instead of an actor who is usually not there."""
    dev, card, stone_branch, _branch, _tree = behind_by_one(
        repo, boards, card_file="shared.py"
    )

    with pytest.raises(Refused) as refusal:
        call(dev, repo, "taskops_merge", task=card)

    said = str(refusal.value)
    assert "only the worker" not in said
    assert str(trees.card_tree(repo, card)) in said
    assert "orchestrator or worker" in said


def _merging(tree: Path) -> bool:
    return run.git("rev-parse", "--verify", "--quiet", "MERGE_HEAD", cwd=tree).ok


def test_a_dirty_worktree_is_never_touched_and_gets_todays_refusal_verbatim(
    repo: Path, boards: Any
) -> None:
    """The card is done, but somebody may be mid-thought in its directory. Nothing
    is attempted, so the message is exactly the one from before the catch-up."""
    dev, card, stone_branch, card_branch, tree = behind_by_one(repo, boards)
    (tree / "scratch.py").write_text("half a thought\n", encoding="utf-8")
    before = run.git("status", "--porcelain", cwd=tree).out

    with pytest.raises(Refused) as refusal:
        call(dev, repo, "taskops_merge", task=card)

    assert str(refusal.value) == (
        f"{card} is 1 commit behind {stone_branch} — merge it in your own worktree first:\n"
        f"  cd {trees.card_tree(repo, card)} && git merge {stone_branch}\n"
        f"then taskops_merge task={card} again"
    )
    assert run.git("status", "--porcelain", cwd=tree).out == before  # untouched
    assert landing.behind(repo, stone_branch, card_branch) == 1  # not caught up either


def test_a_missing_worktree_is_refused_and_never_conjured(repo: Path, boards: Any) -> None:
    """A worktree is cut by assign, not by an integration. If it is gone, the
    board says what it said before and creates nothing."""
    dev, card, stone_branch, _branch, tree = behind_by_one(repo, boards)
    run.must("worktree", "remove", "--force", str(tree), cwd=repo)
    assert not tree.exists()

    with pytest.raises(Refused, match="behind"):
        call(dev, repo, "taskops_merge", task=card)

    assert not tree.exists()  # nothing conjured


def test_a_card_that_is_not_behind_takes_exactly_the_path_it_always_did(
    repo: Path, boards: Any
) -> None:
    """The catch-up is reachable only through `behind` — 0 commits behind and
    nothing new runs at all."""
    dev, card, stone_branch, card_branch, tree = behind_by_one(repo, boards)
    run.must("merge", "-q", "--no-edit", stone_branch, cwd=tree)
    head = run.must("rev-parse", "HEAD", cwd=tree)

    out = call(dev, repo, "taskops_merge", task=card)

    assert stone_branch in out
    assert run.must("rev-parse", "HEAD", cwd=tree) == head  # no second merge commit


def test_a_milestones_criteria_travel_into_every_take_the_way_rules_do(
    repo: Path, boards: Any
) -> None:
    """Every card was green and the milestone was not,
    because no worker ever saw what the WHOLE would be judged against. The
    chapter's criteria ride above the spec, next to its rules."""
    dev = boards(BERNA)
    out = dev.call(
        "plan",
        {
            "milestone": "MVP",
            "goal": "invoice a bank CSV",
            "criteria": ["the served page renders all three tabs against a real board"],
            "tasks": [{"title": "VAT", "spec": "the whole tax"}],
        },
    )
    assert out["milestone"]["criteria"] == [
        "the served page renders all three tabs against a real board"
    ]
    card = out["cards"][0]["id"]
    dev.call("assign", {"tasks": [card], "workers": ["w1"]})
    text = call(boards(W1), repo, "taskops_take", task=card)
    assert "the served page renders all three tabs" in text
    assert text.index("all three tabs") < text.index("## Spec")  # above, like a rule

    # ...and replaced WHOLE through update milestone=, exactly like rules
    dev.call("update", {"milestone": out["milestone"]["id"], "criteria": ["only this now"]})
    assert dev.stores.state()["milestones"][out["milestone"]["id"]]["criteria"] == [
        "only this now"
    ]


def test_landing_shows_the_chapters_criteria_and_the_human_answers_out_loud(
    repo: Path, boards: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate SHOWS the criteria and refuses until the human says they hold —
    nothing is judged by the machine, nothing stored as status: the answer
    travels in the call and lands in the `landed` event."""

    dev = boards(BERNA)
    out = dev.call(
        "plan",
        {
            "milestone": "MVP",
            "goal": "invoice a bank CSV",
            "criteria": ["all three tabs render"],
            "tasks": [{"title": "VAT", "spec": "the whole tax"}],
        },
    )
    stone, card = out["milestone"]["id"], out["cards"][0]["id"]
    dev.call("assign", {"tasks": [card], "workers": ["w1"]})
    w1 = boards(W1)
    w1.call("take", {"task": card})
    w1.call("update", {"task": card, "status": "dropped", "comment": "not needed after all"})

    with pytest.raises(Refused, match="criteria_met=true") as refusal:
        call(dev, repo, "taskops_merge", milestone=stone)
    assert "all three tabs render" in str(refusal.value)  # shown, not summarised
    assert not (repo / ".taskops" / "trees").exists()  # refused before git ran

    monkeypatch.setattr(landing, "land_milestone", lambda repo_, branch: ("main", "abc123"))
    call(dev, repo, "taskops_merge", milestone=stone, criteria_met=True)
    landed = [e for e in dev.stores.events("project") if e["body"].get("op") == "landed"]
    assert landed and landed[-1]["body"].get("criteria_met") is True  # on the record


def test_a_tool_bug_is_an_error_result_not_a_dead_server(
    repo: Path, boards: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stdio loop is the session's only door to the board: an exception that
    escapes a handler must come back as isError, never end the loop."""
    dev = boards(BERNA)

    def boom(*args: Any) -> str:
        raise RuntimeError("a bug in a handler")

    monkeypatch.setitem(
        tools.BY_NAME, "taskops_board", tools.BY_NAME["taskops_board"]._replace(run=boom)
    )
    request = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
               "params": {"name": "taskops_board", "arguments": {}}}
    answer = server.handle(server.Boards(dev, repo, BERNA), json.dumps(request))
    assert answer is not None
    result: Any = answer["result"]
    assert result["isError"] is True and "RuntimeError" in result["content"][0]["text"]


# ── refusals reach the agent ────────────────────────────────────────────────


def test_a_refusal_comes_back_as_readable_text_not_a_protocol_error(
    repo: Path, boards: Any
) -> None:
    dev, cards = seeded(boards)
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "taskops_take", "arguments": {"task": cards[0]["id"]}},
    }
    answer = server.handle(server.Boards(dev, repo, BERNA), json.dumps(request))
    assert answer is not None
    result: Any = answer["result"]
    assert result["isError"] is True
    assert "taskops_assign" in result["content"][0]["text"]  # the way out is in the message


def test_an_unknown_tool_lists_the_ones_that_exist(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "taskops_land", "arguments": {}},
    }
    answer = server.handle(server.Boards(dev, repo, BERNA), json.dumps(request))
    assert answer is not None
    assert "taskops_board" in answer["result"]["content"][0]["text"]


# ── the protocol ────────────────────────────────────────────────────────────


def test_initialize_advertises_the_tools_and_the_instructions(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    answer = server.handle(
        server.Boards(dev, repo, BERNA),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
    )
    assert answer is not None
    result: Any = answer["result"]
    assert result["protocolVersion"] == hello.PROTOCOL
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert "ORCHESTRATOR" in result["instructions"]


def test_a_notification_gets_no_answer_at_all(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    line = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert server.handle(server.Boards(dev, repo, BERNA), line) is None


def test_the_loop_answers_one_line_per_request(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    server.serve(server.Boards(dev, repo, BERNA), io.StringIO("\n".join(lines) + "\n"), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, 2]  # the notification produced nothing
    assert len(answers[1]["result"]["tools"]) == len(tools.TOOLS)


def test_junk_on_the_wire_is_a_parse_error_not_a_crash(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    answer = server.handle(server.Boards(dev, repo, BERNA), "{not json")
    assert answer is not None and answer["error"]["code"] == -32700


_ = T0


# ── review, through the tools ───────────────────────────────────────────────

R1 = "agent:berna/r1"


def reviewed(open_board: Callable[[str], LocalBoard]) -> tuple[LocalBoard, str]:
    """A chapter whose cards need review, with the first one handed IN."""
    dev = open_board(BERNA)
    cards = dev.call(
        "plan",
        {
            "milestone": "MVP facturador",
            "goal": "read a bank CSV and issue invoices with VAT",
            "reviews": True,
            "tasks": [{"title": "invoice model", "spec": "S" * 400, "files": ["src/models.py"]}],
        },
    )["cards"]
    return dev, str(cards[0]["id"])


def test_the_brief_of_a_review_card_says_the_exit_is_status_review(
    repo: Path, boards: Any
) -> None:
    """Or the worker's first attempt to close is a refusal it has to decode
    mid-flight — the brief is where the exit belongs."""
    dev, card = reviewed(boards)
    text = call(dev, repo, "taskops_assign", tasks=[card], worktrees=False)
    assert f'taskops_update task={card} actor={W1} status=review note="<what you did>"' in text
    assert "this card needs REVIEW" in text
    assert "status=done" not in text.split("Stuck or out of context")[0]


def test_taskops_review_claims_the_review_lease(repo: Path, boards: Any) -> None:
    """ONE door for the verifier, not two: `taskops_take` never claims a review
    (its schema has no such flag — a second surface over the same verb is how
    v1 grew duplicate channels), and `taskops_review task=` is claim + dossier.
    The worker keeps its own lease and stays reachable while the verifier reads."""
    assert "review" not in SCHEMAS["taskops_take"]["properties"]
    dev, card = reviewed(boards)
    worker = boards(W1)
    call(worker, repo, "taskops_take", task=card)
    call(worker, repo, "taskops_update", task=card, status="review", note="model + tests")

    verifier = boards(R1)
    text = call(verifier, repo, "taskops_review", task=card)
    assert "S" * 400 in text  # the full dossier, exactly like a take
    assert "Handed in by agent:berna/w1" in text
    board = dev.call("board", {})
    assert [r["holder"] for r in board["groups"]["reviewing"]] == [R1]
    assert dev.call("card", {"task": card})["lease"]["actor"] == W1  # the worker never let go


def test_the_dossier_shows_a_changes_verdict_above_the_spec(repo: Path, boards: Any) -> None:
    """A `changes` verdict changes what you do before you start: you fix, you do
    not rebuild. Below the spec it is a section an agent skims past."""
    dev, card = reviewed(boards)
    worker = boards(W1)
    call(worker, repo, "taskops_take", task=card)
    call(worker, repo, "taskops_update", task=card, status="review", note="model + tests")
    verifier = boards(R1)
    call(
        verifier,
        repo,
        "taskops_review",
        task=card,
        verdict="changes",
        note="_total() is float; make it Decimal, round half up",
    )

    text = call(worker, repo, "taskops_take", task=card)
    assert "## ⟳ Changes requested by the reviewer" in text
    assert "_total() is float; make it Decimal, round half up" in text  # verbatim
    assert text.index("Changes requested") < text.index("## Spec")
    assert 'status=review note="…"' in text  # the way back in, next to the verdict


def test_a_verdict_without_a_note_is_refused_with_the_way_out(repo: Path, boards: Any) -> None:
    dev, card = reviewed(boards)
    worker = boards(W1)
    call(worker, repo, "taskops_take", task=card)
    call(worker, repo, "taskops_update", task=card, status="review", note="model + tests")
    verifier = boards(R1)
    with pytest.raises(Refused, match='verdict=changes note="what to change"'):
        call(verifier, repo, "taskops_review", task=card, verdict="changes")
    with pytest.raises(BadRequest, match="'pass'"):
        call(verifier, repo, "taskops_review", task=card, verdict="ok", note="fine")


def test_taskops_review_is_declared_like_every_other_tool() -> None:
    schema = SCHEMAS["taskops_review"]
    assert set(schema["properties"]) >= {"task", "verdict", "note", "actor"}
    # ONE door for the verifier: take never grows a review flag again. Two tool
    # surfaces over the same verb is the duplicate-channel shape that broke v1.
    assert "review" not in SCHEMAS["taskops_take"]["properties"]
    assert "reviews" in SCHEMAS["taskops_plan"]["properties"]
    assert "review" in SCHEMAS["taskops_update"]["properties"]


def test_a_call_can_name_another_project(tmp_path: Path, repo: Path, boards: Any) -> None:
    """One MCP server per session used to mean one REACHABLE board: a second
    project answered nothing, so its work left through curl against the HTTP
    door — which dispatches verbs and therefore silently loses the git half
    (`assign` hands out a card and cuts no worktree). Found on the first real
    second board, 2026-08-08."""
    other = tmp_path / "elsewhere"
    (other / ".taskops").mkdir(parents=True)
    home = boards(BERNA)
    registry = server.Boards(home, repo, BERNA)

    # The default is unchanged: no repo_path is still this session's own board.
    here, root = registry.at("")
    assert here is home and root == repo

    # And a path inside another project resolves to ITS root, not to ours.
    there, elsewhere = registry.at(str(other))
    assert elsewhere == other
    assert there is not home
    # Twice is the same board, never two caches racing each other's writes.
    assert registry.at(str(other))[0] is there
    registry.close()


def test_repo_path_never_reaches_a_verb(repo: Path, boards: Any) -> None:
    """Where a call GOES is the server's question. A verb that saw `repo_path`
    would refuse it as an unknown argument."""
    seen: dict[str, Any] = {}

    def spy(_board: Any, _repo: Path, args: Any, _now: float) -> str:
        seen.update(args)
        return "ok"

    dev = boards(BERNA)
    request = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
               "params": {"name": "taskops_board",
                          "arguments": {"repo_path": str(repo), "milestone": "ms-1"}}}
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(tools.BY_NAME, "taskops_board", tools.BY_NAME["taskops_board"]._replace(run=spy))
        server.handle(server.Boards(dev, repo, BERNA), json.dumps(request))
    assert "milestone" in seen and "repo_path" not in seen


# ── code travels by git, and the board is REMOTE ────────────────────────────
#
# The point of this section is the pair: the board answers over a socket and the
# git runs HERE, in the process that has the repo. A LocalBoard cannot show that
# — the two halves live in the same process and a server-side push would look
# identical. The server never gains a repo, a clone, or a credential; it hears
# `done`, and the client that asked makes the branch visible on origin.


@pytest.fixture()
def remote_pair(tmp_path: Path) -> Iterator[tuple[BoardServer, Path, Path]]:
    """A real HTTP board on a real port, a real work repo, a real bare origin."""
    httpd = http_serve(tmp_path / "boards", "127.0.0.1", 0)
    httpd.mounts.create(REMOTE_BOARD)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    root = git_repo(tmp_path)
    bare = tmp_path / "origin.git"
    run.must("init", "-q", "--bare", str(bare))
    run.must("remote", "add", "origin", str(bare), cwd=root)
    yield httpd, root, bare
    httpd.shutdown()
    httpd.server_close()


def remote_client(httpd: BoardServer, actor: str, subject: str | None = None) -> RemoteBoard:
    token, _ = httpd.mounts.credentials.mint(subject or actor, REMOTE_BOARD, _clock.now())
    return RemoteBoard(f"http://127.0.0.1:{httpd.server_address[1]}/{REMOTE_BOARD}", token, actor)


def card_on(httpd: BoardServer, root: Path) -> tuple[RemoteBoard, RemoteBoard, str, str]:
    """Plan → assign → take → a real commit on the card's own branch, bound.

    Everything up to the moment `done` becomes possible, over the wire.
    """
    dev = remote_client(httpd, BERNA)
    worker = remote_client(httpd, W1, subject=BERNA)
    cards = dev.call(
        "plan",
        {
            "milestone": "MVP facturador",
            "goal": "read a bank CSV",
            "tasks": [{"title": "invoice model", "spec": "the Invoice dataclass"}],
        },
    )["cards"]
    card = cards[0]["id"]
    dev.call("assign", {"tasks": [card], "workers": ["w1"], "worktrees": False})
    worker.call("take", {"task": card})
    tree = trees.ensure_card(root, card, card, "")
    (tree / "models.py").write_text("class Invoice: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "feat: model", cwd=tree)
    sha = run.must("rev-parse", "HEAD", cwd=tree)
    worker.call("bind", {"task": card, "sha": sha, "subject": "feat: model"})
    return dev, worker, card, sha


def on_origin(bare: Path, branch: str) -> str:
    result = run.git("rev-parse", "--verify", branch, cwd=bare)
    return result.out if result.ok else ""


def test_a_done_accepted_by_a_remote_board_pushes_the_card_branch_to_origin(
    remote_pair: tuple[BoardServer, Path, Path],
) -> None:
    """How code travels between two devs now that the server is an events API.

    The board learns the sha; the branch reaches origin; the other dev fetches
    it into their OWN clone and reads the diff there. Nothing about the objects
    passes through taskops — which is exactly why this has to be pinned against
    a board that is genuinely somewhere else.
    """
    httpd, root, bare = remote_pair
    dev, worker, card, sha = card_on(httpd, root)
    assert not on_origin(bare, card)  # nothing pushed by taking or committing

    text = tools.call(worker, root, "taskops_update",
                      {"task": card, "status": "done", "note": "model + tests"}, _clock.now())

    assert "done" in text
    assert on_origin(bare, card) == sha  # `git fetch origin tk-<id>` now finds it
    assert dev.call("card", {"task": card})["state"] == "done"  # and the board has the sha


def test_a_done_the_remote_board_refuses_pushes_nothing(
    remote_pair: tuple[BoardServer, Path, Path],
) -> None:
    """The refusal travels as an exception out of `board.call`, so the push below
    it is not skipped by a check — it is unreachable. A card closed by somebody
    who does not hold it must leave no trace anywhere, origin included."""
    httpd, root, bare = remote_pair
    _dev, _worker, card, _sha = card_on(httpd, root)
    stranger = remote_client(httpd, W2, subject=BERNA)

    with pytest.raises(Refused, match="agent:berna/w1"):
        tools.call(stranger, root, "taskops_update",
                   {"task": card, "status": "done", "note": "not mine"}, _clock.now())

    assert not on_origin(bare, card)


def test_with_no_origin_the_card_still_closes_and_nothing_is_pushed(
    tmp_path: Path,
) -> None:
    """The whole feature's switch is `git remote get-url origin`. Without one,
    the board move is untouched and git is never even asked to push — a push is
    never a gate, so its absence can never be one either."""
    httpd = http_serve(tmp_path / "boards", "127.0.0.1", 0)
    httpd.mounts.create(REMOTE_BOARD)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        root = git_repo(tmp_path)  # no origin added
        _dev, worker, card, _sha = card_on(httpd, root)
        ran: list[tuple[str, ...]] = []
        real = run.git

        def spy(*args: str, **kwargs: Any) -> Any:
            ran.append(args)
            return real(*args, **kwargs)

        remote_mod.run.git = spy  # type: ignore[assignment]
        try:
            text = tools.call(worker, root, "taskops_update",
                              {"task": card, "status": "done", "note": "no origin here"},
                              _clock.now())
        finally:
            remote_mod.run.git = real  # type: ignore[assignment]

        assert "done" in text  # the board move happened
        assert not any(args[0] == "push" for args in ran)  # not attempted, not failed
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_chapter_whose_cards_are_all_integrated_can_land(
    repo: Path, boards: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`groups.done` is FINISHED work already in the milestone branch — neither
    unfinished nor unintegrated, which is the only thing this gate is about.

    It was added to the payload so closed cards stay visible (a chapter's
    history used to exist on no screen), and the gate read the new group as a
    reason to refuse: the first card you integrated blocked the landing
    permanently, so no chapter could ever land again. Found by landing a real
    chapter, 2026-08-08."""

    dev = boards(BERNA)
    out = dev.call(
        "plan",
        {"milestone": "MVP", "goal": "g", "tasks": [{"title": "VAT", "spec": "the whole tax"}]},
    )
    stone, card = out["milestone"]["id"], out["cards"][0]["id"]
    dev.call("assign", {"tasks": [card], "workers": ["w1"]})
    w1 = boards(W1)
    w1.call("take", {"task": card})
    w1.call("update", {"task": card, "status": "done", "no_code": True, "comment": "done"})
    dev.call("merged", {"task": card, "sha": "9c2f"})  # integrated: it moves to `done`

    assert [c["id"] for c in dev.call("board", {"milestone": stone})["groups"]["done"]] == [card]

    monkeypatch.setattr(landing, "land_milestone", lambda *_: ("master", "abc123"))
    text = call(dev, repo, "taskops_merge", milestone=stone)
    assert "master" in text  # it landed; the settled card was not read as open work


# ── one call integrates the chapter ─────────────────────────────────────────


def three_done(repo: Path, boards: Any, *, clash: bool = False) -> tuple[
    LocalBoard, list[str], str, dict[str, Path]
]:
    """Three done cards, each one commit behind its chapter.

    `behind_by_one` one card wider, and deliberately not folded into it: that
    helper is the single-card catch-up's own fixture and its shape (one card,
    one file name knob) is what those tests read. With `clash`, the SECOND card
    writes the same file the chapter did, so its catch-up conflicts — the batch
    stops in the middle rather than at either end.
    """
    dev, cards = seeded(boards)
    ids = [str(c["id"]) for c in cards]
    dev.call("assign", {"tasks": ids, "workers": ["w1", "w2", "w3"]})
    for n, card in enumerate(ids, 1):
        worker = boards(f"agent:berna/w{n}")
        worker.call("take", {"task": card})
        dev.call("bind", {"task": card, "sha": f"a1b2c{n}", "subject": f"feat: {n}"})
        worker.call("update", {"task": card, "status": "done", "comment": "done"})

    run.must("init", "-q", "-b", "main", str(repo))
    run.must("config", "user.email", "test@example.com", cwd=repo)
    run.must("config", "user.name", "Test", cwd=repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run.must("add", "README.md", cwd=repo)
    run.must("commit", "-q", "-m", "first", cwd=repo)

    stone_branch = str(dev.call("card", {"task": ids[0]})["milestone"]["branch"])
    cut: dict[str, Path] = {}
    for n, card in enumerate(ids, 1):
        branch = str(dev.call("card", {"task": card})["branch"])
        tree = trees.ensure_card(repo, card, branch, stone_branch)
        name = "shared.py" if clash and n == 2 else f"card{n}.py"
        (tree / name).write_text(f"X = {n}\n", encoding="utf-8")
        run.must("add", "-A", cwd=tree)
        run.must("commit", "-q", "-m", f"card {n}", cwd=tree)
        cut[card] = tree

    integration = trees.integration_tree(repo, stone_branch)
    (integration / "shared.py").write_text("VAT = 21\n", encoding="utf-8")
    run.must("add", "-A", cwd=integration)
    run.must("commit", "-q", "-m", "chapter moves", cwd=integration)
    return dev, ids, stone_branch, cut


class TestOneCallIntegratesTheChapter:
    """`taskops_merge tasks=[…]` and `done=true` — the batch. It adds no second
    merge implementation: every card goes through the single-card path, catch-up
    included, so a batch of one is byte-for-byte a `task=` call."""

    def test_tasks_integrate_in_order_through_the_single_card_path(
        self, repo: Path, boards: Any
    ) -> None:
        dev, ids, stone_branch, _cut = three_done(repo, boards)

        out = call(dev, repo, "taskops_merge", tasks=ids)

        assert "3 of 3 integrated" in out
        for card in ids:  # per card, and a sha, not just a count
            assert f"{card}  merged " in out
        integration = trees.integration_tree(repo, stone_branch)
        subjects = run.must("log", "--format=%s", cwd=integration).splitlines()
        # the chapter carries one --no-ff merge per card, newest first: the ORDER given
        assert [s for s in subjects if s.startswith("merge tk-")] == [
            f"merge {card}" for card in reversed(ids)
        ]
        for n in (1, 2, 3):  # each card's own file arrived
            assert (integration / f"card{n}.py").exists()
        for card in ids:  # ...and the board recorded every one of them
            events = dev.call("events", {"task": card})["events"]
            assert any(e.get("kind") == "merged" for e in events)

    def test_done_true_resolves_the_merge_group_itself(self, repo: Path, boards: Any) -> None:
        """The orchestrator names nothing: the cards are the ones the board
        already groups under MERGE, in that group's own order."""
        dev, ids, stone_branch, _cut = three_done(repo, boards)
        assert [r["id"] for r in dev.call("board", {})["groups"]["merge"]] == ids

        out = call(dev, repo, "taskops_merge", done=True)

        assert "3 of 3 integrated" in out
        integration = trees.integration_tree(repo, stone_branch)
        subjects = run.must("log", "--format=%s", cwd=integration).splitlines()
        assert [s for s in subjects if s.startswith("merge tk-")] == [  # the GROUP's order
            f"merge {card}" for card in reversed(ids)
        ]
        assert not dev.call("board", {})["groups"]["merge"]  # the group emptied itself

    def test_a_failure_stops_the_batch_there_and_a_re_run_continues(
        self, repo: Path, boards: Any
    ) -> None:
        """Partial completion is real and not rollback-able — each merge that went
        through is a --no-ff commit and a `merged` event. So the answer says which
        of the three happened, and the re-run picks up exactly where it stopped."""
        dev, ids, stone_branch, cut = three_done(repo, boards, clash=True)

        out = call(dev, repo, "taskops_merge", done=True)

        assert f"{ids[0]}  merged " in out
        # the refusal VERBATIM inside the report — head, git's own conflict file
        # and the tail that names where it gets resolved
        assert f"{ids[1]}  stopped: {ids[1]} is " in out
        assert f"behind {stone_branch}, and catching it up conflicts in:" in out
        assert "shared.py" in out
        assert "orchestrator or worker" in out
        assert f"{ids[2]}  not reached" in out
        assert "1 of 3 integrated" in out
        integration = trees.integration_tree(repo, stone_branch)
        assert (integration / "card1.py").exists()
        assert not (integration / "card3.py").exists()  # nothing past the stop

        # the worker resolves its own conflict, exactly as the refusal says
        tree = cut[ids[1]]
        run.git("merge", "--no-edit", stone_branch, cwd=tree)
        run.must("checkout", "--ours", "shared.py", cwd=tree)
        run.must("add", "shared.py", cwd=tree)
        run.must("commit", "-q", "--no-edit", cwd=tree)

        again = call(dev, repo, "taskops_merge", done=True)

        assert "2 of 2 integrated" in again  # the first card is no longer in the group
        assert f"{ids[1]}  merged " in again and f"{ids[2]}  merged " in again
        assert (integration / "card3.py").exists()

    def test_an_empty_merge_group_answers_honestly_and_errors_on_nothing(
        self, repo: Path, boards: Any
    ) -> None:
        dev, _cards = seeded(boards)
        assert "Nothing to integrate" in call(dev, repo, "taskops_merge", done=True)

    def test_tasks_with_no_card_in_it_names_both_spellings(
        self, repo: Path, boards: Any
    ) -> None:
        dev, _cards = seeded(boards)
        with pytest.raises(BadRequest) as refusal:
            call(dev, repo, "taskops_merge", tasks=[])
        assert "tasks=[tk-a, tk-b]" in str(refusal.value)
        assert "done=true" in str(refusal.value)

    def test_both_spellings_are_declared_where_a_caller_discovers_them(self) -> None:
        props = SCHEMAS["taskops_merge"]["properties"]
        assert {"task", "tasks", "done"} <= set(props)
        assert "tasks" in tools.BY_NAME["taskops_merge"].description


# ── a chapter lands over a moved trunk ──────────────────────────────────────

DOCS = ("ARCHITECTURE.md", "CLAUDE.md")


def chapter_ready_to_land(
    repo: Path, boards: Any, *, clash: bool = False, criteria: list[str] | None = None
) -> tuple[LocalBoard, str, str, Path]:
    """A FINISHED chapter — one card, done and already integrated — over a real
    repo whose trunk (`master`) has MOVED since the chapter was cut.

    `clash` reproduces the two-sided docs edit verbatim: the chapter and the
    trunk both rewrite ARCHITECTURE.md and CLAUDE.md, which is what conflicted
    twice in two days. Without it the trunk's commit is pure drift and the
    catch-up is clean. Returns (dev, milestone id, milestone branch, integration
    worktree).
    """
    run.must("init", "-q", "-b", "master", str(repo))
    run.must("config", "user.email", "test@example.com", cwd=repo)
    run.must("config", "user.name", "Test", cwd=repo)
    for name in DOCS:
        (repo / name).write_text(f"{name}: cut here\n", encoding="utf-8")
    run.must("add", "-A", cwd=repo)
    run.must("commit", "-q", "-m", "first", cwd=repo)

    dev = boards(BERNA)
    out = dev.call(
        "plan",
        {
            "milestone": "MVP",
            "goal": "invoice a bank CSV",
            "criteria": criteria or [],
            "tasks": [{"title": "VAT", "spec": "the whole tax"}],
        },
    )
    stone, card = str(out["milestone"]["id"]), str(out["cards"][0]["id"])
    dev.call("assign", {"tasks": [card], "workers": ["w1"]})
    w1 = boards(W1)
    w1.call("take", {"task": card})

    dossier = dev.call("card", {"task": card})
    stone_branch = str(dossier["milestone"]["branch"])
    tree = trees.ensure_card(repo, card, str(dossier["branch"]), stone_branch)
    (tree / "card.py").write_text("VAT = 21\n", encoding="utf-8")
    if clash:  # the chapter legitimately rewrites the same two docs
        for name in DOCS:
            (tree / name).write_text(f"{name}: the chapter's line\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "card", cwd=tree)
    dev.call("bind", {"task": card, "sha": "a1b2c3", "subject": "feat: VAT"})
    w1.call("update", {"task": card, "status": "done", "comment": "done"})
    sha = landing.merge_card(repo, stone_branch, str(dossier["branch"]), card)
    dev.call("merged", {"task": card, "into": stone_branch, "sha": sha})

    # ...and NOW the trunk moves under it: another chapter landed.
    for name in DOCS:
        (repo / name).write_text(f"{name}: the trunk moved on\n", encoding="utf-8")
    run.must("add", "-A", cwd=repo)
    run.must("commit", "-q", "-m", "another chapter landed", cwd=repo)
    return dev, stone, stone_branch, trees.integration_tree(repo, stone_branch)


class TestAChapterLandsOverAMovedTrunk:
    """`gitmoves._land` — the landing gate catches the chapter up to a trunk that
    moved while it was in flight, on the same `catchup.catch_up` the single-card
    path uses. Gate first, catch-up second, land third."""

    def test_a_chapter_behind_a_clean_trunk_catches_up_and_lands_in_one_call(
        self, repo: Path, boards: Any
    ) -> None:
        """No human runs git: one call, and master carries both the trunk's own
        commit and the chapter."""
        dev, stone, stone_branch, tree = chapter_ready_to_land(repo, boards)
        assert landing.behind_trunk(repo, stone_branch) == ("master", 1)

        text = call(dev, repo, "taskops_merge", milestone=stone)

        assert "master" in text
        subjects = run.must("log", "--format=%s", cwd=repo).splitlines()
        assert f"land {stone_branch}" == subjects[0]
        assert "another chapter landed" in subjects  # the trunk's commit survived
        assert (repo / "card.py").exists()  # ...and so did the chapter's work
        # the catch-up happened in the integration worktree, not the checkout
        assert f"Merge branch 'master' into {stone_branch}" in run.must(
            "log", "--format=%s", cwd=tree
        ).splitlines()

    def test_the_two_sided_docs_conflict_refuses_and_master_is_untouched(
        self, repo: Path, boards: Any
    ) -> None:
        """The reproduction, verbatim: ARCHITECTURE.md and CLAUDE.md written by
        both sides. It still aborts and still refuses — what is new is only the
        behind-count, so the cause is in the sentence."""
        dev, stone, stone_branch, tree = chapter_ready_to_land(repo, boards, clash=True)
        before = run.must("rev-parse", "master", cwd=repo)

        with pytest.raises(Refused) as refusal:
            call(dev, repo, "taskops_merge", milestone=stone)

        said = str(refusal.value)
        assert f"{stone_branch} is 1 commit behind master" in said
        for name in DOCS:
            assert f"  {name}" in said
        assert "master is untouched" in said
        assert f"taskops_merge milestone={stone} again" in said
        assert run.must("rev-parse", "master", cwd=repo) == before  # byte for byte
        assert not run.dirty(tree)  # aborted, never left mid-merge for somebody to find
        assert not (tree / ".git").exists() or not (tree / "MERGE_HEAD").exists()

    def test_the_criteria_refusal_comes_before_any_git_runs(
        self, repo: Path, boards: Any
    ) -> None:
        """The chapter's criteria are the human's question and the catch-up is
        git: unanswered and behind, the criteria refusal wins and the integration
        worktree's HEAD has not moved."""
        dev, stone, stone_branch, tree = chapter_ready_to_land(
            repo, boards, criteria=["all three tabs render"]
        )
        before = run.must("rev-parse", "HEAD", cwd=tree)

        with pytest.raises(Refused, match="criteria_met=true") as refusal:
            call(dev, repo, "taskops_merge", milestone=stone)

        assert "all three tabs render" in str(refusal.value)
        assert run.must("rev-parse", "HEAD", cwd=tree) == before  # no merge ran

        call(dev, repo, "taskops_merge", milestone=stone, criteria_met=True)
        assert run.must("rev-parse", "HEAD", cwd=tree) != before  # answered: now it caught up

    def test_a_chapter_level_with_the_trunk_takes_todays_path_byte_for_byte(
        self, repo: Path, boards: Any
    ) -> None:
        dev, stone, stone_branch, tree = chapter_ready_to_land(repo, boards)
        run.must("merge", "--no-edit", "master", cwd=tree)  # already caught up by hand
        before = run.must("rev-parse", "HEAD", cwd=tree)
        assert landing.behind_trunk(repo, stone_branch) == ("master", 0)

        call(dev, repo, "taskops_merge", milestone=stone)

        assert run.must("rev-parse", "HEAD", cwd=tree) == before  # nothing was merged into it
        assert f"land {stone_branch}" == run.must("log", "--format=%s", cwd=repo).splitlines()[0]

    def test_a_dirty_integration_worktree_is_never_touched(
        self, repo: Path, boards: Any
    ) -> None:
        """Somebody may be mid-thought in there even though every card is done.
        Blocked is not a refusal of its own: the landing falls through to exactly
        today's behaviour and `land_milestone`'s own conflict message speaks."""
        dev, stone, stone_branch, tree = chapter_ready_to_land(repo, boards, clash=True)
        (tree / "scratch.txt").write_text("mid-thought\n", encoding="utf-8")
        run.must("add", "-A", cwd=tree)
        before = run.must("rev-parse", "HEAD", cwd=tree)

        with pytest.raises(Refused) as refusal:
            call(dev, repo, "taskops_merge", milestone=stone)

        assert f"{stone_branch} conflicts with master in:" in str(refusal.value)  # today's words
        assert "behind master" not in str(refusal.value)  # nothing was attempted
        assert run.must("rev-parse", "HEAD", cwd=tree) == before
        assert (tree / "scratch.txt").read_text(encoding="utf-8") == "mid-thought\n"


# ── the chapter's story, and registering a report ───────────────────────────


def test_taskops_activity_renders_a_chapter_card_by_card(repo: Path, boards: Any) -> None:
    """One tool result an orchestrator reads top to bottom: the chapter's goal
    and rules once, then a block per card with its state, its commits SIZED,
    and the count of the conversation it is not being shown."""
    dev, cards = seeded(boards)
    first = cards[0]["id"]
    dev.call("assign", {"tasks": [first], "worktrees": False})
    worker = boards(W1)
    worker.call("take", {"task": first})
    worker.call(
        "bind",
        {
            "task": first,
            "sha": "a1b2c3d4e5",
            "subject": "feat: the Invoice model",
            "files": ["src/models.py"],
            "numstat": {"src/models.py": [12, 3]},
        },
    )
    out = call(dev, repo, "taskops_activity")

    assert "read a bank CSV and issue invoices with VAT" in out  # the header, ONCE
    assert out.count("invoice model") == 1
    assert "a1b2c3d4  feat: the Invoice model  (src/models.py +12-3)" in out
    assert "events (depth=full)" in out  # the thread it is NOT showing, and the way in
    assert "S" * 4000 not in out  # …and no spec at the default depth
    assert "S" * 4000 in call(dev, repo, "taskops_activity", depth="full")


def test_taskops_filed_registers_a_committed_report_and_says_so_twice(
    repo: Path, boards: Any
) -> None:
    """The half that makes the chapter usable from a session: an agent writes
    the file, commits it, and registers it here. A repeat is not an error — the
    same path at the same sha is already on the board, and the tool says which."""
    dev, _ = seeded(boards)
    args = {
        "path": ".taskops/reports/mvp-facturador.md",
        "title": "What the MVP shipped",
        "sha": "9c2f1a",
    }
    first = call(dev, repo, "taskops_filed", **args)
    assert "What the MVP shipped" in first and ".taskops/reports/mvp-facturador.md" in first
    assert "already filed" not in first
    assert "already filed" in call(dev, repo, "taskops_filed", **args)
    # …and it is on the chapter's story from then on.
    assert "What the MVP shipped" in call(dev, repo, "taskops_activity")


def test_a_report_outside_the_reports_directory_is_refused_at_the_tool(
    repo: Path, boards: Any
) -> None:
    dev, _ = seeded(boards)
    with pytest.raises(Refused, match="is not a report path"):
        call(dev, repo, "taskops_filed", path="notes/story.md", title="t", sha="9c2f1a")
