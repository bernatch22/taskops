"""Time on a card, and the four ways a fold like this lies.

The number is a LOWER BOUND by construction and the cap is what makes it one, so these tests are
mostly about what it refuses to claim: it does not add a night's sleep, it does not invent a floor
for a card touched once, it does not mix two actors, and it does not depend on the order events
happened to arrive in.
"""

from __future__ import annotations

from taskops.contracts import Event
from taskops.engine.history import rolls
from taskops.engine.timespent import GAP, attended

MINUTE = 60.0
BASE = 1_785_000_000.0


def ev(task: str, at: float, *, actor: str = "agent:berna/one", kind: str = "comment") -> Event:
    return Event(id=f"{task}-{at}", task=task, actor=actor, kind=kind, body={}, ts=BASE + at)


def test_gaps_under_the_cap_are_added_whole() -> None:
    """The ordinary case: an agent working a card leaves events minutes apart, and the span between
    the first and the last IS the time it was on it."""
    found = attended([ev("tk-a", 0), ev("tk-a", 5 * MINUTE), ev("tk-a", 12 * MINUTE)])
    assert [a["task"] for a in found] == ["tk-a"]
    assert found[0]["seconds"] == 12 * MINUTE
    assert found[0]["events"] == 3


def test_a_gap_over_the_cap_contributes_the_CAP_and_no_more() -> None:
    """The whole honesty of the measure. Two events eight hours apart are not eight hours of work —
    somebody went home. Uncapped, this fold would report a night's sleep as effort on whatever card
    was open when it started."""
    found = attended([ev("tk-a", 0), ev("tk-a", 8 * 3600)])
    assert found[0]["seconds"] == GAP


def test_one_event_on_a_card_scores_ZERO_and_not_a_floor() -> None:
    """A single event is a moment: there is no span between it and nothing. A floor here would be
    the invention the cap exists to prevent, multiplied by every card somebody touched once."""
    found = attended([ev("tk-a", 0)])
    assert found[0]["seconds"] == 0.0
    assert found[0]["events"] == 1


def test_events_that_arrived_OUT_OF_ORDER_are_sorted_before_subtracting() -> None:
    """Not defensive: a `git pull` merges two ends of a log, so events reach a clone in an order
    nobody chose. Subtracting in arrival order takes a difference backwards and counts nothing."""
    forwards = attended([ev("tk-a", 0), ev("tk-a", 4 * MINUTE), ev("tk-a", 9 * MINUTE)])
    backwards = attended([ev("tk-a", 9 * MINUTE), ev("tk-a", 0), ev("tk-a", 4 * MINUTE)])
    assert backwards[0]["seconds"] == forwards[0]["seconds"] == 9 * MINUTE


def test_two_cards_are_counted_apart_and_the_longest_leads() -> None:
    """Per card, because the question is which card took the time — a total over an actor's whole
    window is the number the profile already had."""
    found = attended([ev("tk-short", 0), ev("tk-short", 2 * MINUTE),
                      ev("tk-long", 0), ev("tk-long", 20 * MINUTE)])
    assert [a["task"] for a in found] == ["tk-long", "tk-short"]
    assert [a["seconds"] for a in found] == [20 * MINUTE, 2 * MINUTE]


def test_interleaved_work_on_two_cards_does_not_count_the_SWITCH_as_time() -> None:
    """An agent bouncing between two cards: each card's gaps are its own, so the minutes spent on
    the other one are not billed to it. Naively subtracting consecutive events of the ACTOR — rather
    than of the actor on that card — would count every switch twice."""
    found = attended([ev("tk-a", 0), ev("tk-b", 3 * MINUTE), ev("tk-a", 6 * MINUTE)])
    per = {a["task"]: a["seconds"] for a in found}
    assert per["tk-a"] == 6 * MINUTE, "its own two events, capped-summed"
    assert per["tk-b"] == 0.0, "one event, so no span"


def test_two_actors_on_one_card_are_never_merged() -> None:
    """`rolls` groups by actor and hands each group its own fold, so a card two agents worked is two
    rows and not one. Merging them would make a card look worked twice as long as anybody was on it,
    which is the same class of lie as summing two price conventions."""
    events = [ev("tk-a", 0, actor="agent:berna/one"), ev("tk-a", 10 * MINUTE, actor="agent:berna/one"),
              ev("tk-a", 1 * MINUTE, actor="agent:ana/one"), ev("tk-a", 3 * MINUTE, actor="agent:ana/one")]
    per = {roll["actor"]: roll["on"] for roll in rolls(events)}
    assert per["agent:berna/one"][0]["seconds"] == 10 * MINUTE
    assert per["agent:ana/one"][0]["seconds"] == 2 * MINUTE


def test_the_roll_up_carries_it_over_the_SAME_events_it_counts() -> None:
    """`on` is folded from the very events the roll-up's other numbers come from. A time roll-up over
    its own window would summarise something the reader cannot see beside it."""
    events = [ev("tk-a", 0, kind="commit"), ev("tk-a", 7 * MINUTE), ev("tk-b", 8 * MINUTE)]
    (roll,) = rolls(events)
    assert roll["tasks"] == 2 and roll["commits"] == 1
    assert sum(a["events"] for a in roll["on"]) == 3
    assert sum(a["seconds"] for a in roll["on"]) == 7 * MINUTE
