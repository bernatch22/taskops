"""Two densities of ONE dossier: the terminal's and the file's.

The card these test is "the narration must be the BIBLE of what was done". A report that
cannot say what was ASKED, or that keeps one line of a comment, cannot tell a reader what was
decided — so the written rendering carries the spec, every comment whole and every file, and
the printed one keeps the short form it always had.

Pure, like every test under `render/`: a literal report in, a string out.
"""

from __future__ import annotations

from taskops.contracts import ActorRoll, ClosedCard, CommitStat, Event, PeriodReport, Task
from taskops.render import render_day

SPEC = "Line one of the ask.\n\nAnd a second paragraph nobody would guess from the title."

SAID = ("The first thing decided, at length, deliberately well past the hundred and sixty "
        "characters that the widest of the brief renderings keeps, so that a truncation "
        "anywhere is visible as one and this assertion cannot pass by accident.")

LATER = "And the hand-off note."

FILES = [f"src/taskops/f{n}.py" for n in range(9)]


def _task() -> Task:
    return Task(id="tk-1", title="The work", spec=SPEC, status="done", priority=2,
                parent=None, labels=[], files=[], assignee="", created_by="dev:berna",
                created=1.0, updated=1.0)


def _comment(text: str, ts: float) -> Event:
    return Event(id=f"e{ts}", task="tk-1", actor="agent:berna/v22", kind="comment",
                 body={"text": text}, ts=ts)


def _report() -> PeriodReport:
    card = ClosedCard(task=_task(), actor="agent:berna/v22", claimed_ts=0.0, done_ts=600.0,
                      commits=[CommitStat(sha="a" * 40, subject="did it", files=FILES,
                                          actor="agent:berna/v22", ts=1.0, additions=3,
                                          deletions=1)])
    return PeriodReport(repo="/x", from_date="2026-07-28", to_date="2026-07-28",
                        label="2026-07-28", closed=[card], dropped=0, in_flight=[],
                        blocked=[], conversations=[_comment(SAID, 2.0), _comment(LATER, 3.0)],
                        actors=[ActorRoll(actor="agent:berna/v22", tasks=1, commits=1,
                                          comments=2, done=1)],
                        commits_total=1)


def test_the_written_report_carries_what_was_ASKED() -> None:
    """Without the spec the narration can only describe what was delivered, and a delivery
    with nothing to compare it against is a changelog. Both paragraphs, not the first line."""
    full = render_day(_report(), detail="full")
    assert "Line one of the ask." in full
    assert "second paragraph nobody would guess" in full
    assert "**Pedido**" in full


def test_the_terminal_does_NOT_carry_the_spec() -> None:
    """The short form is what somebody asked for on a screen. A spec per card would bury the
    one thing a printed dossier is for — what closed."""
    assert "**Pedido**" not in render_day(_report())


def test_every_comment_survives_whole_in_the_file_and_only_the_last_in_the_terminal() -> None:
    """The reasoning lives in the comments. The brief form keeps a count and the hand-off
    note, which is the right answer for a terminal and a lossy one for a record."""
    full, brief = render_day(_report(), detail="full"), render_day(_report())
    assert SAID in full and LATER in full
    assert SAID not in brief, "the brief card block truncates at 120 characters"
    assert "2 comment(s)" in brief and "2 comment(s)" in full


def test_the_file_names_every_file_and_the_terminal_caps_them() -> None:
    """`+5 more` in a written report is exactly the answer the reader came for, withheld."""
    full, brief = render_day(_report(), detail="full"), render_day(_report())
    assert all(path in full for path in FILES)
    assert "+5 more" in brief and "+5 more" not in full


def test_the_brief_rendering_is_STILL_the_default() -> None:
    """The golden day report in `tests/engine/test_period` is byte-identical because of this:
    a density parameter that changed what a bare call prints would rewrite every committed
    dossier the first time somebody regenerated one."""
    assert render_day(_report()) == render_day(_report(), detail="brief")
