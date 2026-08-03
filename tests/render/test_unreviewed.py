"""The question `plan` asks back: who closes these?

There is deliberately no project default for a card's reviewer — with nothing set a card names
nobody, which is right for one developer trying the tool and wrong for a card to stay in. So the
ask lives in the RETURN VALUE of the call that created the cards, which is the only place a
planner reads it with every id still in front of it. A sentence in a guide is gone by the second
compaction; this is the pattern this codebase already had to learn twice.
"""

from __future__ import annotations

from typing import Any

from taskops.render._unreviewed import SHOW, ask_who_reviews


def card(id_: str, reviewer: str = "") -> Any:
    return {"id": id_, "reviewer": reviewer}


def test_a_card_naming_nobody_is_asked_about() -> None:
    said = ask_who_reviews([card("tk-0a84e1")])

    assert "tk-0a84e1" in said
    assert "--reviewer peer" in said and "--reviewer human" in said


def test_it_says_what_is_actually_still_guarding_the_card() -> None:
    """Not "unreviewed" — one rule survives with no reviewer named, and a warning that implied
    none would be wrong in the direction that gets a guard added twice: an AGENT may not close
    the review it opened. What it does NOT stop is the same developer's second agent."""
    said = ask_who_reviews([card("tk-1")])

    assert "may not close" in said and "same developer" in said


def test_every_card_deciding_for_itself_says_nothing() -> None:
    """Silence is the common case on a board that settled this once, and it is load-bearing: a
    plan result that always ended in a paragraph about reviewers is a paragraph nobody reads,
    which is how the one time it mattered goes past unnoticed."""
    assert ask_who_reviews([card("tk-1", "peer"), card("tk-2", "dev:ana")]) == ""


def test_deliberately_unreviewed_counts_as_decided() -> None:
    """`--reviewer none` normalises to "", which is the same value as never having said — so a
    card somebody chose to leave unreviewed cannot be told apart here, and asking again about it
    would be the tool arguing with a decision. The batch is what makes that acceptable: this is
    asked once per plan, not once per card, forever."""
    assert ask_who_reviews([card("tk-1", "  ")]) != "", "whitespace is not a decision"


def test_a_big_plan_asks_once_and_names_a_few() -> None:
    """A plan of forty cards must not answer with forty lines. The point is the QUESTION."""
    said = ask_who_reviews([card(f"tk-{n}") for n in range(40)])

    assert said.count("tk-") == SHOW, "the named few; the example commands say `<id>`, not an id"
    assert "+36 more" in said and "40 card(s)" in said
