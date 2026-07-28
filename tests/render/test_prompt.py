"""The prompt segment, from literal dicts — no database in sight.

Everything worth asserting here is a rule about what is NOT printed, because the whole
design of a prompt segment is subtraction: it earns its place by disappearing.
"""

from __future__ import annotations

from typing import Any

from taskops.contracts.status import Status
from taskops.render.prompt import PORCELAIN_VERSION, render_porcelain, render_prompt


def make(**over: Any) -> Status:
    """A status with nothing to say, so each test names only the fact it is about."""
    base: dict[str, Any] = dict(
        project="axion", root="/tmp/axion", actor="dev:berna", objective="",
        total=0, ready=0, blocked=0, counts={}, mine=[], others=[],
        idle=0, idle_days=7, bottleneck=None,
        reports=dict(today="2026-07-29", today_events=0, yesterday="2026-07-28",
                     yesterday_written=True, yesterday_narrated=True),
        sync=dict(host="", ahead=0, last_sync=0.0))
    base.update(over)
    return base  # type: ignore[return-value]


def claim(task: str = "tk-1") -> dict[str, Any]:
    return dict(actor="dev:berna", task=task, title="t", state="claimed",
                left=900.0, expiring=False)


def test_the_full_segment_is_the_one_from_the_spec() -> None:
    status = make(total=9, counts={"ready": 2, "claimed": 1, "done": 6}, mine=[claim()],
                  sync=dict(host="h", ahead=5, last_sync=1.0),
                  reports=dict(today="2026-07-29", today_events=0, yesterday="2026-07-28",
                               yesterday_written=False, yesterday_narrated=False))
    assert render_prompt(status) == "tk:axion 3▸1 ⇡5 !r"


def test_a_project_with_nothing_to_say_renders_as_the_empty_string() -> None:
    """Not `tk:axion`, not a space — nothing. A segment that is always there is a
    segment nobody reads, and it still costs a column of the line."""
    assert render_prompt(make()) == ""


def test_an_empty_project_says_nothing_even_when_yesterday_was_never_narrated() -> None:
    """A repo with zero cards has no habit to have slipped. Nagging there would put
    `!r` on the prompt of every freshly-initialised checkout, forever."""
    status = make(reports=dict(today="d", today_events=0, yesterday="y",
                               yesterday_written=False, yesterday_narrated=False))
    assert render_prompt(status) == ""


def test_zero_segments_are_omitted_one_by_one() -> None:
    assert render_prompt(make(total=4, counts={"ready": 3, "done": 1})) == "tk:axion 3"
    assert render_prompt(make(total=1, counts={"done": 1},
                              sync=dict(host="h", ahead=2, last_sync=1.0))) == "tk:axion ⇡2"


def test_the_arrow_appears_only_when_something_is_mine() -> None:
    """`3▸0` would read as a claim on nothing. Three open cards and none of them mine
    is exactly the state the bare number describes."""
    assert render_prompt(make(total=3, counts={"ready": 3})) == "tk:axion 3"


def test_done_and_cancelled_never_count_as_open() -> None:
    status = make(total=99, counts={"done": 90, "cancelled": 6, "ready": 3})
    assert render_prompt(status) == "tk:axion 3"


def test_colour_is_off_unless_asked_and_speaks_zsh_when_it_is() -> None:
    """Raw SGR inside zsh's PROMPT miscounts the line width and corrupts editing, so
    the zsh path emits `%F{..}%f` and nothing else does."""
    status = make(total=3, counts={"ready": 3})
    assert "\033" not in render_prompt(status)
    assert "%" not in render_prompt(status)
    assert render_prompt(status, colour="zsh") == "%F{blue}tk:axion%f %F{cyan}3%f"


def test_porcelain_is_one_key_per_line_and_leads_with_its_version() -> None:
    out = render_porcelain(make(total=3, counts={"ready": 3}, mine=[claim()]))
    pairs = dict(line.split("=", 1) for line in out.splitlines())
    assert out.splitlines()[0] == f"version={PORCELAIN_VERSION}"
    assert pairs["project"] == "axion"
    assert pairs["open"] == "3"
    assert pairs["mine"] == "1"
    assert pairs["ahead"] == "0"
    assert pairs["prompt"] == "tk:axion 3▸1"


def test_porcelain_spells_booleans_as_one_and_zero_and_absence_as_empty() -> None:
    """`True`/`None` are Python spellings; a shell reading this should never have to
    know them. Every flag is 1 or 0 and every missing string is the empty string."""
    pairs = dict(line.split("=", 1) for line in render_porcelain(make()).splitlines())
    assert pairs["yesterday_narrated"] == "1"
    assert pairs["bottleneck"] == ""
    assert pairs["blocks"] == "0"
    assert pairs["remote"] == ""


def test_no_porcelain_value_can_contain_a_separator() -> None:
    """The parsing rule promised in the docs — split on the FIRST `=`, one line per
    key — only holds if no value carries a newline. Titles are the risk, so none ship."""
    status = make(total=2, counts={"ready": 2},
                  bottleneck=dict(task="tk-1", title="a title\nwith a newline", blocks=4))
    for line in render_porcelain(status).splitlines():
        assert "\n" not in line.split("=", 1)[1]
    assert "a title" not in render_porcelain(status)
