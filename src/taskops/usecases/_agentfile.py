"""The frontmatter of an agent file, parsed with the standard library and nothing else.

taskops has ZERO runtime dependencies, and one `import yaml` here would end that for the whole
package — for a header that is, in every agent file anybody actually writes, four flat keys.

So this parses the SUBSET and refuses the rest out loud:

```
name: taskops-collectors      a scalar
labels: [collectors, etl]     a flat inline list
```

Anything else — a nested block, a `-` list, a `|` fold, an anchor — raises with the file named.
A partial YAML parser that GUESSES at what it does not understand is the worst of the three
options available: it turns a typo into a silently wrong registry, and the agent then routes
cards nobody meant it to have. Refusing is recoverable; the loader turns the refusal into a
warning and skips that one file.
"""

from __future__ import annotations

import re
from pathlib import Path

from .._errors import BadRequest
from ..contracts.agents import AgentSpec

__all__ = ["parse_agent", "without_keys", "FENCE"]

FENCE = "---"

_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")


def parse_agent(text: str, path: Path) -> AgentSpec:
    """One agent file → its spec. Raises `BadRequest` naming the file for anything unparsed."""
    fields = _frontmatter(text, path)
    if not fields.get("name"):
        raise BadRequest(f"{path}: an agent file needs a `name:` key — it is the registry key")
    return AgentSpec(name=str(fields["name"]), description=str(fields.get("description", "")),
                     labels=_as_list(fields.get("labels", [])),
                     files=_as_list(fields.get("files", [])),
                     # Absent means yes: a registry written before this key existed, and every
                     # ordinary specialist, must keep working unchanged.
                     claims=str(fields.get("claims", "true")).strip().lower()
                     not in ("false", "no", "0"),
                     path=str(path), text=text)


def without_keys(text: str, drop: tuple[str, ...]) -> str:
    """The same file with some frontmatter keys removed, everything else byte-identical.

    Surgery rather than re-serialisation: see `contracts.agents.AgentSpec.text`.
    """
    lines = text.splitlines()
    end = _end_of_frontmatter(lines)
    head = [ln for ln in lines[1:end]
            if not any(ln.startswith(f"{key}:") for key in drop)]
    return "\n".join([FENCE, *head, *lines[end:]]) + "\n"


def _frontmatter(text: str, path: Path) -> dict[str, object]:
    lines = text.splitlines()
    end = _end_of_frontmatter(lines, path)
    out: dict[str, object] = {}
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        out.update(_pair(raw, path))
    return out


def _end_of_frontmatter(lines: list[str], path: Path | None = None) -> int:
    if lines and lines[0].strip() == FENCE:
        for i in range(1, len(lines)):
            if lines[i].strip() == FENCE:
                return i
    if path is None:
        return 0
    raise BadRequest(f"{path}: no `---` frontmatter block — an agent file opens with one")


def _pair(raw: str, path: Path) -> dict[str, object]:
    match = _LINE.match(raw)
    if match is None or not match.group(2).strip():
        raise BadRequest(f"{path}: cannot read the line `{raw.strip()}` — taskops parses only "
                         f"`key: value` and `key: [a, b]`, no nested blocks and no `-` lists")
    key, value = match.group(1), match.group(2).strip()
    if value[0] in "|>&*{":
        raise BadRequest(f"{path}: the value of `{key}` uses YAML taskops does not parse — "
                         f"write it as `{key}: value` or `{key}: [a, b]`")
    if value.startswith("["):
        if not value.endswith("]"):
            raise BadRequest(f"{path}: the list `{key}` must open and close on one line")
        return {key: [item.strip().strip("\"'") for item in value[1:-1].split(",")
                      if item.strip()]}
    return {key: value.strip("\"'")}


def _as_list(value: object) -> list[str]:
    """A single scalar counts as a list of one — `labels: etl` is what people write."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []
