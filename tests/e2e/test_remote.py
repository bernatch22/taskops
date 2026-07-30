"""Two projects, one server, and the four things that must not go wrong.

The server is a fake (`tests/e2e/fakeserver.py`) written from the frozen contract rather than
imported from the sibling module that implements it — see that file for why. Everything else
is real: real projects on disk, the real CLI parser, the real event log.

The assertions are chosen from the failures that have actually happened in this codebase.
Chiefly: **the board, not the table.** A `pull` that relayed events and never replayed them
left a teammate looking at an empty board once already (`engine/replay.py` tells it), and the
row would have been in the database the whole time — so `test_a_pull_puts_the_card_on_the_board`
asks the board, which is the only question a person ever asks.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from typing import Iterator

import pytest

from taskops.storage import Store
from taskops.usecases import (
    add_remote,
    board,
    init,
    plan,
    pull,
    push,
    read_remote,
    remove_remote,
    write_report,
)
from tests.e2e.fakeserver import TOKEN, Fake, running


@pytest.fixture
def fake() -> Fake:
    return Fake()


@pytest.fixture
def base(fake: Fake) -> Iterator[str]:
    yield from running(fake)


def make(where: Path, url: str = "") -> Path:
    init(where, install_git_hooks=False)
    if url:
        add_remote(where, url, TOKEN)
    return where


# ── the token ───────────────────────────────────────────────────────────────────────────

def test_the_token_file_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    """0600 at creation, not after a chmod: the two-step version publishes the token to every
    account on the machine for the width of one syscall."""
    make(tmp_path, "https://taskops.example.com")
    mode = (tmp_path / ".taskops" / "remote.json").stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_git_refuses_to_see_the_token(tmp_path: Path) -> None:
    """THE test. `init` writes a gitignore block that lists what under `.taskops/` is not
    committed, and it lists paths rather than a wildcard — so a file added to that directory
    is tracked by default. A token in a commit is not recoverable by deleting the file."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    make(tmp_path, "https://taskops.example.com")
    ignored = subprocess.run(["git", "check-ignore", ".taskops/remote.json"],
                             cwd=tmp_path, capture_output=True, text=True)
    assert ignored.returncode == 0, "remote.json is NOT gitignored — the token would commit"
    listed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                            cwd=tmp_path, capture_output=True, text=True).stdout
    assert "remote.json" not in listed


def test_an_upgraded_project_gains_the_rule_before_it_can_leak(tmp_path: Path) -> None:
    """A repository initialised by an older taskops has the marker and not the new line.
    Re-running init has to add it, or upgrading in place is one `git add .` from a leak."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("# taskops — older\n.taskops/db.sqlite\n",
                                         encoding="utf-8")
    make(tmp_path, "https://taskops.example.com")
    assert ".taskops/remote.json" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_a_second_remote_is_refused_by_naming_the_first(tmp_path: Path) -> None:
    """One remote per project. Two is federation, which is not designed — and the refusal
    has to say which one is already there, or the fix is a guess."""
    make(tmp_path, "https://one.example.com")
    with pytest.raises(Exception, match="one.example.com"):
        add_remote(tmp_path, "https://two.example.com", TOKEN)


def test_removing_the_remote_deletes_the_token(tmp_path: Path) -> None:
    make(tmp_path, "https://one.example.com")
    assert remove_remote(tmp_path) == "https://one.example.com"
    assert not (tmp_path / ".taskops" / "remote.json").exists()
    assert read_remote(tmp_path) is None


# ── events ──────────────────────────────────────────────────────────────────────────────

def test_a_plan_reaches_the_server_without_anybody_pushing(tmp_path: Path, base: str,
                                                           fake: Fake) -> None:
    """The three-person simulacro ran on "push after every change", and the rule was broken
    within minutes by the person who wrote it. A plan on a remote project now shares itself;
    the manual `push` remains for everything else and finds nothing left to send."""
    plan(make(tmp_path, base), [{"title": "wire the client"}], actor="dev:berna")
    assert any(event["kind"] == "created" for event in fake.events)
    assert push(tmp_path).accepted == 0, "the plan already carried itself"


def test_a_second_push_sends_nothing_and_the_server_grows_by_nothing(
        tmp_path: Path, base: str, fake: Fake) -> None:
    """Idempotency, asserted where it matters: not "the second call succeeded" but "the log
    on the server is the same length"."""
    plan(make(tmp_path, base), [{"title": "wire the client"}], actor="dev:berna")
    push(tmp_path)
    held = len(fake.events)
    assert push(tmp_path).accepted == 0
    assert len(fake.events) == held


def test_nothing_is_marked_exported_when_the_push_never_lands(tmp_path: Path) -> None:
    """A push cut off mid-flight must re-send. Marking first and posting after is how an
    event that never left the machine becomes an event nothing will ever send again."""
    plan(make(tmp_path, "http://127.0.0.1:1"), [{"title": "unsent"}], actor="dev:berna")
    with pytest.raises(Exception, match="could not reach"):
        push(tmp_path)
    with Store(tmp_path) as store:
        assert store.events.unexported(), "events were marked exported without a 200"


def test_a_pull_puts_the_card_on_the_board(tmp_path: Path, base: str) -> None:
    """The materialisation bug, pinned. Relaying without replaying leaves every event in the
    table and the board empty, which is precisely what a teammate saw and reported."""
    mine = make(tmp_path / "mine", base)
    plan(mine, [{"title": "wire the client"}], actor="dev:berna")
    push(mine)
    theirs = make(tmp_path / "theirs", base)
    assert pull(theirs).events_in > 0
    titles = [card["task"]["title"]
              for column in board(theirs)["columns"] for card in column["cards"]]
    assert "wire the client" in titles, "the events arrived and the board stayed empty"


def test_the_cursor_advances_and_is_the_servers_number(tmp_path: Path, base: str,
                                                       fake: Fake) -> None:
    plan(make(tmp_path, base), [{"title": "wire the client"}], actor="dev:berna")
    push(tmp_path)
    saved = read_remote(tmp_path)
    assert saved is not None and saved["cursor"] == len(fake.events)


def test_a_pull_re_reads_a_server_that_forgot_the_cursor(tmp_path: Path, base: str) -> None:
    """A store recreated on the server answers from 0. Re-importing everything is a no-op,
    not a repair job — content-hash ids make `relay` accept each event exactly once."""
    plan(make(tmp_path / "mine", base), [{"title": "wire the client"}], actor="dev:berna")
    push(tmp_path / "mine")
    theirs = make(tmp_path / "theirs", base)
    pull(theirs)
    assert pull(theirs).events_in == 0


# ── reports ─────────────────────────────────────────────────────────────────────────────

def test_a_report_the_server_lacks_goes_up(tmp_path: Path, base: str, fake: Fake) -> None:
    plan(make(tmp_path, base), [{"title": "wire the client"}], actor="dev:berna")
    label = write_report(tmp_path).stem
    assert label in push(tmp_path).reports.uploaded
    assert label in fake.reports


def test_a_newer_report_on_the_server_comes_down(tmp_path: Path, base: str,
                                                 fake: Fake) -> None:
    make(tmp_path, base)
    fake.reports["all"] = ("<!-- taskops:report date=all max_seq=99 -->\ntheirs\n", 99)
    assert "all" in pull(tmp_path).reports.downloaded
    assert "theirs" in (tmp_path / ".taskops" / "reports" / "all.md").read_text()


def test_a_conflicting_report_is_not_overwritten_and_names_both_seqs(
        tmp_path: Path, base: str, fake: Fake) -> None:
    """Equal fingerprints, different text: two narrations of the same dossier, one of which
    a person may have written. Nobody can decide that automatically, so nothing moves and the
    message has to carry both numbers and both ways out."""
    make(tmp_path, base)
    ours, theirs = _same_seq_reports()
    _lay(tmp_path, "all", ours)
    fake.reports["all"] = (theirs, 7)
    swap = push(tmp_path).reports
    assert swap.uploaded == [] and swap.conflicts
    assert "seq 7" in swap.conflicts[0] and "--force" in swap.conflicts[0]
    assert fake.reports["all"][0] == theirs, "the server's narration was overwritten"
    assert (tmp_path / ".taskops" / "reports" / "all.md").read_text() == ours


def test_force_is_the_valve_and_it_takes_the_local_copy(tmp_path: Path, base: str,
                                                        fake: Fake) -> None:
    make(tmp_path, base)
    ours, theirs = _same_seq_reports()
    _lay(tmp_path, "all", ours)
    fake.reports["all"] = (theirs, 7)
    assert push(tmp_path, force=True).reports.uploaded == ["all"]
    assert fake.reports["all"][0] == ours


def test_a_server_without_the_listing_route_still_syncs(tmp_path: Path, base: str,
                                                        fake: Fake) -> None:
    """The contract froze before anyone noticed a client cannot ask for a report it has no
    way to learn exists. A 400 on the proposed listing must degrade to "reconcile what is on
    this disk", never fail the whole command."""
    fake.serve_labels = False
    plan(make(tmp_path, base), [{"title": "wire the client"}], actor="dev:berna")
    label = write_report(tmp_path).stem
    assert push(tmp_path).reports.uploaded == [label]


# ── being offline ───────────────────────────────────────────────────────────────────────

def test_an_unreachable_server_says_so_and_says_the_board_is_still_yours(
        tmp_path: Path) -> None:
    make(tmp_path, "http://127.0.0.1:1")
    with pytest.raises(Exception, match="could not reach http://127.0.0.1:1"):
        pull(tmp_path)


def test_a_project_with_no_remote_is_told_how_to_get_one(tmp_path: Path) -> None:
    make(tmp_path)
    with pytest.raises(Exception, match="taskops remote add"):
        push(tmp_path)


def _same_seq_reports() -> tuple[str, str]:
    header = "<!-- taskops:report date=all max_seq=7 -->"
    return f"{header}\n\n## narration\n\nmine.\n", f"{header}\n\n## narration\n\ntheirs.\n"


def _lay(root: Path, label: str, text: str) -> None:
    path = root / ".taskops" / "reports" / f"{label}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_push_sends_a_board_the_git_path_already_exported(
        tmp_path: Path, base: str) -> None:
    """The bug the first real project hit: `sync` had marked every event exported for the
    git log, and a push that drained the `exported` flag sent nothing — a 370-event board
    went up as `0 event(s) out`, silently. Push keeps its own cursor now."""
    from taskops.usecases import sync

    # No remote yet, so the plan lands locally exactly as a git-only project's would; the
    # remote arrives AFTER, which is precisely the adoption case this test pins.
    init(tmp_path, install_git_hooks=False)
    plan(tmp_path, [{"title": "Ya exportada por git"}], actor="dev:t")
    sync(tmp_path)                       # marks everything exported, as a git project would be
    add_remote(tmp_path, base, TOKEN)
    done = push(tmp_path)
    assert done.accepted > 0, "a git-synced board must still push to a server"
