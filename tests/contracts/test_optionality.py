"""The trap that would silently break every MCP schema.

Under `from __future__ import annotations` every annotation is a string, so a
TypedDict cannot see a `NotRequired[...]` marker at class-creation time:
`__optional_keys__` comes back EMPTY and every field reads as required to anything
that introspects the class. The MCP schema generator does exactly that, so the
whole tool surface would advertise every optional parameter as mandatory — and a
host that validates would reject a perfectly good call.

`contracts/` therefore declares optionality with the `total=False` SPLIT, which is
class-level and immune. These tests pin it: they fail the day somebody reaches for
the more obvious spelling.
"""

from __future__ import annotations

import pytest

from taskops.contracts import (
    AskParams,
    NextParams,
    PlanParams,
    ReportParams,
    UpdateParams,
)

TOOL_PARAMS = (PlanParams, NextParams, UpdateParams, AskParams, ReportParams)


@pytest.mark.parametrize("spec", TOOL_PARAMS)
def test_every_tool_requires_the_repository(spec: type) -> None:
    """`repo_path` is the one argument no tool may guess."""
    assert "repo_path" in spec.__required_keys__


@pytest.mark.parametrize("spec", TOOL_PARAMS)
def test_optional_keys_are_actually_visible(spec: type) -> None:
    """The anti-NotRequired guard, stated as the property that matters.

    Every one of these contracts has at least one optional field. If any reports
    none, the marker has been written in the form PEP 563 erases.
    """
    assert spec.__optional_keys__, f"{spec.__name__} reports no optional keys"


def test_required_and_optional_partition_the_fields() -> None:
    """No field may be in both sets, and none may be in neither.

    A field in neither is invisible to the schema generator, so an agent would
    never learn it exists — the failure mode that motivated generating the schema
    from the contract in the first place.
    """
    for spec in TOOL_PARAMS:
        required = set(spec.__required_keys__)
        optional = set(spec.__optional_keys__)
        annotated = set(spec.__annotations__) | {
            key for base in spec.__mro__[1:] for key in getattr(base, "__annotations__", {})
        }
        assert not (required & optional), f"{spec.__name__}: overlap"
        assert annotated <= (required | optional), f"{spec.__name__}: unclassified field"


def test_plan_requires_the_tasks_it_is_planning() -> None:
    """A `plan` call with no tasks is not a plan; the schema must say so."""
    assert "tasks" in PlanParams.__required_keys__


def test_update_requires_a_task() -> None:
    assert "task" in UpdateParams.__required_keys__


def test_next_requires_nothing_but_the_repository() -> None:
    """The DEFAULT call an agent makes has to be answerable with no arguments.

    Every field beyond the repository is a restriction, and an agent that just
    wants work should not have to invent an actor id to ask for it.
    """
    assert NextParams.__required_keys__ == frozenset({"repo_path"})
