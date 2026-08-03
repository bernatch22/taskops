"""`taskops_milestone` — one test per branch of the tool an agent moves a chapter with.

Driven through `HANDLERS`, the real dispatch table, and not through the use case: the whole reason
this tool exists is that a use case an agent cannot reach is a capability nobody has, and every
argument below is a string that arrived as JSON. Two of the bugs this file would have caught were
exactly that shape — a verb bound to a function that does not exist, and a bare list answered
where the decoder wants an object.

The refusals are here too, because a refusal IS the feature: `done` is a person's, and an agent
that could take it would be grading the chapter it worked under.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.transports.mcp.dispatch import HANDLERS
from taskops.usecases import init


def tool(**args: object) -> str:
    return str(HANDLERS["taskops_milestone"]({k: v for k, v in args.items()}))


def cards(**args: object) -> str:
    return str(HANDLERS["taskops_plan"]({k: v for k, v in args.items()}))


@pytest.fixture()
def where(tmp_path: Path) -> Path:
    """A board with NO chapter. Every test here either opens one or is about not having one."""
    init(tmp_path, install_git_hooks=False)
    return tmp_path


def _id(said: str) -> str:
    """The id out of a rendered chapter — eight characters, which is what every surface prints."""
    return said.split()[1]


def test_a_board_with_no_chapter_says_so_and_names_the_way_out(where: Path) -> None:
    """The one state a session must learn from a READ rather than from a refusal mid-plan.

    `plan` refuses without a chapter, and a tool that answered "nothing" would send the caller
    straight into that refusal — a wasted turn that reads as a broken tool.
    """
    said = tool(repo_path=str(where))
    assert "no milestone yet" in said
    assert "taskops_milestone create=" in said


def test_create_starts_it_and_planned_does_not(where: Path) -> None:
    """`planned` is the whole difference between a todo-list and a board: a chapter written down
    is not a chapter being worked on, and nothing may be planned into the first."""
    started = tool(repo_path=str(where), create="que el CSV entre", actor="agent:berna/w1")
    later = tool(repo_path=str(where), create="que se pueda facturar", planned=True,
                 actor="agent:berna/w1")
    assert started.startswith("◆"), started
    assert later.startswith("○"), later
    listed = tool(repo_path=str(where))
    assert "# active — 1" in listed
    assert "que se pueda facturar" in listed.split("# planned")[1]


def test_several_chapters_are_active_and_the_tool_names_them_all(where: Path) -> None:
    """The orchestrator is the one reader that CHOOSES between them, so it must see them all.

    A tool that answered with "the" chapter would have to pick, and picking is what put the bound
    on the board instead of on the card — a card belongs to exactly one chapter, and that is where
    the narrowing lives.
    """
    tool(repo_path=str(where), create="el importador", actor="dev:berna")
    tool(repo_path=str(where), create="la facturacion", actor="dev:berna")
    said = tool(repo_path=str(where))
    assert "# active — 2" in said
    assert "el importador" in said and "la facturacion" in said


def test_reading_one_chapter_answers_with_its_cards(where: Path) -> None:
    """"How do I reach its cards" in ONE call, which is what makes the tool usable for dispatch.

    The cards come off the board and are filtered by the chapter they name — a chapter owns no
    list, so there is nothing to keep in step.
    """
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    cards(repo_path=str(where), milestone=chapter, actor="dev:berna",
          tasks=[{"title": "leer el CSV", "spec": "encoding"},
                 {"title": "normalizar fechas", "spec": "DD/MM"}])
    said = tool(repo_path=str(where), milestone=chapter)
    assert "2 card(s) · 2 ready" in said
    assert "leer el CSV" in said and "normalizar fechas" in said


def test_review_reports_it_and_says_who_has_to_act(where: Path) -> None:
    """An agent REPORTS. The chapter stays open — nothing is archived on an agent's word — and the
    answer names the person's command, because a state word is not a sentence."""
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    said = tool(repo_path=str(where), review=chapter, m="las dos cards cerradas",
                actor="agent:berna/w1")
    assert said.startswith("◐")
    assert "REPORTED FINISHED — “las dos cards cerradas”" in said
    assert "A person verifies" in said


def test_an_agent_may_not_verify_what_it_reported(where: Path) -> None:
    """THE rule, one level up from `done` on a card. The refusal names the verb it CAN use: a
    worker told only "no" spent four turns explaining it could not, watched live."""
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    tool(repo_path=str(where), review=chapter, m="listo", actor="agent:berna/w1")
    with pytest.raises(BadRequest) as refused:
        tool(repo_path=str(where), done=chapter, actor="agent:berna/w1")
    assert "verifying is not reporting" in str(refused.value)
    assert "review=" in str(refused.value), "the refusal has to name the way out"


def test_a_person_verifies_and_the_record_says_who(where: Path) -> None:
    """`closed_by` is the point of the whole state: "we shipped it" is a claim with an author."""
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    tool(repo_path=str(where), review=chapter, m="listo", actor="agent:berna/w1")
    said = tool(repo_path=str(where), done=chapter, actor="dev:berna")
    assert said.startswith("✓")
    assert "reached · dev:berna" in said


def test_a_rejection_with_no_findings_is_refused(where: Path) -> None:
    """A chapter bounced with nothing to act on comes back unchanged — a card going round twice
    with a whole chapter's work behind it."""
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    tool(repo_path=str(where), review=chapter, m="listo", actor="agent:berna/w1")
    with pytest.raises(BadRequest) as refused:
        tool(repo_path=str(where), reject=chapter, actor="dev:berna")
    assert "no findings" in str(refused.value)


def test_a_rejection_puts_it_back_in_force_with_the_reason(where: Path) -> None:
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    tool(repo_path=str(where), review=chapter, m="listo", actor="agent:berna/w1")
    said = tool(repo_path=str(where), reject=chapter, m="falta el encoding latin-1",
                actor="dev:berna")
    assert said.startswith("◆"), "back in force, and its cards keep their home"


def test_cancelling_keeps_the_reason_because_there_is_no_delete(where: Path) -> None:
    """"We stopped" is not "we shipped", and the reason is what somebody wants three weeks later
    when the same idea comes back."""
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    said = tool(repo_path=str(where), cancel=chapter, m="la clienta se fue", actor="dev:berna")
    assert "abandoned · dev:berna — “la clienta se fue”" in said


def test_a_planned_chapter_starts_and_an_agent_may_start_it(where: Path) -> None:
    """Beginning work is working. A chapter nobody may move out of `planned` is a todo-list with
    a lock on it, which is why `start` carries no guard."""
    chapter = _id(tool(repo_path=str(where), create="la facturacion", planned=True,
                       actor="dev:berna"))
    assert tool(repo_path=str(where), start=chapter, actor="agent:berna/w1").startswith("◆")


def test_updating_the_wording_is_not_a_state_change(where: Path) -> None:
    """A chapter gets re-worded as a team learns what it is actually shipping, and that is not a
    move: nothing about who may close it changes, so nothing guards it."""
    chapter = _id(tool(repo_path=str(where), create="el import", actor="agent:berna/w1"))
    said = tool(repo_path=str(where), update=chapter, text="que una clienta suba su CSV",
                horizon="2026-09-01", actor="agent:berna/w1")
    assert "que una clienta suba su CSV" in said and "by 2026-09-01" in said


def test_a_terminal_chapter_names_every_state_it_could_have_reached(where: Path) -> None:
    """The refusal teaches the shape of the machine. Without the second half a caller guesses at
    the next arrow and is refused again — the card machine learned this the same way."""
    chapter = _id(tool(repo_path=str(where), create="el importador", actor="dev:berna"))
    tool(repo_path=str(where), done=chapter, actor="dev:berna")
    with pytest.raises(BadRequest) as refused:
        tool(repo_path=str(where), review=chapter, m="otra vez", actor="agent:berna/w1")
    assert "nowhere — it is closed" in str(refused.value)
