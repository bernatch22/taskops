"""The Editor's doors (ARCHITECTURE.md §22): the inhabited directories of a
checkout, one worktree scanned and read, and the HTTP door over them — against
real repositories in tmp_path and a real server on a real port. No mocks: git
and the disk are the point, and every wall here is a path a browser could send.
"""

from __future__ import annotations

import os
import json
import threading
from typing import Any, Iterator
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from taskops import _clock
from taskops.http import editor, treewatch
from tests.test_git import repo
from taskops.gitwork import run, scan, trees, reading, inhabited
from taskops.http.server import BoardServer, serve

BOARD = "facturador"
BERNA = "dev:berna"
CARD = "tk-a11111"
CHAPTER = "ms/mvp"


def checkout(tmp_path: Path) -> Path:
    """A checkout with a chapter tree and a card tree, and every state a file can
    be in inside the card's: modified, staged, added, untracked, clean, deleted
    from the disk, ignored, pruned, binary, and two symlinks — one that stays
    inside the tree and one that leaves it."""
    root = repo(tmp_path, "checkout")
    (root / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("import os\n\ndef main():\n    return 1\n", encoding="utf-8")
    (root / "src" / "old.py").write_text("gone = True\n", encoding="utf-8")
    (root / "src" / "tidy.py").write_text("tidy = True\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "the app", cwd=root)
    tree = trees.ensure_card(root, CARD, CARD, CHAPTER)
    (tree / "src" / "app.py").write_text(
        "import os\n\ndef main():\n    return 2\n\ndef extra():\n    pass\n", encoding="utf-8"
    )
    (tree / "src" / "new.py").write_text("new = 1\n", encoding="utf-8")
    (tree / "src" / "staged.py").write_text("staged = 1\n", encoding="utf-8")
    run.must("add", "src/staged.py", cwd=tree)
    (tree / "src" / "tidy.py").write_text("tidy = False\n", encoding="utf-8")
    run.must("add", "src/tidy.py", cwd=tree)
    (tree / "src" / "old.py").unlink()
    (tree / "node_modules" / "left-pad").mkdir(parents=True)
    (tree / "node_modules" / "left-pad" / "index.js").write_text("x", encoding="utf-8")
    (tree / "dist").mkdir()
    (tree / "dist" / "bundle.js").write_text("y", encoding="utf-8")
    (tree / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")
    (tree / "debug.log").write_text("ignored\n", encoding="utf-8")
    os.symlink(tree / "src" / "app.py", tree / "alias.py")
    os.symlink(Path("/etc/hosts"), tree / "escape")
    return root


def card_tree(root: Path) -> Path:
    return trees.card_tree(root, CARD)


# ── the inhabited directories ───────────────────────────────────────────────


def test_the_checkout_is_listed_first_and_every_tree_after_it(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    found = inhabited.listed(root)
    assert [t.name for t in found] == ["main", "_ms-mvp", CARD]
    assert found[0].dir == "" and found[0].branch == "main" and len(found[0].head) == 40
    assert found[2].dir == f".taskops/trees/{CARD}" and found[2].branch == CARD


def test_a_stray_directory_under_trees_is_not_a_worktree(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    (trees.trees_dir(root) / "not-a-tree").mkdir()
    assert "not-a-tree" not in [t.name for t in inhabited.listed(root)]
    assert inhabited.locate(root, "not-a-tree") is None


@pytest.mark.parametrize("name", ["..", "../..", "tk-a11111/src", "/etc", "", "tk-nope", ".git"])
def test_a_tree_name_is_a_directory_name_or_nothing(tmp_path: Path, name: str) -> None:
    root = checkout(tmp_path)
    assert inhabited.locate(root, name) is None


def test_main_and_a_card_locate_to_their_own_directories(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    assert inhabited.locate(root, "main") == root
    assert inhabited.locate(root, CARD) == card_tree(root)


@pytest.mark.parametrize(
    "rel",
    [
        "../checkout/README.md",
        "/etc/hosts",
        "src//app.py",
        "./src/app.py",
        ".git/config",
        ".git",
        "src",  # a directory, not a file
        "escape",  # a symlink that leaves the tree
        "src/\napp.py",
        "src\\app.py",
        "",
    ],
)
def test_a_path_that_leaves_the_tree_is_refused_never_repaired(tmp_path: Path, rel: str) -> None:
    """One wall for every shape: the resolved file must sit under the resolved
    tree, and `.git` is not code. A `..` normalised into something acceptable
    would be the bug, not the fix."""
    assert inhabited.inside(card_tree(checkout(tmp_path)), rel) is None


def test_a_plain_path_and_a_symlink_that_stays_inside_both_resolve(tmp_path: Path) -> None:
    tree = card_tree(checkout(tmp_path))
    assert inhabited.inside(tree, "src/app.py") == (tree / "src" / "app.py").resolve()
    assert inhabited.inside(tree, "alias.py") == (tree / "src" / "app.py").resolve()


# ── the scan ────────────────────────────────────────────────────────────────


def test_the_scan_names_every_project_file_with_its_git_state(tmp_path: Path) -> None:
    taken = scan.take(card_tree(checkout(tmp_path)))
    states = {path: entry.state for path, entry in taken.files.items()}
    assert states == {
        "README.md": "clean",
        ".gitignore": "clean",
        "docs/notes.md": "clean",
        "src/app.py": "modified",
        "src/new.py": "untracked",
        "src/staged.py": "added",
        "src/tidy.py": "staged",
        "logo.png": "untracked",
        "alias.py": "untracked",
        "escape": "untracked",
    }
    assert taken.capped is False and taken.total == len(states)


def test_what_git_ignores_and_what_nobody_reads_are_both_left_out(tmp_path: Path) -> None:
    """`node_modules` by the tree's own .gitignore, `debug.log` likewise, and
    `dist/` — NOT ignored here — by this package's exclude list, pruned at the
    directory rather than walked and filtered."""
    taken = scan.take(card_tree(checkout(tmp_path)))
    assert not any(path.startswith(("node_modules/", "dist/")) for path in taken.files)
    assert "debug.log" not in taken.files
    assert scan.excluded("a/node_modules/b.js") and scan.excluded(".taskops/trees/tk-x/a")
    assert not scan.excluded("src/distribution.py")


def test_a_file_deleted_from_the_disk_is_not_drawn(tmp_path: Path) -> None:
    """`src/old.py` is still in the index. The reader is looking at the disk."""
    assert "src/old.py" not in scan.take(card_tree(checkout(tmp_path))).files


def test_the_checkout_does_not_list_its_own_worktrees(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    taken = scan.take(root)
    assert not any(path.startswith(".taskops/trees/") for path in taken.files)
    assert taken.files["src/app.py"].state == "clean"


def test_the_listing_is_capped_and_says_so(tmp_path: Path) -> None:
    taken = scan.take(card_tree(checkout(tmp_path)), cap=3)
    assert taken.capped is True and taken.total == 10 and len(taken.files) == 3


def test_two_scans_differ_exactly_when_the_disk_moved(tmp_path: Path) -> None:
    tree = card_tree(checkout(tmp_path))
    before = scan.take(tree)
    assert not scan.differs(before, scan.take(tree))
    (tree / "src" / "new.py").write_text("new = 2\n\n", encoding="utf-8")
    assert scan.differs(before, scan.take(tree))


# ── reading one file ────────────────────────────────────────────────────────


def test_text_is_read_whole_and_a_binary_is_named_not_decoded(tmp_path: Path) -> None:
    tree = card_tree(checkout(tmp_path))
    got = reading.read(tree / "src" / "app.py")
    assert got.text.startswith("import os\n") and not got.binary and not got.truncated
    assert got.size == len(got.text.encode()) and got.mtime > 0
    logo = reading.read(tree / "logo.png")
    assert logo.binary and logo.text == "" and logo.size == 16


def test_a_file_over_the_cap_is_cut_and_flagged(tmp_path: Path) -> None:
    tree = card_tree(checkout(tmp_path))
    got = reading.read(tree / "src" / "app.py", cap=10)
    assert got.truncated and got.text == "import os\n" and got.size > 10


def test_the_base_is_the_merge_base_or_head_and_a_stranger_is_none(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    tree = card_tree(root)
    head = run.must("rev-parse", "HEAD", cwd=tree)
    assert reading.base_of(tree, "") == reading.Base("HEAD", head)
    assert reading.base_of(tree, CHAPTER) == reading.Base(CHAPTER, head)  # no commit yet
    assert reading.base_of(tree, "nope") is None
    assert reading.base_of(tree, "--output=/tmp/x") is None


def test_the_marks_say_which_lines_moved_on_the_file_as_it_stands(tmp_path: Path) -> None:
    """Line 4 changed (`return 1` → `return 2`) and lines 5–7 are new; the
    numbers are the NEW side's, because that is the file on screen."""
    tree = card_tree(checkout(tmp_path))
    base = reading.base_of(tree, "")
    assert base is not None
    assert reading.marks(tree, base.sha, "src/app.py", is_tracked=True, lines=7) == [
        reading.Mark(4, 4, "modified"),
        reading.Mark(5, 7, "added"),
    ]
    (tree / "src" / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    assert reading.marks(tree, base.sha, "src/app.py", is_tracked=True, lines=2) == [
        reading.Mark(1, 1, "deleted"),
    ]


def test_an_untracked_file_is_all_addition_and_so_is_its_patch(tmp_path: Path) -> None:
    tree = card_tree(checkout(tmp_path))
    base = reading.base_of(tree, "")
    assert base is not None
    assert not reading.tracked(tree, "src/new.py") and reading.tracked(tree, "src/app.py")
    assert reading.marks(tree, base.sha, "src/new.py", is_tracked=False, lines=1) == [
        reading.Mark(1, 1, "added")
    ]
    text, cut = reading.patch_of(tree, base.sha, "src/new.py", is_tracked=False)
    assert "+new = 1" in text and "/dev/null" in text and not cut
    text, _ = reading.patch_of(tree, base.sha, "src/app.py", is_tracked=True)
    assert "-    return 1" in text and "+    return 2" in text


# ── the door, over the wire ─────────────────────────────────────────────────


@pytest.fixture()
def window(tmp_path: Path) -> Iterator[BoardServer]:
    """A host that sits INSIDE a checkout — what `taskops ui` constructs."""
    root = checkout(tmp_path)
    httpd = serve(tmp_path / "boards", "127.0.0.1", 0, repo=root)
    httpd.mounts.create(BOARD)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture()
def host(tmp_path: Path) -> Iterator[BoardServer]:
    """`taskops serve`: boards, no checkout — the deployed instance's shape."""
    httpd = serve(tmp_path / "boards", "127.0.0.1", 0)
    httpd.mounts.create(BOARD)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _url(httpd: BoardServer, rest: str, board: str = BOARD) -> str:
    return f"http://127.0.0.1:{httpd.server_address[1]}/{board}/api/editor/{rest}"


def _token(httpd: BoardServer) -> str:
    token, _ = httpd.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    return token


def _get(url: str, token: str) -> tuple[int, dict[str, Any]]:
    joiner = "&" if "?" in url else "?"
    try:
        with urlopen(f"{url}{joiner}token={token}", timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as err:
        return err.code, json.loads(err.read().decode())


def test_the_trees_door_lists_the_checkout_first(window: BoardServer) -> None:
    status, body = _get(_url(window, "trees"), _token(window))
    assert status == 200 and body["ok"] is True
    assert [t["name"] for t in body["data"]["trees"]] == ["main", "_ms-mvp", CARD]
    assert body["data"]["checkout"] == str(window.mounts.repo)


def test_the_tree_door_answers_the_files_and_states_the_cap(window: BoardServer) -> None:
    status, body = _get(_url(window, f"tree?tree={CARD}"), _token(window))
    assert status == 200
    data = body["data"]
    assert data["tree"] == CARD and data["branch"] == CARD and len(data["head"]) == 40
    by_path = {f["path"]: f for f in data["files"]}
    assert by_path["src/app.py"]["state"] == "modified" and by_path["src/app.py"]["size"] > 0
    assert by_path["src/new.py"]["state"] == "untracked"
    assert set(data) == {"tree", "branch", "head", "files", "capped", "total", "cap", "seq", "at"}
    assert data["cap"] == scan.FILE_CAP and data["capped"] is False and data["seq"] >= 1


def test_the_file_door_answers_text_marks_and_the_base_it_used(window: BoardServer) -> None:
    status, body = _get(
        _url(window, f"file?tree={CARD}&path=src/app.py&base={CHAPTER.replace('/', '%2F')}"),
        _token(window),
    )
    assert status == 200
    data = body["data"]
    assert data["text"].startswith("import os\n") and data["binary"] is False
    assert data["tracked"] is True and data["truncated"] is False and data["cap"] == reading.CAP
    assert data["base"]["ref"] == CHAPTER and len(data["base"]["sha"]) == 40
    assert data["marks"] == [[4, 4, "modified"], [5, 7, "added"]]


def test_an_untracked_file_and_a_binary_are_both_said_plainly(window: BoardServer) -> None:
    _, body = _get(_url(window, f"file?tree={CARD}&path=src/new.py"), _token(window))
    assert body["data"]["tracked"] is False and body["data"]["marks"] == [[1, 1, "added"]]
    assert body["data"]["base"]["ref"] == "HEAD"
    _, body = _get(_url(window, f"file?tree={CARD}&path=logo.png"), _token(window))
    assert body["data"]["binary"] is True and body["data"]["text"] == ""
    assert body["data"]["marks"] == [] and body["data"]["size"] == 16


def test_the_diff_door_is_the_same_patch_the_worktrees_page_draws(window: BoardServer) -> None:
    status, body = _get(_url(window, "file?tree=main&path=src/app.py"), _token(window))
    assert status == 200 and body["data"]["marks"] == []  # the checkout is clean
    status, body = _get(_url(window, f"diff?tree={CARD}&path=src/app.py"), _token(window))
    assert status == 200
    assert set(body["data"]) == {"tree", "path", "base", "patch", "truncated", "cap"}
    assert "+    return 2" in body["data"]["patch"] and body["data"]["truncated"] is False


@pytest.mark.parametrize(
    "rest",
    [
        f"file?tree={CARD}&path=../checkout/README.md",
        f"file?tree={CARD}&path=/etc/hosts",
        f"file?tree={CARD}&path=.git/config",
        f"file?tree={CARD}&path=escape",
        f"diff?tree={CARD}&path=src",
        f"file?tree={CARD}",
    ],
)
def test_a_path_outside_the_tree_is_refused_with_one_sentence(window: BoardServer, rest: str) -> None:
    status, body = _get(_url(window, rest), _token(window))
    assert status == 400 and body["ok"] is False, rest
    assert "not a file inside that worktree" in body["error"]["message"], rest


def test_a_base_that_could_be_an_option_never_reaches_git(window: BoardServer) -> None:
    status, body = _get(
        _url(window, f"file?tree={CARD}&path=src/app.py&base=--output%3D/tmp/x"), _token(window)
    )
    assert status == 400 and "not a shape this door shows git" in body["error"]["message"]


def test_a_tree_nobody_has_is_a_stated_refusal(window: BoardServer) -> None:
    for name in ("tk-nope", "..", "tk-a11111%2Fsrc", ""):
        status, body = _get(_url(window, f"tree?tree={name}"), _token(window))
        assert status == 404 and "no worktree named" in body["error"]["message"], name
    status, body = _get(_url(window, "nonsense"), _token(window))
    assert status == 400 and "editor/trees" in body["error"]["message"]


def test_the_editor_door_is_the_same_token_door_as_rpc(window: BoardServer) -> None:
    with pytest.raises(HTTPError) as caught:
        urlopen(_url(window, "trees"), timeout=5)
    assert json.loads(caught.value.read().decode())["error"]["code"] == "refused"
    status, _ = _get(_url(window, "trees"), "not-a-real-token")
    assert status in (401, 403, 409)
    status, body = _get(_url(window, "trees", board="nadie"), _token(window))
    assert status == 404 and "no board named" in body["error"]["message"]


def test_a_host_with_no_checkout_says_so_and_names_taskops_ui(host: BoardServer) -> None:
    """The deployed instance serves pulled boards and holds no worktree: the
    page must draw the sentence, never an empty tree."""
    for rest in ("trees", f"tree?tree={CARD}", f"feed?tree={CARD}"):
        status, body = _get(_url(host, rest), _token(host))
        assert status == 404, rest
        assert body["error"]["message"] == editor.NO_CHECKOUT, rest
        assert "taskops ui" in body["error"]["message"]


def test_the_tree_feed_pokes_when_a_file_changes_on_disk(window: BoardServer) -> None:
    """A signal, not a payload: `{"type": "change", "tree", "seq"}` and nothing
    else, within a tick of the disk moving. Bounded by LINES rather than the
    clock, as the board feed's own test is."""
    stream = urlopen(f"{_url(window, f'feed?tree={CARD}')}&token={_token(window)}", timeout=10)
    assert b"hello" in stream.readline() + stream.readline()
    tree = card_tree(Path(str(window.mounts.repo)))
    (tree / "src" / "later.py").write_text("later = True\n", encoding="utf-8")
    seen: dict[str, Any] = {}
    for _ in range(12):
        line = stream.readline().decode().strip()
        if line.startswith("data:"):
            payload: Any = json.loads(line[5:])
            if payload.get("type") == "change":
                seen = payload
                break
    stream.close()
    assert seen.get("tree") == CARD and seen.get("seq", 0) >= 2, "the disk moved and the page was never told"
    assert set(seen) == {"type", "tree", "seq"}
    # And the listing a page refetches on that signal is the watcher's own reading.
    _, body = _get(_url(window, f"tree?tree={CARD}"), _token(window))
    assert "src/later.py" in {f["path"] for f in body["data"]["files"]}


def test_a_listing_nobody_watches_is_scanned_on_the_request(tmp_path: Path) -> None:
    from taskops.http import feed

    tree = card_tree(checkout(tmp_path))
    held = treewatch.Trees(feed.Hub())
    first = held.listing("b/editor/t", tree)
    (tree / "src" / "again.py").write_text("again = 1\n", encoding="utf-8")
    second = held.listing("b/editor/t", tree)
    assert "src/again.py" in second.scan.files and second.seq == first.seq + 1
    assert held.listing("b/editor/t", tree).seq == second.seq  # nothing moved: the seq holds
