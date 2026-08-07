"""mcp/ — the tools an agent actually sees, and what comes back in the text."""

from __future__ import annotations

import io
import json
from typing import Any, Callable, Iterator
from pathlib import Path

import pytest

from taskops import _clock
from taskops.mcp import hello, tools, server
from taskops.board import LocalBoard
from tests.conftest import T0
from taskops._errors import Refused, BadRequest
from taskops.mcp.schema import SCHEMAS

BERNA = "dev:berna"
W1 = "agent:berna/w1"

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


def test_there_are_exactly_nine_tools_and_each_has_a_schema() -> None:
    assert len(tools.TOOLS) == 9  # the ninth is taskops_review (optional review)
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
    # docs/fan-out.md's D, delivered where planning happens rather than filed:
    # the seams land serialized BEFORE a fan-out, because a parallel worker
    # branches before they exist and its (correct) search finds nothing.
    for seam in ("ONE serialized card", "search finds nothing", "docs/fan-out.md"):
        assert seam in text
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


def test_a_milestones_criteria_travel_into_every_take_the_way_rules_do(
    repo: Path, boards: Any
) -> None:
    """docs/fan-out.md §4: every card was green and the milestone was not,
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
    travels in the call and lands in the `landed` event (docs/fan-out.md §8B)."""
    from taskops.gitwork import trees

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

    monkeypatch.setattr(trees, "land_milestone", lambda repo_, branch: ("main", "abc123"))
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
    answer = server.handle(dev, repo, json.dumps(request))
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
    answer = server.handle(dev, repo, json.dumps(request))
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
    answer = server.handle(dev, repo, json.dumps(request))
    assert answer is not None
    assert "taskops_board" in answer["result"]["content"][0]["text"]


# ── the protocol ────────────────────────────────────────────────────────────


def test_initialize_advertises_the_tools_and_the_instructions(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    answer = server.handle(
        dev, repo, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    )
    assert answer is not None
    result: Any = answer["result"]
    assert result["protocolVersion"] == hello.PROTOCOL
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert "ORCHESTRATOR" in result["instructions"]


def test_a_notification_gets_no_answer_at_all(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    line = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert server.handle(dev, repo, line) is None


def test_the_loop_answers_one_line_per_request(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    server.serve(dev, repo, io.StringIO("\n".join(lines) + "\n"), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, 2]  # the notification produced nothing
    assert len(answers[1]["result"]["tools"]) == 9


def test_junk_on_the_wire_is_a_parse_error_not_a_crash(repo: Path, boards: Any) -> None:
    dev = boards(BERNA)
    answer = server.handle(dev, repo, "{not json")
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
