"""The registry of specialist agents, and the two decisions a board can make with it.

taskops never invokes an agent. It knows WHICH agent a card belongs to (`agent_for`) and it
refuses a claim from an agent the card does not belong to (`fenced`) — the host session does
the spawning, with its own sub-agent tool. That split is not a limitation to work around: a
board that spawned processes would be a second, invisible fleet nobody asked for.

The registry is **Claude Code's own**, and that is the whole design:

```
plugin/agents/*.md      the DEFAULTS  — manager, worker, verifier, shipped with taskops
.claude/agents/*.md     the SPECIALISTS — the project's, exactly where Claude Code keeps them
```

There was briefly a `.taskops/agents/` with a copier that mirrored it into `.claude/agents/`,
and every part of that was a mistake. Claude Code's project subagents are already committed,
already shared with the team, and already the thing the host can spawn — inventing a parallel
registry bought nothing and cost a marker, a pruner, a name translator, and three bugs in an
afternoon. taskops reads the standard location and adds two OPTIONAL frontmatter keys of its
own (`labels`, `files`); Claude Code ignores keys it does not know, so one file serves both.

A repo file with the same `name` as a plugin file WINS, because a project must be able to
override the stock worker without forking the plugin.

A malformed file is a WARNING and a skip, never an exception: agent files are edited by hand,
and a typo in one of them must not be able to stop a session from starting.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from .._errors import BadRequest, TaskopsError
from ..contracts.agents import AgentSpec
from ._agentfile import parse_agent

__all__ = ["REGISTRY_DIR", "registry", "specialists", "agent_for", "agent_named", "fenced"]

REGISTRY_DIR = ".claude/agents"
"""Claude Code's own project scope — committed, team-shared, and the only place the host can
spawn from. Nested ones are scanned by Claude Code too; taskops reads the project root's,
which is where a repository keeps the specialists it means for everybody."""

OPTIONAL_KEYS = ("labels", "files", "claims")
"""What taskops adds to a subagent file, and what nothing else reads.

They live in the SAME frontmatter as `name`/`description`/`tools`/`model` because a project
should describe a specialist once. Claude Code ignores frontmatter keys it does not recognise,
which is what makes one file serve two readers — and is why the copier that used to strip
these into a mirrored file was solving a problem nobody had."""


def specialists(root: Path | str) -> list[AgentSpec]:
    """The project's own agents, by name. Empty when `.claude/agents/` is absent — which is
    the regression guard for every project that predates this: no registry, no behaviour."""
    return _load(Path(root) / REGISTRY_DIR)


def registry(root: Path | str) -> list[AgentSpec]:
    """Defaults plus specialists, the repo overriding the plugin by `name`."""
    merged = {spec["name"]: spec for spec in _load(_plugin_dir())}
    merged.update({spec["name"]: spec for spec in specialists(root)})
    return [merged[name] for name in sorted(merged)]


def agent_for(root: Path | str, labels: list[str]) -> str:
    """The specialist a card belongs to, or "" for none.

    Most shared labels wins; a tie goes to the alphabetically first name. Deterministic on
    purpose — a router that picked differently on two runs would make a fleet unreproducible,
    and "which agent got this card" is the first question anybody asks when one goes wrong.
    """
    wanted = set(labels)
    scored = [(-len(wanted & set(a["labels"])), a["name"]) for a in registry(root) if a["labels"]]
    ranked = sorted(score for score in scored if score[0] < 0)
    return ranked[0][1] if ranked else ""


def agent_named(root: Path | str, actor: str) -> AgentSpec | None:
    """The registry entry an actor id names, or None.

    `agent:<dev>/<name>` — the tail is the registry key. An actor that matches nothing stays
    UNRESTRICTED: a human's ad-hoc worker must not become fenced in just because specialists
    exist, or adding one agent would quietly change the rules for everybody else.
    """
    tail = actor.rsplit("/", 1)[-1]
    return next((a for a in registry(root) if a["name"] == tail), None)


def fenced(agent: AgentSpec | None, labels: list[str]) -> str:
    """Why this agent may not have this card, or "" if it may.

    Names BOTH label sets, because the useful refusal is not "no" but "you do X, this is Y".
    """
    if agent is None:
        return ""
    if not agent["claims"]:
        # The orchestrator rule, enforced instead of asked for. Told in three separate places
        # not to implement the work itself, a session did exactly that — twice — because an
        # instruction is what a model weighs against everything else in its context, and a
        # refusal is not.
        return (f"{agent['name']} does not hold cards — it plans and hands work out. Dispatch "
                f"this one to a specialist and spawn that sub-agent instead")
    if not agent["labels"]:
        return ""
    if set(labels) & set(agent["labels"]):
        return ""
    theirs = ", ".join(labels) or "no labels"
    return (f"{agent['name']} works on [{', '.join(agent['labels'])}]; this card carries "
            f"[{theirs}] — it belongs to another specialist")


def _plugin_dir() -> Path:
    """Shipped next to the source in a checkout; absent from an installed wheel, which is fine
    — the defaults are then whatever the installed plugin already gave Claude Code."""
    return Path(__file__).resolve().parents[3] / "plugin" / "agents"


def _load(folder: Path) -> list[AgentSpec]:
    out: list[AgentSpec] = []
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.md")):
        try:
            out.append(parse_agent(path.read_text(encoding="utf-8"), path))
        except (BadRequest, TaskopsError, OSError, UnicodeDecodeError) as err:
            warnings.warn(f"taskops: skipping agent file — {err}", stacklevel=2)
    return out
