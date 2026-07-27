"""Static reflection over the package — the machinery the invariant tests run on.

Pure stdlib `ast`: nothing here imports the modules under test, so a module with
a syntax error fails its OWN test instead of collapsing the whole suite at
collection time.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "taskops"


def modules_under(package: str) -> list[str]:
    """Dotted names of every module under `src/taskops/<package>`."""
    root = SRC / package if package else SRC
    return sorted(
        "taskops." + p.relative_to(SRC).with_suffix("").as_posix().replace("/", ".")
        for p in root.rglob("*.py")
    )


def _path(module: str) -> Path:
    return SRC / (module.removeprefix("taskops.").replace(".", "/") + ".py")


@lru_cache(maxsize=None)
def source_of(module: str) -> str:
    return _path(module).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _tree(module: str) -> ast.Module:
    return ast.parse(source_of(module), filename=module)


def imports_of(module: str) -> set[str]:
    """Absolute dotted targets of every import, relative ones resolved."""
    pkg = module.rsplit(".", 1)[0]
    out: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(_resolve(node, pkg))
    return out


def _resolve(node: ast.ImportFrom, pkg: str) -> str:
    """A relative import -> the absolute dotted module it names.

    `from . import x` inside `a.b.c` means `a.b`; level 2 means `a`. Getting
    this wrong would make every layering test pass by comparing to "".
    """
    if not node.level:
        return node.module or ""
    base = pkg.split(".")
    up = node.level - 1
    root = ".".join(base[: len(base) - up] if up else base)
    return f"{root}.{node.module}" if node.module else root


def classes_of(module: str) -> list[tuple[str, list[str]]]:
    """`(class_name, base_names)` for every class; TypedDicts and Protocols out.

    Those two are data and contracts: `class X(Base, total=False)` is the only
    PEP 563-safe way to declare an optional field, so they are exempt from the
    shallow-hierarchy rule by construction.
    """
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(_tree(module)):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [_base_name(b) for b in node.bases]
        if "TypedDict" in bases or "Protocol" in bases:
            continue
        out.append((node.name, [b for b in bases if b]))
    return out


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def asserts_in(module: str) -> list[int]:
    """Line numbers of every `assert` statement in a shipped module."""
    return [node.lineno for node in ast.walk(_tree(module)) if isinstance(node, ast.Assert)]


def calls_in(module: str) -> set[str]:
    """Dotted names of everything CALLED, as written (`time.time`, `now`).

    Written-form matching is the point: these invariants are about what the
    source says, and resolving aliases would let `import time as t` slip past
    the very rule it breaks.
    """
    out: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name:
                out.add(name)
    return out


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def code_lines(module: str) -> int:
    """Lines that are CODE: no blanks, no comments, no docstrings.

    This is the number the file budget is about. Counting raw lines punishes the
    one thing this codebase is built on — a documented reason for every decision —
    and rewards deleting the explanation to fit. It also cannot be gamed the other
    way: logic does not fit inside a docstring.
    """
    skip = _docstring_lines(module) | class_attribute_docs(module) | _prose_assignments(module)
    n = 0
    for i, line in enumerate(source_of(module).splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or i in skip:
            continue
        n += 1
    return n


def _prose_assignments(module: str) -> set[int]:
    """Lines of a module-level assignment whose value is only string literals.

    `TOOL_DESCRIPTION = ("…" "…")` is PROSE that happens to be addressable from Python. It contains no
    logic by construction — a string literal cannot — so charging it to the code budget punishes the
    same thing raw line counting did, and `transports/mcp/_descriptions` is a whole module of it.

    Deliberately narrow: only module level, only when every part is a string constant. An f-string is
    excluded, because interpolation is behaviour.
    """
    out: set[int] = set()
    for node in _tree(module).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        if _only_strings(node.value):
            out |= set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return out


def _only_strings(node: ast.expr) -> bool:
    """A string constant, or a concatenation of nothing but string constants."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _only_strings(node.left) and _only_strings(node.right)
    return False


def _docstring_lines(module: str) -> set[int]:
    """Every line occupied by a docstring — module, class or function.

    A docstring is the first statement of its body and a bare string constant, so
    finding them needs no heuristics about quotes: the parser already knows.
    """
    out: set[int] = set()
    tree = _tree(module)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        out |= _span_of_docstring(node.body)
    # Module-level string statements that are NOT the first one: the attribute
    # docstrings this codebase uses under a constant (`LEASE_TTL = 900` then a
    # string). They document, so they count as documentation.
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            out |= set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return out


def _span_of_docstring(body: list[ast.stmt]) -> set[int]:
    if not body:
        return set()
    first = body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        return set()
    return set(range(first.lineno, (first.end_lineno or first.lineno) + 1))


def class_attribute_docs(module: str) -> set[int]:
    """Docstring lines that follow a class-level annotation (contract fields).

    `contracts/` documents each field with a string under it, which is where most
    of the reasoning in this package lives. Those lines are documentation by any
    reading, so the code-line count must not charge for them.
    """
    out: set[int] = set()
    for node in ast.walk(_tree(module)):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                    and isinstance(stmt.value.value, str):
                out |= set(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
    return out


def long_functions(module: str, limit: int) -> list[str]:
    """`name:lines` for every function whose BODY exceeds `limit` lines.

    Decorators, signature and docstring excluded: the budget is about how much
    logic one head must hold, and a thorough docstring is not logic.
    """
    out: list[str] = []
    for node in ast.walk(_tree(module)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = _body_without_docstring(node)
        if not body:
            continue
        n = (body[-1].end_lineno or 0) - body[0].lineno + 1
        if n > limit:
            out.append(f"{node.name}:{n}")
    return out


def _body_without_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return body[1:]
    return body
