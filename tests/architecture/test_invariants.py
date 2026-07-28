"""The hard rules, executable.

Prose in ARCHITECTURE.md is enforced by whoever happens to review the diff. Here
a violation is a failing test.
"""

from __future__ import annotations

import pytest

from tests.architecture.walk import (
    asserts_in,
    calls_in,
    classes_of,
    code_lines,
    imports_of,
    long_functions,
    modules_under,
    source_of,
)

MAX_CODE_LINES = 70
"""The real budget: lines of CODE per module, docstrings and comments excluded.

megabrain-v3 counts RAW lines at 100, and that rule punishes the one thing both
codebases are built on — a written reason for every decision. A file there stays
under the ceiling by deleting the explanation, which is the opposite of the intent.
Measuring code makes the budget say what it means: no module may hold more than
~70 lines of logic, and it may carry as much reasoning as that logic needs.
"""

MAX_FILE_LINES = 160
"""A raw ceiling all the same. Not about complexity — about a file that has become
a document with some code in it, which wants to be a doc plus a module."""

MAX_FUNC_LINES = 30

LAYER_ZERO = (
    "taskops._types",
    "taskops._errors",
    "taskops._ids",
    "taskops._clock",
    "taskops._version",
)

_CLASS_NAMES = {name for m in modules_under("") for name, _ in classes_of(m)}


def test_the_walker_actually_sees_the_package() -> None:
    """Anti-vacuum guard: every invariant below iterates `modules_under`, so a
    walker that silently found nothing would turn this whole file green."""
    assert len(modules_under("")) >= 5


def test_layer_zero_imports_nothing_from_the_package() -> None:
    """The vocabulary sits UNDER everything and depends on nothing.

    That is what lets `taskops/__init__` expose the error types eagerly while
    every other layer stays lazy. One import from a sibling turns the base of the
    package into a graph, and the failure arrives later as a circular import from
    some unrelated module.
    """
    for module in LAYER_ZERO:
        siblings = [i for i in imports_of(module) if i.startswith("taskops")]
        assert not siblings, f"{module} is layer 0 but imports {siblings}"


def test_sql_lives_only_in_storage() -> None:
    """The Store is the sole owner of the schema.

    A query written anywhere else is a second place that knows the column order,
    and it is always the one nobody updates when the schema moves.
    """
    for module in modules_under(""):
        if module.startswith("taskops.storage"):
            continue
        src = source_of(module)
        assert "db.execute" not in src, f"{module} runs SQL outside storage/"
        assert "SELECT " not in src.upper(), f"{module} runs SQL outside storage/"


def test_contracts_import_only_layer_zero() -> None:
    """Layer 1 is types and nothing else.

    Six readers consume these — storage, engine, render, and the three
    transports — so a contract that imported storage would make the wire format
    depend on the database, and the UI's mirror of these types could not be
    generated from them.
    """
    allowed = set(LAYER_ZERO)
    for module in modules_under("contracts"):
        inside = {i for i in imports_of(module) if i.startswith("taskops")}
        stray = {i for i in inside if i not in allowed and not i.startswith("taskops.contracts")}
        assert not stray, f"{module} is layer 1 but imports {stray}"


def test_transports_never_reach_past_the_use_cases() -> None:
    """THE anti-drift rule. Three surfaces, one behaviour.

    A transport that imported storage or engine directly would be a fourth place
    where a decision lives, and the CLI, MCP and HTTP answers would start
    disagreeing about what "done" requires — which is the exact failure this
    architecture is shaped to prevent. Transports may touch contracts (to name
    what they serialize) and render (to turn it into text), never the machinery.
    """
    for module in modules_under("transports"):
        for imported in imports_of(module):
            assert not imported.startswith("taskops.storage"), (
                f"{module} imports storage — go through usecases/"
            )
            assert not imported.startswith("taskops.engine"), (
                f"{module} imports engine — go through usecases/"
            )


def test_the_state_machine_has_exactly_one_home() -> None:
    """Every legal status move is declared in `engine.machine` and nowhere else.

    A transition table plus one `if status == "done"` somewhere convenient is two
    state machines, and the convenient one is always the one that forgets the
    guard. Modules may READ a status; only the machine may decide a move.
    """
    for module in modules_under(""):
        if module in ("taskops.engine.machine", "taskops._types"):
            continue
        src = source_of(module)
        for spelling in ("TRANSITIONS", "GUARDS"):
            assert f"{spelling} =" not in src, (
                f"{module} declares {spelling} — the machine owns transitions"
            )


def test_only_the_clock_module_reads_the_clock() -> None:
    """Leases expire, so "now" is load-bearing and must be injectable.

    Every direct `time.time()` is a place a test of expiry would have to sleep
    through in real seconds. Routing them all through `_clock.now` is what makes
    "the agent crashed and its lease lapsed" a microsecond-long test.
    """
    for module in modules_under(""):
        if module == "taskops._clock":
            continue
        calls = calls_in(module)
        for banned in ("time.time", "time.monotonic", "datetime.now"):
            assert banned not in calls, f"{module} calls {banned} — use _clock.now"


def test_render_is_pure_text() -> None:
    """`render/` turns a contract into a string, so it can never fail on I/O.

    That is what lets the same renderer serve the CLI, the MCP reply and the
    UI's markdown export, and it is why a rendering bug can be reproduced
    from a literal dict with no database in sight.
    """
    for module in modules_under("render"):
        for imported in imports_of(module):
            for banned in (
                "taskops.storage",
                "taskops.engine",
                "taskops.usecases",
                "sqlite3",
                "subprocess",
            ):
                assert not imported.startswith(banned), f"{module} imports {banned}"


def test_the_engine_is_sync() -> None:
    """sqlite and a state machine. Only the http transport may be async, and it
    calls the sync use cases from a threadpool. No async twin, ever."""
    for module in modules_under(""):
        if module.startswith("taskops.transports.http"):
            continue
        assert "asyncio.run(" not in source_of(module), f"{module} runs an event loop"


def test_no_multiple_inheritance_between_project_classes() -> None:
    """Composition over inheritance, enforced where it bites.

    Mixing ONE project class with builtins stays legal, because that is the
    deliberate trick in `_errors.py`: `NoSuchTask(TaskopsError, KeyError)` keeps
    an `except KeyError` caller in the wild working.
    """
    for module in modules_under(""):
        for cls, bases in classes_of(module):
            project = [b for b in bases if b in _CLASS_NAMES]
            assert len(project) <= 1, f"{module}.{cls} inherits from {project}"


def test_shipped_code_never_asserts() -> None:
    """`python -O` deletes every assert, and people run libraries under -O.

    A guard that vanishes under an optimisation flag is worse than no guard: the
    value it swore was fine flows on and fails somewhere unrelated. Real
    preconditions raise. Test files are exempt — that is where assert lives.
    """
    for module in modules_under(""):
        lines = asserts_in(module)
        assert not lines, f"{module}: assert at line(s) {lines} — raise instead"


@pytest.mark.parametrize("module", list(modules_under("")))
def test_no_module_exceeds_the_code_budget(module: str) -> None:
    n = code_lines(module)
    assert n <= MAX_CODE_LINES, f"{module}: {n} code lines (max {MAX_CODE_LINES})"


@pytest.mark.parametrize("module", list(modules_under("")))
def test_no_file_becomes_a_document(module: str) -> None:
    n = len(source_of(module).splitlines())
    assert n <= MAX_FILE_LINES, f"{module}: {n} lines (max {MAX_FILE_LINES})"


@pytest.mark.parametrize("module", list(modules_under("")))
def test_no_function_exceeds_the_line_budget(module: str) -> None:
    over = long_functions(module, MAX_FUNC_LINES)
    assert not over, f"{module}: {over} (max {MAX_FUNC_LINES} lines)"


def test_the_plugin_declares_the_package_version() -> None:
    """The plugin's manifest is what Claude Code SHOWS a user, and it drifted: the package was
    0.2.0 everywhere and the plugin still said 0.1.0, so anybody who installed it read the wrong
    number from the one place they were looking. A number copied by hand is a number that goes
    stale; this is the copy being checked."""
    import json

    from taskops._version import __version__
    from tests.architecture.walk import SRC

    manifest = json.loads((SRC.parents[1] / "plugin" / ".claude-plugin" / "plugin.json")
                          .read_text(encoding="utf-8"))
    assert manifest["version"] == __version__, (
        f"plugin.json says {manifest['version']} and the package is {__version__}")
