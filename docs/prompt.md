# The prompt segment

`taskops status --prompt` prints one line and nothing else:

```
tk:taskops 3▸1 ⇡5 !r
```

- `tk:<project>` — the project directory's name.
- `3▸1` — **3** open cards, **1** of them claimed by you. The `▸1` half is dropped when
  none are yours, so three open cards nobody has taken reads `3`.
- `⇡5` — **5** events this machine has recorded and not pushed to the remote.
- `!r` — yesterday has a report with **no narration** (or no report at all).

Every segment disappears when it is zero, and a project with nothing to say prints the
**empty string**. That is the point: a segment you always see is a segment you stop reading.

## The two guarantees

**It never speaks out of turn.** Outside a taskops project, or with a database that is
missing, locked, half-written or from a newer schema, it prints *nothing* and exits **0**.
No stderr either. This runs in front of every line you type — a single error message here
would corrupt the whole terminal, so there is no failure it considers worth reporting.

**It never does I/O it can lose.** No network, no model, no `git` subprocess: one local
SQLite read. `--fetch` is ignored in this mode. Budget is under 50ms; measured in-process
on this repository it is ~17ms.

> **The interpreter start dominates.** The command itself is milliseconds, but starting
> CPython and importing the package is tens of milliseconds more — several times the work.
> That is why the zsh snippet below is **asynchronous**: nothing you type ever waits for it.

Colour is **off by default**. Pass `--colour zsh` to get zsh's own `%F{…}%f` escapes.
Do not put raw ANSI inside `PROMPT`: zsh miscounts the line width and line editing breaks.

## zsh — copy and paste

Appends the segment to the right-hand prompt, refreshed in the background after every
command. Add to `~/.zshrc`:

```zsh
# --- taskops prompt segment -------------------------------------------------
typeset -g TASKOPS_SEGMENT=''
typeset -g _taskops_fd=0

_taskops_collect() {                     # the async half: read what the child wrote
  local fd=$1
  TASKOPS_SEGMENT="$(<&$fd)"
  zle -F $fd                             # stop watching, then close
  exec {fd}<&-
  _taskops_fd=0
  zle && zle reset-prompt                # repaint only if there is a prompt to repaint
}

_taskops_precmd() {
  (( _taskops_fd )) && return            # one in flight is enough
  exec {_taskops_fd}< <(taskops status --prompt --colour zsh 2>/dev/null)
  zle -F $_taskops_fd _taskops_collect
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _taskops_precmd
setopt prompt_subst
RPROMPT='${TASKOPS_SEGMENT}'
# ----------------------------------------------------------------------------
```

`zle -F <fd> <handler>` is zsh's own I/O watcher: the shell keeps taking input and calls
the handler once the child has written. `2>/dev/null` is belt and braces — the command is
already silent on failure.

If you would rather not use `zle -F`, the one-liner version is a detached job writing to a
file, read on the next prompt (so the segment is one command stale):

```zsh
_taskops_precmd() {
  TASKOPS_SEGMENT="$(cat /tmp/.taskops-seg-$$ 2>/dev/null)"
  { taskops status --prompt --colour zsh >/tmp/.taskops-seg-$$ 2>/dev/null } &!
}
```

## Claude Code statusline

Claude Code renders a custom status line by **running a command** and using its stdout. It
feeds that command a JSON document on **stdin** with the session's context; the field we
want is `workspace.current_dir`.

> A **plugin cannot provide a status line.** `statusLine` is a user/project *setting*, not
> something a plugin declares — installing the taskops plugin will not give you this. You
> add the two pieces below by hand.

`~/.claude/statusline.sh` (or anywhere; `chmod +x` it):

```sh
#!/bin/sh
# Claude Code hands us the session JSON on stdin. Take the working directory from it,
# print whatever you want your status line to be, then append the taskops segment.
input=$(cat)
dir=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin)["workspace"]["current_dir"])' 2>/dev/null)
[ -n "$dir" ] || dir=$PWD

printf '%s' "$(basename "$dir")"
seg=$(taskops status --prompt --repo "$dir" 2>/dev/null)
[ -n "$seg" ] && printf '  %s' "$seg"
```

Then in `~/.claude/settings.json` (or the project's `.claude/settings.json`):

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.sh"
  }
}
```

No `--colour zsh` here: the status line takes plain text (and ANSI), not zsh escapes.

## `--porcelain` — the stable contract

`taskops status --porcelain` prints `key=value`, one key per line, for scripts:

```
version=1
project=taskops
root=/Users/berna/taskops
actor=dev:berna
total=29
open=7
ready=7
blocked=0
mine=0
others=0
idle=0
idle_days=7
bottleneck=
blocks=0
remote=
ahead=0
today_events=9
yesterday=2026-07-28
yesterday_written=1
yesterday_narrated=1
prompt=tk:taskops 7
```

Parsing rule: **split on the first `=`**. No value ever contains a newline or an `=` —
counts, flags and identifiers only, never a card title — so that rule holds forever.

Booleans are `1`/`0`. Absent things are the empty string (`bottleneck=`, `remote=`).
`prompt` is exactly what `--prompt` would print, uncoloured, empty when there is nothing
to say.

### Versioning

`version=1` is the first line and it is the contract.

- Within a version, keys may be **added**. Never renamed, never removed, and the meaning
  of an existing key never changes. So `grep '^ahead='` is safe to depend on.
- Anything that would break that is `version=2`, and a script that cares should check the
  first line before trusting the rest.

Like `--prompt`, `--porcelain` prints **nothing** and exits **0** outside a project or on
a broken database.
