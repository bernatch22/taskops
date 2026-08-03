"""The three nouns at a terminal: `taskops milestone`, `taskops context`, `taskops me`.

Driven through `build_parser` and the real `run`, because the split is a CLI decision and argparse
is where it lands: `--mine` used to mean "file it under me" on a write and "show my page" on a
read, and a flag that changes what a verb IS cannot be checked anywhere but here.

The retired spellings are tested too. A reader who types `context objective` learns where it went
from the answer — argparse's own refusal lists the choices and never names the replacement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.transports.cli.main import build_parser
from taskops.usecases import init


def run(*argv: str) -> str:
    """One command, exactly as a person types it."""
    args = build_parser().parse_args(list(argv))
    return str(args.run(args))


@pytest.fixture()
def where(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


def _chapter(where: Path, text: str = "que el CSV entre") -> str:
    return run("milestone", "--repo", str(where), "--actor", "dev:berna", "new", text).split()[1]


def test_a_chapter_walks_its_whole_life_from_the_terminal(where: Path) -> None:
    """The nine verbs are one sentence each, and the receipt after every move is the chapter with
    its counts — because the question after each of them is "and how far along is it now"."""
    chapter = _chapter(where)
    assert run("milestone", "--repo", str(where), "show", chapter).startswith("◆")
    reported = run("milestone", "--repo", str(where), "--actor", "agent:berna/w1", "review",
                   chapter, "-m", "las dos cards cerradas")
    assert "REPORTED FINISHED" in reported
    closed = run("milestone", "--repo", str(where), "--actor", "dev:berna", "done", chapter)
    assert closed.startswith("✓") and "reached · dev:berna" in closed


def test_a_planned_chapter_is_listed_apart_from_what_is_being_worked_on(where: Path) -> None:
    """A chapter written down is not a chapter being worked on, and nothing may be planned into
    the first. Printed as one list they would read as four things in flight."""
    run("milestone", "--repo", str(where), "--actor", "dev:berna", "new", "el importador")
    run("milestone", "--repo", str(where), "--actor", "dev:berna", "new", "la facturacion",
        "--planned")
    said = run("milestone", "--repo", str(where))
    assert "# active — 1" in said
    assert "la facturacion" in said.split("# planned")[1]


def test_list_all_is_the_record_and_the_bare_list_is_what_is_open(where: Path) -> None:
    """"What have we shipped" is unanswerable from the chapters still open, which is why closed
    ones are a flag and not the default: a session asking what to work on must not read history."""
    chapter = _chapter(where)
    run("milestone", "--repo", str(where), "--actor", "dev:berna", "done", chapter)
    assert "no milestone yet" in run("milestone", "--repo", str(where))
    assert chapter in run("milestone", "--repo", str(where), "list", "--all")


def test_a_project_rule_outlives_the_chapter_and_a_chapter_fact_does_not(where: Path) -> None:
    """`--project` is the LIFETIME, and this is the whole point of the level: a chapter's facts
    leave every slice when a person verifies it, and a rule does not.

    The default is the chapter deliberately — a fact that died with it is restated in one command,
    and one that lives forever accumulates until nobody reads any of them.
    """
    chapter = _chapter(where)
    run("context", "--repo", str(where), "--actor", "dev:berna", "rule",
        "cero dependencias fuera de la stdlib", "--project")
    run("context", "--repo", str(where), "--actor", "dev:berna", "decision",
        "el CSV se lee en streaming")
    run("milestone", "--repo", str(where), "--actor", "dev:berna", "done", chapter)

    said = run("context", "--repo", str(where))
    assert "cero dependencias fuera de la stdlib" in said
    assert "el CSV se lee en streaming" not in said, "a chapter's fact left with its chapter"
    # And it is still READABLE, on purpose and by name. "What did we decide while doing the
    # importer" is a real question six months later; injecting it forever is what made contexts rot.
    assert "el CSV se lee en streaming" in run("context", "--repo", str(where),
                                               "--milestone", chapter)


def test_your_own_page_carries_your_objective_and_not_somebody_elses(where: Path) -> None:
    """`taskops me` is the noun `--mine` used to be a flag for. Nobody types their own id to say
    "this is mine": the command IS the statement, resolved through `whoami` like a claim."""
    _chapter(where)
    run("me", "--repo", str(where), "--actor", "dev:ana", "objective", "terminar el importador")
    run("me", "--repo", str(where), "--actor", "dev:juan", "objective", "la facturacion")

    mine = run("me", "--repo", str(where), "--actor", "dev:ana")
    assert "terminar el importador" in mine
    assert "la facturacion" not in mine


def test_the_retired_spellings_name_their_replacement(where: Path) -> None:
    """`context objective` and `context show` are gone, and a refusal that only listed the
    remaining choices would leave the reader to guess which noun took the verb."""
    assert "taskops me objective" in run("context", "--repo", str(where), "objective")
    assert "bare" in run("context", "--repo", str(where), "show")


def test_a_note_may_not_be_the_projects_because_a_permanent_note_is_a_rule(where: Path) -> None:
    """The one sort `--project` refuses. A note that outlived its chapter is the scratchpad that
    made a slice grow forever — if it is permanent it is a `rule` or a `decision`."""
    from taskops._errors import BadRequest

    _chapter(where)
    with pytest.raises(BadRequest) as refused:
        run("context", "--repo", str(where), "--actor", "dev:berna", "note", "algo suelto",
            "--project")
    assert "a note is always a chapter's" in str(refused.value)
