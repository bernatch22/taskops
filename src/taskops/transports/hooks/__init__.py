"""The wiring transport: the door git and Claude Code come through.

Three audiences, three doors. `cli/` is the developer's, `mcp/` is the agent's, and this one
belongs to the two callers that are neither — git, which runs shell scripts, and Claude Code,
which runs `{"type": "command"}` entries. Both EXECUTE something, so something executable has
to exist; what this module changes is that it stopped being the developer's `taskops`.

Nobody types `python -m taskops.transports.hooks`. It is written into `.git/hooks/*` by
`usecases.hooks` and into `plugin/hooks/hooks.json`, and read by nothing else.

It is a transport like the other two and obeys the same fence: thin, no `storage`, no
`engine` — `test_transports_never_reach_past_the_use_cases` is what enforces it.
"""

from __future__ import annotations
