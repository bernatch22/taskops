"""The milestone machine, tested from literals — no board, no store, no clock.

Table-driven like `test_machine.py`, and for the same reason: the whole value of a pure machine
is that "an agent may not close the chapter it reported" is three lines here instead of a fixture
with a server, two clones and an event log in it.
"""

from __future__ import annotations

import pytest

from taskops.contracts.milestone import OPEN_MILESTONE, STATES, MilestoneState
from taskops.engine.milestones import MOVES, allowed_from, move

AGENT = "agent:berna/one"
DEV = "dev:berna"
ID = "7c1a44b2"

LEGAL: tuple[tuple[MilestoneState, MilestoneState, str, str], ...] = (
    ("planned", "in_force", AGENT, ""),          # start — an agent plans and an agent begins
    ("planned", "in_force", DEV, ""),
    ("in_force", "review", AGENT, "shipped the importer"),
    ("in_force", "review", DEV, ""),
    ("in_force", "reached", DEV, ""),            # a person may verify with no report first
    ("in_force", "abandoned", DEV, "we are not doing invoices this quarter"),
    ("review", "reached", DEV, ""),
    ("review", "in_force", DEV, "tk-269195 is still open"),
    ("review", "abandoned", DEV, "the client withdrew"),
    ("planned", "abandoned", DEV, "superseded by the CSV chapter"),
)


@pytest.mark.parametrize(("state", "to", "actor", "note"), LEGAL)
def test_every_legal_move_is_allowed(state: MilestoneState, to: MilestoneState,
                                     actor: str, note: str) -> None:
    assert move(state, to, actor, note=note, milestone=ID) is None


ILLEGAL: tuple[tuple[MilestoneState, MilestoneState], ...] = (
    ("planned", "review"),        # nothing is reported before anybody starts
    ("planned", "reached"),       # and nothing is verified before anybody starts
    ("in_force", "planned"),      # un-starting would erase that work happened
    ("review", "planned"),
    ("reached", "in_force"),      # terminal: reopening makes the log say it finished twice
    ("reached", "review"),
    ("reached", "abandoned"),     # "we shipped it" may never become "we stopped"
    ("abandoned", "in_force"),
    ("abandoned", "planned"),
    ("abandoned", "reached"),     # nor the other way round
    ("review", "review"),         # a self-arrow is not a move
    ("in_force", "in_force"),
)


@pytest.mark.parametrize(("state", "to"), ILLEGAL)
def test_every_illegal_move_is_refused(state: MilestoneState, to: MilestoneState) -> None:
    """And refused to a DEV, so the refusal is about the arrow and never about the actor."""
    refusal = move(state, to, DEV, note="reason enough", milestone=ID)
    assert refusal, f"{state} -> {to} is not in the machine and must be refused"
    assert state in refusal, "a refusal that does not name the current state cannot be acted on"
    for target in allowed_from(state):
        assert target in refusal, "and it lists where the chapter CAN go, or the caller guesses"


def test_the_table_covers_every_state() -> None:
    """Anti-vacuum: a state missing from the table would be silently terminal, so every test
    about its arrows would pass by never running one."""
    assert set(MOVES) == set(STATES)


def test_the_terminal_states_are_terminal() -> None:
    assert allowed_from("reached") == ()
    assert allowed_from("abandoned") == ()


def test_an_illegal_move_out_of_a_closed_chapter_says_it_is_closed() -> None:
    """`allowed_from` is empty there, so the generic "it may only go to: " would trail off."""
    refusal = move("reached", "in_force", DEV, milestone=ID)
    assert refusal and "closed" in refusal


AGENT_MAY_NOT: tuple[tuple[MilestoneState, MilestoneState, str], ...] = (
    ("in_force", "reached", "done"),
    ("review", "reached", "done"),
    ("review", "in_force", "reject"),
    ("in_force", "abandoned", "cancel"),
    ("review", "abandoned", "cancel"),
    ("planned", "abandoned", "cancel"),
)


@pytest.mark.parametrize(("state", "to", "verb"), AGENT_MAY_NOT)
def test_done_reject_and_cancel_refuse_an_agent(state: MilestoneState, to: MilestoneState,
                                                verb: str) -> None:
    """The rule the whole model rests on: verifying is not reporting.

    `done` on a card already requires somebody who is not its author, and this is that rule one
    level up — without it a fleet of agents can close every card it wrote and the board would
    read "we shipped it" with nobody having looked.
    """
    refusal = move(state, to, AGENT, note="everything is finished", milestone=ID)
    assert refusal, f"an agent must not {verb} a milestone"
    assert AGENT in refusal, "the refusal names WHO is being refused"
    assert verb in refusal, "and which act it was"


def test_the_refusal_to_an_agent_names_the_way_out() -> None:
    """A refusal that says only no cost this repository four debugging sessions. This one has to
    leave the agent with a command to run, a person to wait for, and the reason its word is not
    enough — otherwise it spends its turns arguing with the board."""
    refusal = move("in_force", "reached", AGENT, milestone=ID)
    assert refusal
    assert "review" in refusal, "the verb it CAN use"
    assert ID in refusal, "with the id it takes"
    assert "person" in refusal, "who does the closing"
    assert "nothing is archived on your word" in refusal.lower(), "and why its report is not it"


def test_an_agent_may_start_and_report() -> None:
    """The other half of the same rule: planning, starting and reporting are an agent's job, so
    a guard there would leave the board describable only by a person."""
    assert move("planned", "in_force", AGENT, milestone=ID) is None
    assert move("in_force", "review", AGENT, note="done, I think", milestone=ID) is None


def test_a_rejection_with_no_findings_is_refused() -> None:
    """Sending a chapter back with nothing to act on means whoever reported it guesses, and the
    chapter comes back to review unchanged — a card's rejection rule, one level up."""
    refusal = move("review", "in_force", DEV, note="", milestone=ID)
    assert refusal and "no findings" in refusal
    assert "a criterion" in refusal, "and it says what would be enough"


def test_whitespace_is_not_a_finding() -> None:
    """A newline satisfies "not empty" and tells the reporter exactly as much as nothing did."""
    assert move("review", "in_force", DEV, note="  \n ", milestone=ID)


def test_a_rejection_that_says_what_is_missing_is_allowed() -> None:
    assert move("review", "in_force", DEV, note="tk-269195 has no test", milestone=ID) is None


def test_the_person_check_comes_before_the_findings_check() -> None:
    """Order, for the agent: told to write findings for a chapter it may not send back at all,
    it goes and does work that gets refused anyway."""
    refusal = move("review", "in_force", AGENT, note="", milestone=ID)
    # The verb is quoted as the COMMAND it is: "may not reject" was not a sentence either.
    assert refusal and "may not `reject`" in refusal


def test_two_milestones_may_be_in_force_at_once() -> None:
    """THE invariant that is deliberately absent.

    A team ships the importer and the invoices in the same fortnight. A rule allowing one chapter
    would force one of them to read `planned` while somebody is demonstrably working on it — a
    board lying about what is happening. Nothing in this machine counts the board, so starting a
    second chapter while a first is in force (or in review) is refused by nothing at all.
    """
    for other in OPEN_MILESTONE:
        assert other in ("in_force", "review")
        assert move("planned", "in_force", AGENT, milestone="second") is None
        assert move("planned", "in_force", DEV, milestone="third") is None


def test_a_malformed_actor_is_not_silently_a_person() -> None:
    """The guard folds through `identity.parse`, the one home for an actor id's shape. A lenient
    reader here would make `berna` — a plausible typo — a person with closing rights."""
    from taskops._errors import BadRequest

    with pytest.raises(BadRequest):
        move("review", "reached", "berna", milestone=ID)
