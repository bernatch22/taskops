"""`taskops brief | inbox | track | checkout` — the Claude Code session hooks.

Grouped in one module because they are one lifecycle, and because every one of them shares
the same rule: print something an agent can act on, or print NOTHING. These run on
SessionStart and after every tool call, so a line of noise here is a line of noise in every
session, forever.
"""

from __future__ import annotations

import argparse

from ....render import render_brief, render_inbox
from ....usecases import brief, checkout, inbox, track
from ._shared import add_identity, add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    for name, help_text, runner in (
        ("brief", "what this session holds and who messaged it (SessionStart)", _brief),
        ("inbox", "messages not yet delivered to this actor (PostToolUse)", _inbox),
        ("track", "record what a tool just did, for the live board (PostToolUse)", _track),
        ("checkout", "post the session's summary to its tasks (Stop)", _checkout),
    ):
        parser = sub.add_parser(name, help=help_text)
        add_target(parser)
        add_identity(parser)
        if name in ("track", "checkout"):
            parser.add_argument("--summary", default="", help="one line: what happened")
        if name == "track":
            parser.add_argument("--task", default="", help="which task (default: the only one held)")
        parser.set_defaults(run=runner)


def _brief(args: argparse.Namespace) -> str:
    return render_brief(brief(repo_of(args), session=args.session, actor=args.actor))


def _inbox(args: argparse.Namespace) -> str:
    return render_inbox(inbox(repo_of(args), actor=args.actor))


def _track(args: argparse.Namespace) -> str:
    """Silent by design. It runs after EVERY tool call, so its output would otherwise be
    injected into the session hundreds of times to say nothing new."""
    track(repo_of(args), summary=str(args.summary), task=str(args.task), actor=args.actor)
    return ""


def _checkout(args: argparse.Namespace) -> str:
    posted = checkout(repo_of(args), summary=str(args.summary), session=args.session,
                      actor=args.actor)
    return f"taskops: recorded on {len(posted)} task(s)" if posted else ""
