"""The CLI's parser, without running a command.

`build_parser` is the whole surface of the terminal: what names exist, and what flags each
one takes. Asserting on it is cheap and catches the two things a rename gets wrong — an old
name that stopped working, and an alias whose flags quietly drifted from the real command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.transports.cli.commands import ask, ui
from taskops.transports.cli.main import build_parser, main
from taskops.usecases import next_task


def flags_of(name: str) -> set[str]:
    """Every option string the parser for `name` accepts, as a set."""
    parsed = build_parser().parse_args([name])
    return set(vars(parsed)) - {"command", "run", "deprecated_name"}


def test_the_ui_command_is_called_ui() -> None:
    parsed = build_parser().parse_args(["ui"])
    assert parsed.run is ui.run
    assert parsed.deprecated_name is False
    assert parsed.port == ui.DEFAULT_PORT


def test_the_old_studio_name_still_runs_and_marks_itself_deprecated() -> None:
    """A rename that breaks a line in somebody's shell history buys nothing. The alias reaches
    the same `run`; the flag is what makes `run` print the one deprecation line."""
    parsed = build_parser().parse_args(["studio"])
    assert parsed.run is ui.run
    assert parsed.deprecated_name is True


def test_the_alias_takes_exactly_the_flags_the_real_command_takes() -> None:
    """An alias that dropped `--readonly` would be worse than no alias: the board on the wall
    would start accepting writes, and nothing would say so."""
    assert flags_of("studio") == flags_of("ui")


def test_the_deprecated_name_is_hidden_from_help() -> None:
    """It is a bridge for existing muscle memory, not a second documented way in."""
    assert "studio" not in build_parser().format_help()


def test_the_help_lists_what_a_person_does_and_nothing_else() -> None:
    """The regroup, asserted where it is visible. `guard` and `brief` are typed by a git
    hook and by nothing else, so a person scanning this page for their task list should
    never have to decide whether one of them is what they wanted."""
    listed = _listed_commands()
    assert listed == {"init", "join", "board", "setup", "ui", "serve", "tasks", "attention", "statusline",
                      "context", "policy", "status",
                      "report", "schedule", "recover", "sync", "login", "open", "publish", "land", "remote",
                      "push", "pull"}


def test_login_is_the_one_command_that_is_not_about_a_repository() -> None:
    """A session belongs to the PERSON on this machine, not to a checkout: it is stored in the
    home directory and serves every clone at once. `--repo` would be a lie — there is nothing
    per-project to point it at — so its absence is the assertion."""
    parsed = build_parser().parse_args(["login", "https://taskops.example.com"])
    taken = set(vars(parsed)) - {"command", "run"}
    assert taken == {"url", "logout", "show"}


def test_the_remote_verbs_are_the_developers_and_are_listed() -> None:
    """`remote`, `push` and `pull` decide when THIS MACHINE talks to a server, which is a
    person's call and not an agent's — so they are on the CLI, in the help, and deliberately
    absent from the MCP tool surface. They sit beside `sync` rather than replacing it: a team
    with no server still converges through git, and that path is not deprecated."""
    for verb in ("remote", "push", "pull"):
        assert "repo" in flags_of(verb), f"{verb} cannot be pointed at a project"


@pytest.mark.parametrize("gone", ["guard", "hook", "ingest", "brief", "inbox", "track",
                                  "checkout", "next", "update", "ask", "plan", "dispatch",
                                  "log", "run"])
def test_the_thirteen_hidden_commands_are_gone_not_hidden(gone: str) -> None:
    """Seven listed AND seven existing. Hidden reads the same from the outside as absent and
    is not the same thing: every one of these was still a door into the developer's binary,
    which is how git and Claude Code kept entering through it. `guard`/`hook`/`ingest` and the
    session verbs live in `taskops.transports.hooks`; the rest are the agent's, over MCP."""
    with pytest.raises(SystemExit):
        build_parser().parse_args([gone])


def _listed_commands() -> set[str]:
    """The command NAMES `--help` offers. Parsed out of the listing rather than searched
    for as substrings, because `init`'s own help text ends in "install the git hooks" — a
    naive `"hook" not in help` passes today and fails on a sentence nobody thought about."""
    listing = build_parser().format_help()
    body = listing.split("<command>\n", 1)[1].split("\noptions:", 1)[0]
    # Exactly four spaces then a word: a help string long enough to wrap continues on a line
    # indented FOURTEEN, and counting those made the first word of a description a "command"
    # — which is how adding `serve` reported a phantom command called `token`.
    return {line.split()[0] for line in body.splitlines()
            if line.startswith("    ") and not line.startswith("     ")}


def test_tasks_show_and_search_reach_the_same_run_the_old_verb_did() -> None:
    """Not an approximation of `ask` — the same function. Two implementations of "read a
    task" is how the CLI and the MCP start disagreeing about what a task looks like."""
    assert build_parser().parse_args(["tasks", "show", "tk-0"]).run is ask.run
    assert build_parser().parse_args(["tasks", "search", "whatever"]).run is ask.run


def test_the_group_takes_repo_before_or_after_the_subcommand(root: Path) -> None:
    """argparse writes a subparser's defaults over what the parent already parsed, so this
    is the assertion that `--repo` in front of the subcommand is not silently reset to `.`."""
    for argv in (["tasks", "--repo", str(root), "list"], ["tasks", "list", "--repo", str(root)]):
        assert main(argv) == 0


def test_tasks_add_creates_a_card_and_prints_its_id(root: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tasks", "add", "Write the thing", "--repo", str(root),
                 "--spec", "what done looks like", "--priority", "0"]) == 0
    created = capsys.readouterr().out
    assert "tk-" in created
    assert main(["tasks", "list", "--repo", str(root)]) == 0
    assert "Write the thing" in capsys.readouterr().out


def test_tasks_done_refuses_a_card_with_no_commit(root: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    """The same guard `update --status done` enforces, because it IS that code path. A
    second door onto `done` that skipped the check is the whole reason for wrapping."""
    main(["tasks", "add", "Write the thing", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]
    next_task(root, task=task, actor="dev:berna")
    capsys.readouterr()
    assert main(["tasks", "done", task, "--repo", str(root), "-m", "finished",
                 "--actor", "dev:berna"]) == 1
    assert "commit" in capsys.readouterr().err


def test_tasks_edit_sets_acceptance_criteria_alone(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The flag the README documented and `set_acceptance`'s own docstring named, for as long as
    both existed, and that was never wired: the use case, the rpc verb and the MCP field were all
    there, and the only surface that could not set a card's criteria was the one a PERSON types.

    ALONE is the assertion. `edit` refuses a caller who named no field, and calling it anyway
    made `--acceptance` fail with "nothing to edit" — its refusal for an empty call, about a call
    that named something.
    """
    main(["tasks", "add", "Import a CSV", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root), "--acceptance",
                 "WHEN a 3-row CSV is imported THE SYSTEM SHALL store 3 rows; "
                 "WHEN a row fails THE SYSTEM SHALL keep the rest"]) == 0

    said = capsys.readouterr().out
    assert "acceptance (2)" in said and "store 3 rows" in said
    # Split on `;` and not `,`: an EARS line is a sentence, and commas live inside it.
    assert "WHEN a row fails THE SYSTEM SHALL keep the rest" in said


def test_a_criterion_that_is_not_EARS_is_kept_and_flagged(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Accepted, never refused — refusing would make a card unwriteable over a wording rule —
    so the warning is the only thing standing between that and a silent downgrade."""
    main(["tasks", "add", "Import a CSV", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root), "--acceptance", "que ande"]) == 0

    said = capsys.readouterr().out
    assert "que ande" in said and "does not read as EARS" in said


def test_an_empty_acceptance_clears_the_criteria(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--acceptance ""` is a real edit — somebody removing criteria that were wrong — and it
    has to be distinguishable from not passing the flag, which is why the default is `None`."""
    main(["tasks", "add", "Import a CSV", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]
    main(["tasks", "edit", task, "--repo", str(root), "--acceptance", "WHEN x THE SYSTEM SHALL y"])
    capsys.readouterr()

    assert main(["tasks", "edit", task, "--repo", str(root), "--acceptance", ""]) == 0
    assert "(cleared)" in capsys.readouterr().out


def test_edit_with_no_field_at_all_is_still_refused(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The refusal `--acceptance` had to stop borrowing must still fire for the call it is for."""
    main(["tasks", "add", "Import a CSV", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root)]) == 1
    assert "nothing to edit" in capsys.readouterr().err


def test_tasks_edit_rewrites_the_card_from_the_terminal(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The whole door, end to end: flags in, a rewritten row out, and the list showing it."""
    main(["tasks", "add", "Write the thing", "--repo", str(root), "--spec", "wrong brief"])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root), "--title", "Write the RIGHT thing",
                 "--spec", "the real brief", "--priority", "0"]) == 0
    assert "edited title, spec, priority" in capsys.readouterr().out
    assert main(["tasks", "show", task, "--repo", str(root)]) == 0
    assert "the real brief" in capsys.readouterr().out


def test_tasks_edit_with_no_flags_says_so_instead_of_pretending(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """At least one field is required, and the refusal comes from the use case — so the MCP
    and HTTP surfaces would refuse identically rather than only argparse knowing the rule."""
    main(["tasks", "add", "Write the thing", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root)]) == 1
    assert "nothing to edit" in capsys.readouterr().err


def test_open_never_echoes_the_credential_it_just_opened(
        root: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """A terminal is a thing people screenshot, paste into issues and share on a call. The
    browser is already holding the secret; a second copy in the scrollback is pure exposure."""
    from taskops.usecases import add_remote

    add_remote(root, "https://boards.example.com/axion", token="tk_secret")
    monkeypatch.setattr("webbrowser.open", lambda _url: True)

    assert main(["open", "--repo", str(root)]) == 0
    assert "tk_secret" not in capsys.readouterr().out


def test_open_shows_the_url_when_there_is_no_browser_to_hand_it_to(
        root: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Over SSH the URL is the only useful output there is — withholding it there would leave
    the caller with nowhere to go, which is a different failure from leaking it."""
    from taskops.usecases import add_remote

    add_remote(root, "https://boards.example.com/axion", token="tk_secret")
    monkeypatch.setattr("webbrowser.open", lambda _url: False)

    assert main(["open", "--repo", str(root)]) == 0
    assert "tk_secret" in capsys.readouterr().out


def test_open_print_gives_the_url_and_opens_nothing(
        root: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    from taskops.usecases import add_remote

    add_remote(root, "https://boards.example.com/axion", token="tk_secret")
    monkeypatch.setattr("webbrowser.open", _refuse)

    assert main(["open", "--repo", str(root), "--print"]) == 0
    assert capsys.readouterr().out.strip().endswith("/axion/?token=tk_secret")


def _refuse(url: str) -> bool:
    raise AssertionError(f"--print must not open a browser, but it opened {url}")


def test_cancel_is_the_nearest_thing_to_deleting_a_card(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """There is no delete, and the difference is not pedantry: the log is append-only, so a
    deleted card would be a hole in the history every report is derived from. Cancelling closes
    it — it stops blocking its dependents exactly as `done` does — and keeps the reason."""
    main(["tasks", "add", "an idea nobody will do", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "cancel", task, "--repo", str(root),
                 "-m", "duplicate of tk-other"]) == 0
    assert main(["tasks", "show", task, "--repo", str(root)]) == 0
    shown = capsys.readouterr().out
    assert "cancelled" in shown
    assert "duplicate of tk-other" in shown, "the reason is the point"


def test_cancelling_without_a_reason_is_refused() -> None:
    """A cancelled card with no explanation is a card the next person with the same idea
    recreates. `-m` is required for this one transition and optional for the others."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["tasks", "cancel", "tk-1"])


def test_reject_sends_a_review_back_to_its_worker(root: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    """The human half of the review loop. `reject` is a `ready`, not a `release`, and the
    difference is who gets it next: a rejected card KEEPS its assignee so the worker that
    wrote it picks it up, while a release means "I give this up, anybody take it"."""
    from taskops.storage import Store
    from taskops.usecases import next_task, update
    from taskops.usecases._handoff import hand_over

    main(["tasks", "add", "the work", "--repo", str(root), "--spec", "s"])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]
    with Store(root) as store:
        hand_over(store, task, "agent:ana/api1", actor="dev:ana")
    next_task(root, task=task, actor="agent:ana/api1")
    update(root, task, status="review", comment="round 1", actor="agent:ana/api1")
    capsys.readouterr()

    assert main(["tasks", "reject", task, "--repo", str(root),
                 "-m", "the 409 does not carry the cart"]) == 0
    with Store(root) as store:
        after = store.tasks.need(task)
    assert after["status"] == "ready"
    assert after["assignee"] == "agent:ana/api1", "back to ITS worker, not to the pool"


def test_rejecting_without_a_finding_is_refused() -> None:
    """A rejection with no reason is a card bounced with nothing to act on — the worker reads
    "not good enough" and guesses, which is how a card goes round twice for no reason."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["tasks", "reject", "tk-1"])
