"""Reading and rewriting a `git commit` shell command.

This exists because of what a Claude Code `PreToolUse` hook can do: return `updatedInput`
and have the tool call run with a MODIFIED command. So the `Task:` trailer can be injected
into the agent's own `git commit -m …` before it executes — the agent never writes it, never
forgets it, and never sees a failure about it.

Parsing shell is a bad idea in general, so the scope here is deliberately narrow: recognise
`git commit` with a `-m` message, and rebuild the same command with a different message.
Anything else — a compound command, `-F`, an editor commit with no `-m` — is reported as
"cannot rewrite", and the caller falls back to allowing or denying without a rewrite. Guessing
at a command somebody is about to run is how a coordination tool breaks a commit.
"""

from __future__ import annotations

import shlex

__all__ = ["is_commit", "message_of", "with_message"]

_MESSAGE_FLAGS = ("-m", "--message")


def is_commit(command: str) -> bool:
    """Is this a `git commit`."""
    return _subcommand(_words(command)) == "commit"


def message_of(command: str) -> str:
    """The `-m` message, or "" when there is not exactly one to read.

    "" covers several different situations on purpose — no `-m` at all (an editor commit),
    `-F` (a file), or several `-m` flags (git joins them into paragraphs). The caller cannot
    do anything useful with any of them beyond declining to rewrite, so they collapse.
    """
    words = _words(command)
    found = [words[i + 1] for i, word in enumerate(words[:-1])
             if word in _MESSAGE_FLAGS]
    return found[0] if len(found) == 1 else ""


def with_message(command: str, message: str) -> str:
    """The same command with its `-m` value replaced. "" if it cannot be done safely.

    A compound command is refused outright. `git commit -m x && git push` would need this to
    understand shell operators to rewrite correctly, and a rewrite that dropped the second
    half would be far worse than no rewrite at all — the agent's push would silently not
    happen.
    """
    if _is_compound(command) or not message_of(command):
        return ""
    words = _words(command)
    out: list[str] = []
    skip = False
    for word in words:
        if skip:
            out.append(message)
            skip = False
            continue
        out.append(word)
        skip = word in _MESSAGE_FLAGS
    return shlex.join(out)


def _words(command: str) -> list[str]:
    """Shell-split, or [] if the command cannot be lexed.

    Never raises: the input is whatever an agent typed, and an unbalanced quote must read as
    "not something I can analyse" rather than take the hook down and block the commit.
    """
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _is_compound(command: str) -> bool:
    """Does the command chain, pipe, redirect or substitute.

    Checked on the RAW string rather than the lexed words, because shlex strips exactly the
    operators this is looking for — after splitting, `a && b` and `a b` are hard to tell
    apart, and mistaking one for the other is what would drop half a command.
    """
    return any(token in command for token in ("&&", "||", ";", "|", "$(", "`", ">", "<"))


_VALUED_FLAGS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")


def _subcommand(words: list[str]) -> str:
    """The git subcommand: the first bare word after `git`, or "".

    Parsed properly rather than by looking for "commit" near the front, which is what this did
    first — and `git log --grep commit` was then read as a commit, so the guard would have
    inspected a read-only command. Git's own pre-subcommand flags are skipped, including the
    ones that take a value (`git -C /tmp commit`), because otherwise their argument would be
    mistaken for the subcommand.
    """
    if not words or words[0] != "git":
        return ""
    index = 1
    while index < len(words):
        word = words[index]
        if word in _VALUED_FLAGS:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            return word
    return ""
