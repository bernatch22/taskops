"""The context layer: what stays in force, what falls out, and what two clones agree on.

Four properties earn their test here, and each one is a way the layer would fail SILENTLY:
a supersede that ate its predecessor, a slice that dropped a standing decision, a retire that
deleted, and a tie two machines broke differently. None of them raise; they just make the
next agent work from something slightly wrong, which is the whole failure mode the context
layer exists to remove.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK
from taskops.contracts.slice import Chapters
from taskops.engine.log import build
from taskops.storage import Store
from taskops.storage.context import facts
from taskops.usecases import next_task, update
from taskops.usecases._contextslice import for_task, in_force
from taskops.usecases._contextviews import context_for, history, show
from taskops.usecases.context import retire, state
from taskops.usecases.plan import plan
from taskops.usecases.session import brief

NEVER = "never Co-Authored-By in a commit"

NO_CHAPTERS = Chapters(active=[], planned=[], counts={})
"""The milestone side of a slice, empty. The pure tests below are about the OTHER two dimensions
of scope — subject and owner — so they hand the chapter dimension nothing rather than a board."""


def test_a_new_objective_supersedes_without_erasing(root: Path) -> None:
    """Superseding is a NEWER event, never an edit of the old one. `show` moves on; the log
    remembers — which is the whole reason this is a log and not a config file.

    Read from `yours` and stated with an OWNER, because 0.5.0 has no such thing as the project's
    objective: the project's north is a milestone, and an objective belongs to one person. What is
    asserted is unchanged — the newer of two supersedes, and the older is still in the log.
    """
    first = state(root, "objective", "ship the context layer", owner="dev:ana")
    second = state(root, "objective", "ship 0.4", owner="dev:ana")
    current = show(root, actor="dev:ana", mine=True)["yours"]
    assert current is not None and current["id"] == second["id"]
    assert [f["text"] for f in history(root)] == [first["text"], second["text"]]


def test_a_retired_fact_leaves_show_and_stays_in_the_log(root: Path) -> None:
    """`retire` retires. An append-only log has no eraser, so the fact is still there,
    flagged — otherwise "why did we stop doing this" has no answer six months later."""
    fact = state(root, "decision", NEVER)
    retire(root, fact["id"])
    assert show(root)["decisions"] == []
    logged = history(root)
    assert [f["id"] for f in logged] == [fact["id"]]
    assert logged[0]["retired"] is True


def test_retiring_something_that_was_never_stated_says_so(root: Path) -> None:
    with pytest.raises(BadRequest) as raised:
        retire(root, "nope")
    assert "context log" in str(raised.value)


def test_an_UNSCOPED_decision_reaches_every_card_and_a_scoped_one_does_not(root: Path) -> None:
    """The distinction that survived `invariant`. That sort skipped the subject filter entirely,
    so a rule reached every card whatever its labels said; now the way to write one is to give it
    NO scope, and `_applies` lets it through on that basis alone.

    Both directions in one test on purpose. Asserting only that the unscoped one arrives would
    pass with the filter deleted, which is the mutation that makes every scoped decision global —
    and a worker reading three projects' worth of settled questions is the failure the slice
    exists to prevent."""
    state(root, "decision", NEVER)
    state(root, "decision", "SQL only in storage/", labels=["storage"])
    task = plan(root, [{"title": "render the board", "labels": ["ui"], "files": ["src/ui.py"]}])
    view = context_for(root, task["created"][0]["id"])
    assert [f["text"] for f in view["decisions"]] == [NEVER]


def test_a_decision_reaches_a_card_by_label_or_by_edit_surface(root: Path) -> None:
    """Two ways in, plus the unscoped fact that reaches everything: a decision with no scope
    is a project-wide one, and demanding a label for it would leave it reaching nothing."""
    state(root, "decision", "labelled", labels=["storage"])
    state(root, "decision", "by file", files=["src/taskops/storage"])
    state(root, "decision", "unscoped")
    state(root, "decision", "elsewhere", labels=["ui"], files=["src/ui.py"])
    made = plan(root, [{"title": "add a table", "labels": ["storage"],
                        "files": ["src/taskops/storage/_ddl.py"]}])
    texts = {f["text"] for f in context_for(root, made["created"][0]["id"])["decisions"]}
    assert texts == {"labelled", "by file", "unscoped"}


def test_two_clones_break_a_tie_the_same_way(root: Path, tmp_path: Path) -> None:
    """The split-brain test. Two machines add an objective offline at the SAME timestamp, then
    exchange events in opposite orders. `(ts, id)` decides, and `id` is the content hash — the
    same number on both — so both elect the same winner. Ordering by arrival would give each
    clone its own answer, and no supervisor could tell they disagreed.
    """
    at = 1_800_000_100.0
    mine = build(task=CONTEXT_TASK, actor="dev:a", kind=CONTEXT_KIND, ts=at,
                 body={"sort": "objective", "text": "ship 0.4"})
    theirs = build(task=CONTEXT_TASK, actor="dev:b", kind=CONTEXT_KIND, ts=at,
                   body={"sort": "objective", "text": "ship 0.5"})
    assert mine["ts"] == theirs["ts"] and mine["id"] != theirs["id"]
    other = tmp_path / "clone"
    (other / ".taskops").mkdir(parents=True)
    elected = [_winner_after(where, order)
               for where, order in ((root, [mine, theirs]), (other, [theirs, mine]))]
    assert elected[0] == elected[1]


def _winner_after(where: Path, events: list[dict]) -> str:  # type: ignore[type-arg]
    """Apply a log in one arrival order and report which objective is in force.

    Read from `objectives` — one entry per owner, and these two events carry none, so the tie is
    broken inside the same (empty) owner exactly as it was. The key `objective` is gone: an
    objective is somebody's now, and there is no single one for a board.
    """
    with Store(where) as store:
        for event in events:
            store.events.append(event)          # type: ignore[arg-type]
        elected = in_force(facts(store), NO_CHAPTERS)["objectives"]
    return elected[0]["text"] if elected else ""


def test_the_slice_is_pure_and_survives_a_card_with_no_scope() -> None:
    """`for_task` takes facts and a task, no store — which is why a card with neither labels
    nor files can be tested from literals, and why it still gets every unscoped fact."""
    live = [_fact("i", "decision"), _fact("d", "decision", labels=["ui"])]
    # `assignee` too: the slice now asks who holds the card, to hand them THEIR objective. A
    # literal standing in for a Task has to carry the fields a Task has — a hand-made one that
    # did not is a scar this repository already has.
    bare = {"labels": [], "files": [], "assignee": "", "milestone": ""}
    view = for_task(live, bare, NO_CHAPTERS)    # type: ignore[arg-type]
    assert [f["text"] for f in view["decisions"]] == ["i"]


def test_a_fact_with_no_text_is_refused(root: Path) -> None:
    with pytest.raises(BadRequest):
        state(root, "decision", "   ")


def test_an_unknown_sort_is_refused_before_anything_is_written(root: Path) -> None:
    with pytest.raises(BadRequest) as raised:
        state(root, "vibe", "be nice")
    assert "objective" in str(raised.value)


def _fact(name: str, sort: str, *, labels: list[str] | None = None, owner: str = "",
          ts: float = 1.0) -> dict:  # type: ignore[type-arg]
    # `level`/`milestone` are fields of `Fact`, so a literal standing in for one carries them.
    # `milestone=""` at the default level is the shape a fact written before chapters existed has,
    # and it reads as standing — which is what these tests need, since they hand no chapters.
    return {"id": name, "sort": sort, "text": name, "labels": labels or [], "files": [],
            "horizon": "", "owner": owner, "actor": "dev:a", "ts": ts, "retired": False,
            "milestone": "", "level": "milestone"}


# ---- the second dimension of scope: a fact can belong to ONE developer


def _owned(text: str, sort: str = "objective", *, owner: str = "", ts: float = 1.0) -> dict:  # type: ignore[type-arg]
    return _fact(text, sort, owner=owner, ts=ts)


def _card(assignee: str) -> dict:  # type: ignore[type-arg]
    """A Task literal carrying the fields the slice reads — `assignee` and `milestone` among them
    now. Empty chapter: these are about the OWNER dimension, not about which chapter a card is in."""
    return {"labels": [], "files": [], "assignee": assignee, "milestone": ""}


def test_a_worker_reads_an_UNOWNED_objective_AND_its_own() -> None:
    """Both, never one instead of the other — and the unowned one is a board written before 0.5.0.

    Nothing can write one now (`state` refuses an objective with no owner, because the project's
    north is a milestone), and that is exactly why this is worth pinning: an old board's facts may
    not vanish because a version changed. It arrives in `objectives`, where the renderer marks it
    `project`, and the reader's own still arrives in `yours`.
    """
    live = [_owned("ship the importer"), _owned("the parser", owner="dev:ana")]

    slice_ = for_task(live, _card("agent:ana/w1"), NO_CHAPTERS)  # type: ignore[arg-type]

    assert "ship the importer" in [f["text"] for f in slice_["objectives"]]
    assert slice_["yours"]["text"] == "the parser"


def test_a_slice_grows_by_ONE_however_many_developers_there_are() -> None:
    """THE property, and the reason `owner` is a filter and not a label. Past ~150-200 standing
    instructions compliance decays, so a page that grew with the size of the team would make
    every agent slightly worse every time somebody joined."""
    live = [_owned("ship it"), *[_owned(f"{who}'s week", owner=f"dev:{who}")
                                 for who in ("ana", "juan", "mirna")]]

    slice_ = for_task(live, _card("agent:ana/w1"), NO_CHAPTERS)  # type: ignore[arg-type]

    assert slice_["yours"]["text"] == "ana's week"
    assert len(slice_["objectives"]) == 2, "the unowned one and mine — not four"


def test_an_agent_reads_what_the_person_who_spawned_it_set() -> None:
    """`agent:ana/w1` and `dev:ana` are one person with two hands — the same comparison
    `reviewer: peer` makes, and the reason a worker inherits its developer's objective."""
    live = [_owned("the parser", owner="dev:ana")]
    assert for_task(live, _card("agent:ana/w3"), NO_CHAPTERS)["yours"] is not None  # type: ignore[arg-type]
    assert for_task(live, _card("dev:ana"), NO_CHAPTERS)["yours"] is not None       # type: ignore[arg-type]


def test_somebody_elses_fact_is_not_in_your_slice() -> None:
    """Every sort, one rule: an owned fact reaches that dev and nobody else. A note ana wrote
    for herself in juan's page is noise he cannot act on, and noise is what the slice exists
    to keep out."""
    live = [_owned("mine", "note", owner="dev:ana"),
            _owned("also mine", "decision", owner="dev:ana"),
            _owned("everyone's", "decision")]

    juan = for_task(live, _card("agent:juan/w1"), NO_CHAPTERS)   # type: ignore[arg-type]

    assert juan["notes"] == []
    assert [f["text"] for f in juan["decisions"]] == ["everyone's"]


def test_the_overview_shows_everybody_because_that_is_what_it_is_for() -> None:
    """`context show` answers "who is on what", which is the question somebody deciding who to
    hand a card to is asking. Filtering it to the caller would remove the only answer."""
    live = [_owned("ship it"), _owned("the parser", owner="dev:ana"),
            _owned("the migration", owner="dev:juan")]

    assert len(in_force(live, NO_CHAPTERS)["objectives"]) == 3
    assert in_force(live, NO_CHAPTERS)["yours"] is None, "an overview belongs to nobody"


def test_your_own_page_is_yours_alone() -> None:
    live = [_owned("ship it"), _owned("the parser", owner="dev:ana"),
            _owned("the migration", owner="dev:juan")]

    mine = in_force(live, NO_CHAPTERS, mine="ana")

    assert [f["text"] for f in mine["objectives"]] == ["ship it", "the parser"]
    assert mine["yours"]["text"] == "the parser"


def test_one_objective_per_owner_and_the_latest_wins_within_each() -> None:
    """A second objective supersedes the first — but only the one with the SAME owner. Stating
    yours used to replace the project's, so telling the board what you were on erased the
    reason anybody was doing it."""
    live = [_owned("old north", ts=1.0), _owned("new north", ts=2.0),
            _owned("ana old", owner="dev:ana", ts=1.0),
            _owned("ana new", owner="dev:ana", ts=2.0)]

    whole = in_force(live, NO_CHAPTERS)

    assert [f["text"] for f in whole["objectives"]] == ["new north", "ana new"]


def test_an_owner_nothing_can_parse_is_refused(root: Path) -> None:
    """Found by running `--mine`, twice, and it is the worst shape a bug can take.

    `dev_of` answers "" for anything it cannot read, so an unparseable owner filed the fact as
    the PROJECT's — and an objective is superseded by the newest one with the same owner. So
    `--mine` with a malformed id did not fail, did not warn, and ERASED the team's north from
    every worker's slice. Twice: first the literal string "me", then the bare dev name.
    """
    for bad in ("me", "berna", "dev:", "agent:nope"):
        with pytest.raises(BadRequest):
            state(root, "objective", "mine", owner=bad)
    assert state(root, "objective", "mine", owner="dev:ana")["owner"] == "dev:ana"


# ---- the seam: the slice a VERIFIER reads on a card somebody else handed over


def _routed_review(root: Path) -> tuple[str, str]:
    """Ana's card, handed to review, routed by the server to the other connected dev.

    Driven through the real verbs and not assembled by hand, because the whole bug lives in a
    field being OVERWRITTEN halfway along: `assignee` says `agent:ana/w1` at the claim and
    `dev:dos` after routing writes the reviewer into it. A literal Task would have to pick one,
    and picking the first is picking the state where the bug does not exist.
    """
    brief(root, actor="dev:ana", session="s-ana")
    brief(root, actor="dev:dos", session="s-dos")
    card = plan(root, [{"title": "t", "spec": "s", "reviewer": "peer",
                        "acceptance": ["WHEN handed over THE SYSTEM SHALL route it"]}],
                actor="dev:ana")["created"][0]["id"]
    next_task(root, task=card, actor="agent:ana/w1")
    routed = update(root, card, status="review", comment="over to you",
                    actor="agent:ana/w1")["routed_to"]
    return str(card), str(routed)


def test_a_review_slice_carries_the_AUTHORS_objective_and_not_the_REVIEWERS(root: Path) -> None:
    """The case the owner filter was missing, and the only one where the reader is not the
    author. A verifier judges work against what the person who wrote it was trying to do — so
    the slice for a card in review is the project's facts plus ANA's, even though by then the
    card is assigned to the dev the review was routed to.
    """
    state(root, "objective", "the parser", owner="dev:ana")
    state(root, "objective", "the importer", owner="dev:dos")

    card, routed = _routed_review(root)
    assert routed == "dev:dos", "the fixture must reach the state where `assignee` is a REVIEWER"
    slice_ = context_for(root, card)

    assert slice_["yours"]["text"] == "the parser", "the author's, not the reviewer's"
    # ONE objective and it is the author's. The project no longer has one to sit beside it — that
    # is the milestone, which this slice carries in `milestone`.
    assert {f["text"] for f in slice_["objectives"]} == {"the parser"}


def test_a_review_slice_still_grows_by_ONE_and_never_reaches_a_third_developer(
        root: Path) -> None:
    """The counterpart, and the property the whole owner filter exists for. Handing the author's
    facts to a verifier must not turn the slice into everybody's: a dev with nothing to do with
    this card is noise, and adding the reviewer's own on top would make it grow by two.
    """
    state(root, "decision", "never Co-Authored-By")
    state(root, "note", "ana's own scratchpad", owner="dev:ana")
    state(root, "note", "dos's own scratchpad", owner="dev:dos")
    state(root, "note", "tres is elsewhere", owner="dev:tres")
    state(root, "objective", "the migration", owner="dev:tres")

    slice_ = context_for(root, _routed_review(root)[0])

    assert [f["text"] for f in slice_["notes"]] == ["ana's own scratchpad"]
    assert [f["text"] for f in slice_["decisions"]] == ["never Co-Authored-By"]
    assert "the migration" not in {f["text"] for f in slice_["objectives"]}


# ---- what a board written by an OLDER taskops still says


def test_a_fact_written_as_an_invariant_is_read_as_a_decision(root: Path) -> None:
    """`invariant` was a fourth sort and is gone. A board that used it is not a board that loses
    its standing rules: the reader MAPS the retired sort instead of skipping it, which is the
    difference between "a newer taskops invented a sort" (skip — correct) and "this taskops
    retired one" (map — because skipping makes every rule on that board vanish from every slice,
    with no error anywhere).

    Written straight into the log, because that is the only way to produce the state: the use
    case cannot state a sort the type no longer has.
    """
    from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK
    from taskops.engine import record
    from taskops.usecases._project import project as opened

    with opened(root) as store:
        record(store, task=CONTEXT_TASK, actor="dev:ana", kind=CONTEXT_KIND,
               body={"sort": "invariant", "text": "no dependencies outside the stdlib",
                     "labels": ["core"], "files": [], "horizon": "", "owner": ""})

    seen = show(root)
    # PROJECT-level, and that is the mapping doing its job twice over: a body written before 0.5.0
    # carries no `level`, and the level it is read at decides the fact's LIFETIME. Reading it as
    # this chapter's would retire an old board's standing rules the moment somebody closed a
    # milestone they predate — so an unlevelled fact stands forever, which is what an invariant was.
    assert [f["text"] for f in seen["project_decisions"]] == ["no dependencies outside the stdlib"]
    # And its SCOPE is dropped. An invariant reached every card whatever its labels said, so a
    # remapped one that kept `core` would quietly stop reaching everything else — the meaning to
    # preserve is "reaches everything", not the field.
    assert seen["project_decisions"][0]["labels"] == []


def test_a_remapped_invariant_still_reaches_a_card_it_shares_nothing_with(root: Path) -> None:
    """THE point of dropping the scope, asserted where it shows: a card with unrelated labels."""
    from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK
    from taskops.engine import record
    from taskops.usecases._project import project as opened

    with opened(root) as store:
        record(store, task=CONTEXT_TASK, actor="dev:ana", kind=CONTEXT_KIND,
               body={"sort": "invariant", "text": NEVER, "labels": ["storage"], "files": [],
                     "horizon": "", "owner": ""})
    task = plan(root, [{"title": "render the board", "labels": ["ui"]}])

    view = context_for(root, task["created"][0]["id"])

    # `project_decisions`: an unlevelled body is the project's — see the test above for why that
    # is the only reading that does not silently retire an old board's rules.
    assert [f["text"] for f in view["project_decisions"]] == [NEVER]


def test_a_sort_a_NEWER_taskops_invented_is_still_skipped(root: Path) -> None:
    """The other half of the same branch, and it must not have moved: an unknown sort is dropped,
    because a teammate on a newer version writing one must not make this board unreadable."""
    from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK
    from taskops.engine import record
    from taskops.usecases._project import project as opened

    with opened(root) as store:
        record(store, task=CONTEXT_TASK, actor="dev:ana", kind=CONTEXT_KIND,
               body={"sort": "from-the-future", "text": "x", "labels": [], "files": [],
                     "horizon": "", "owner": ""})

    seen = show(root)
    assert seen["decisions"] == [] and seen["notes"] == [] and seen["objectives"] == []
