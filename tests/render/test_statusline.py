"""The bottom row of a Claude Code session.

Read hundreds of times per session, on a 300 ms debounce, by somebody who is looking at
something else. Everything pinned here follows from that: it never grows with the board, it
never says a board word a reader would have to look up, and it says out loud when it is showing
a cache rather than the truth.
"""

from __future__ import annotations

import re
from typing import Any

from taskops.contracts.bar import Bar, Holding
from taskops.render.statusline import SAYS, render_statusline

BARE = re.compile(r"\x1b\[[0-9;]*m")


def plain(said: str) -> str:
    return BARE.sub("", said)


def bar(**over: Any) -> Bar:
    base: dict[str, Any] = {"board": "probe", "local": True, "holding": [], "waiting": {},
                            "mail": 0}
    return {**base, **over}  # type: ignore[return-value]


def card(id_: str = "tk-0a84e11", title: str = "the date parser", status: str = "claimed"):
    return Holding(id=id_, title=title, status=status)


# ---- what a person reads


def test_it_says_what_you_are_holding_first() -> None:
    """The volatile end leads. What is under your hands changes when you claim; the board's
    name never changes, so a narrow terminal should cut the second one."""
    said = plain(render_statusline(bar(holding=[card()], waiting={"dispatch": 3}), {}))
    assert said.index("tk-0a84e") < said.index("3 to hand out") < said.index("probe")


def test_no_move_reaches_the_bar_in_board_vocabulary() -> None:
    """`dispatch` and `specless` are schedule states. A bar is allowed to be terse and never
    cryptic: `5 to hand out` is as short as `5 dispatch` and means something on its own."""
    said = plain(render_statusline(bar(waiting=dict.fromkeys(SAYS, 1)), {}))
    for move, (word, _tone) in SAYS.items():
        assert word in said
        # `land` is exempt because its translation IS the English verb — "to land" is what a
        # person says. Every other move name must be absent from the row entirely.
        assert move in word or move not in said


def test_it_says_when_it_is_showing_a_cache() -> None:
    """THE reason `local` is on this projection. A shared board's bar reads a replica that
    syncs when something calls taskops, so a teammate's claim lands here late — and two bars
    that looked identical would promise a liveness only one of them has."""
    assert "(local)" in plain(render_statusline(bar(), {}))
    assert "(shared, cached)" in plain(render_statusline(bar(local=False), {}))


def test_the_vim_mode_is_repeated_here_when_there_is_one() -> None:
    """The built-in footer badges are a separate row taskops cannot write to, so the eye that
    goes looking for `-- INSERT --` should not have to travel to find the board too."""
    said = plain(render_statusline(bar(), {"vim": {"mode": "insert"}}))
    assert said.startswith("-- INSERT --")


def test_somebody_who_does_not_use_vim_never_sees_a_mode() -> None:
    assert "--" not in plain(render_statusline(bar(waiting={"verify": 1}), {}))


# ---- the ceilings


def test_the_row_does_not_grow_with_the_board() -> None:
    """THE property, and the only one that matters at five hundred cards."""
    small = plain(render_statusline(bar(holding=[card()], waiting={"dispatch": 1}), {}))
    big = plain(render_statusline(bar(holding=[card() for _ in range(9)],
                                      waiting={"dispatch": 120, "verify": 80}), {}))
    assert len(big) - len(small) < 30


def test_the_id_is_whole_enough_to_paste() -> None:
    """The reason it is on screen at all is that somebody reads it into `taskops tasks show`.
    Truncating it to a round eight characters shaves the last hex digit off a nine-character
    id and prints a handle that resolves to nothing."""
    said = plain(render_statusline(bar(holding=[card("tk-92c0aa")]), {}))
    assert "tk-92c0aa" in said


def test_more_than_one_held_card_is_a_count_not_a_list() -> None:
    said = plain(render_statusline(bar(holding=[card(), card("tk-77b"), card("tk-99c")]), {}))
    assert "+2" in said and "tk-77b" not in said


def test_a_long_title_is_cut() -> None:
    said = plain(render_statusline(bar(holding=[card(title="x " * 60)]), {}))
    assert "…" in said and len(said) < 80


# ---- and what it refuses to say


def test_it_is_ONE_row() -> None:
    said = render_statusline(bar(local=False, holding=[card()], mail=2,
                                 waiting={"verify": 1, "dispatch": 2}),
                             {"vim": {"mode": "normal"},
                              "context_window": {"used_percentage": 95}})
    assert "\n" not in said


def test_context_is_silent_until_it_matters() -> None:
    """A number on screen from the first prompt is a number nobody reads by the time it counts."""
    quiet = plain(render_statusline(bar(), {"context_window": {"used_percentage": 12}}))
    loud = plain(render_statusline(bar(), {"context_window": {"used_percentage": 91}}))
    assert "ctx" not in quiet and "91% ctx" in loud


def test_an_empty_board_prints_the_board_and_nothing_else() -> None:
    """Not "" — a bar that vanished would read as taskops having crashed, and the one fact
    somebody still wants from an idle board is which board they are standing in."""
    assert plain(render_statusline(bar(), {})) == "probe (local)"


def test_colour_is_removable_without_changing_a_word() -> None:
    """If a terminal shows the escapes raw, what is left must still be the row."""
    said = render_statusline(bar(waiting={"verify": 2}), {})
    assert "\x1b[" in said and plain(said) == "2 to review  ·  probe (local)"
