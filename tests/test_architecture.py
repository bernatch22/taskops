"""The layering of ARCHITECTURE.md §4 and §14, pinned by AST — written before
the code it constrains.

A rule with no test is a suggestion. Every assertion here is a v1 bug that
cost real time; the docstring of each test names it.

The layering is a total order and imports only point DOWN. Two things that
look like exceptions and are not: `board.py` sits ABOVE `verbs/` (it dispatches
the registry), and `gitwork/` is a client capability rather than a transport —
so `mcp/` may use it without breaking "no transport imports another transport".
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "taskops"

# module (dotted, relative to `taskops`) prefix -> level
LEVELS: list[tuple[str, int]] = [
    ("_errors", 0),
    ("_ids", 0),
    ("_clock", 0),
    ("_json", 0),
    ("_locate", 0),
    ("_version", 0),
    ("core", 1),
    ("store", 2),
    ("verbs", 3),
    ("board", 4),
    ("gitwork", 4),
    ("mcp", 5),
    ("http", 5),
    ("cli", 6),
    ("__init__", 99),  # the public facade may import anything
]

MAX_LINES = 200  # v1's 70 produced artificial splits; 200 forces cohesion instead


def modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if p.name != "__init__.py" or p.parent == SRC)


def dotted(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    return ".".join(rel.parts)


def level_of(name: str) -> int:
    top = name.split(".")[0]
    for prefix, level in LEVELS:
        if top == prefix:
            return level
    raise AssertionError(f"{name} is in no layer — add it to LEVELS in this test")


def package_of(name: str) -> str:
    return name.split(".")[0]


def imports_of(path: Path) -> list[str]:
    """First-party `taskops.*` imports, returned dotted-relative to `taskops`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    own = dotted(path)
    depth_base = own.split(".")[:-1]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:  # relative: `from .x import y` / `from ..core import z`
                base = depth_base[: len(depth_base) - (node.level - 1)]
                target = ".".join([*base, node.module]) if node.module else ".".join(base)
                found.append(target)
            elif node.module and node.module.startswith("taskops"):
                found.append(node.module[len("taskops") :].lstrip("."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("taskops"):
                    found.append(alias.name[len("taskops") :].lstrip("."))
    return [f for f in found if f]


def stdlib_imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.add(node.module.split(".")[0])
    return names


def source_of(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_module_is_in_a_layer() -> None:
    for path in modules():
        level_of(dotted(path))


def test_imports_only_point_down() -> None:
    """A cycle between layers is how v1 ended up with 25 places re-deciding routing."""
    for path in modules():
        name = dotted(path)
        mine = level_of(name)
        for target in imports_of(path):
            theirs = level_of(target)
            assert theirs <= mine, f"{name} (L{mine}) imports {target} (L{theirs}) — upward"


def test_transports_do_not_import_each_other() -> None:
    """mcp/, http/ are peers: neither may reach into the other."""
    for path in modules():
        name = dotted(path)
        if level_of(name) != 5:
            continue
        for target in imports_of(path):
            if level_of(target) == 5:
                assert package_of(target) == package_of(name), (
                    f"{name} imports peer transport {target} — go through board/verbs instead"
                )


def test_sqlite_only_in_store() -> None:
    """The only place that knows SQL exists."""
    for path in modules():
        if "sqlite3" in stdlib_imports_of(path):
            assert dotted(path).startswith("store."), f"{dotted(path)} imports sqlite3"


def test_subprocess_only_in_gitwork_run() -> None:
    """v1 had four subprocess wrappers; one swallowed stderr and turned a refused
    push into 'somebody landed while this ran', in an infinite loop."""
    for path in modules():
        if "subprocess" in stdlib_imports_of(path):
            assert dotted(path) == "gitwork.run", f"{dotted(path)} imports subprocess"


def test_only_clock_reads_the_clock() -> None:
    """v1 let a stray strftime through and a report cut days in two timezones."""
    allowed = {"_clock", "core.hours"}
    needles = ("time.time(", "time.monotonic(", "datetime.now(", ".strftime(", "time.localtime(")
    for path in modules():
        name = dotted(path)
        if name in allowed:
            continue
        src = source_of(path)
        for needle in needles:
            assert needle not in src, f"{name} reads the clock ({needle}) — use _clock.now()"


def test_core_is_pure() -> None:
    """core/ is level 1: no I/O, no sqlite, no subprocess, no network, no env."""
    banned = {"sqlite3", "subprocess", "socket", "http", "urllib", "os", "shutil"}
    for path in modules():
        if not dotted(path).startswith("core."):
            continue
        leaked = banned & stdlib_imports_of(path)
        assert not leaked, f"{dotted(path)} imports {leaked} — core/ must stay pure"


def test_verbs_never_run_git_or_render() -> None:
    """v1's `recover` ran git porcelain on the SERVER and reported paths from a
    machine that was not the caller's. Git lives in the client, always."""
    for path in modules():
        if not dotted(path).startswith("verbs."):
            continue
        for target in imports_of(path):
            assert not target.startswith(("gitwork", "mcp", "http", "board")), (
                f"{dotted(path)} imports {target} — a verb is pure store+core"
            )


def test_no_module_exceeds_the_line_budget() -> None:
    for path in modules():
        lines = len(source_of(path).splitlines())
        assert lines <= MAX_LINES, f"{dotted(path)} is {lines} lines (budget {MAX_LINES})"


def test_no_assert_for_invariants_in_src() -> None:
    """`python -O` deletes asserts. Invariants raise real errors."""
    for path in modules():
        tree = ast.parse(source_of(path), filename=str(path))
        assert not any(isinstance(n, ast.Assert) for n in ast.walk(tree)), (
            f"{dotted(path)} uses assert for an invariant — raise a TaskopsError"
        )


def test_future_annotations_everywhere() -> None:
    for path in modules():
        assert "from __future__ import annotations" in source_of(path), dotted(path)
