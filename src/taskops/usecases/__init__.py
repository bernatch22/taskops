"""Layer 5 — one module per verb, sync, returning contracts.

Every transport calls THESE, so a behaviour is implemented once and three surfaces
cannot drift apart. `tests/architecture` enforces the other half of that: a transport
may not import `storage` or `engine` directly, which is what stops a fourth place where
a decision lives.

Sync all the way down. taskops is sqlite and a state machine; the http edge may be
async and calls in from a threadpool, but there is no async twin of the engine.
"""

from __future__ import annotations

from . import narration
from ._contextviews import context_for
from ._contextviews import history as context_log
from ._contextviews import show as context_show
from ._ghlink import links, read_link, remove_link, write_link
from ._project import locate
from ._range import Selector, parse_date
from ._sessions import mint, opens, resolve
from .acceptance import acceptance_for, set_acceptance
from .accounts import authenticate
from .agents import agent_for, agent_named, fenced, registry, specialists
from .ask import ask, search
from .attention import attention
from .browse import board_url, root_url
from .capture import capture
from .claim import next_task
from .context import retire as context_retire
from .context import state as context_state
from .dispatch import DispatchResult, dispatch
from .dossier import digest, read_report, report_path, write_report
from .edit import edit
from .exchange import MAX_BATCH, MAX_PAGE, accept_events, pull_events
from .feed import follow, is_wire
from .guard import Verdict, check_command, check_commit
from .index import report_index
from .ingest import ingest_commit
from .ingestbranch import ingest_branch
from .join import join
from .log import session_log
from .login import is_session, login, logins, logout, session_of
from .notelanding import note_landing
from .plan import plan
from .policy import set_policy
from .policy import show as policy_show
from .pushpull import Exchange, pull, push
from .recover import Recovered, recover
from .remote import add_remote, read_remote, remove_remote, require_remote
from .report import activity, board, day, fleet, period, standup
from .reportfile import read_report_file, write_report_file
from .session import Brief, brief, checkout, inbox, track
from .setup import InitReport, init
from .status import EXPIRING, IDLE_DAYS, status
from .sweep import LIMIT, sweep
from .sync import rebuild, sync
from .teamnow import team_now
from .update import update

__all__ = [
    # the five MCP tools
    "plan", "capture", "next_task", "acceptance_for", "set_acceptance", "update", "edit", "ask", "search", "board", "attention", "team_now", "note_landing", "join", "standup", "fleet", "activity",
    "day", "period", "Selector",
    "dispatch", "DispatchResult", "write_report", "read_report", "digest", "report_path",
    "report_index", "recover", "Recovered",
    # the remote exchange: events and report files over HTTP
    "accept_events", "pull_events", "MAX_BATCH", "MAX_PAGE",
    "read_report_file", "write_report_file",
    # the unattended barrier: every finished day that nobody wrote up
    "sweep", "LIMIT",
    # the git-status of a project: what is open, who holds it, what is unwritten
    "status", "IDLE_DAYS", "EXPIRING",
    # the CLI verbs the hooks call
    "init", "InitReport", "check_commit", "check_command", "Verdict",
    "ingest_commit", "ingest_branch",
    "brief", "Brief", "inbox", "checkout", "track", "sync", "rebuild", "follow", "locate", "session_log",
    # the remote: one server, and the two verbs that converge with it
    "add_remote", "read_remote", "require_remote", "remove_remote", "push", "pull", "Exchange",
    # signing in: one GitHub login per machine, a session per server
    "login", "logout", "logins", "session_of", "is_session", "board_url", "root_url",
    # the standing facts: what we are chasing, what may not break, what was decided
    "context_state", "context_retire", "context_show", "context_log", "context_for",
    # the standing settings: values the engine acts on, validated when they are written
    "set_policy", "policy_show",
    # the live narration: started in the background, watched on the wire
    "narration", "is_wire", "parse_date",
    # who you are: a GitHub login, the sessions it mints, the repository a board is linked to
    "authenticate", "mint", "resolve", "opens",
    "links", "read_link", "write_link", "remove_link",
    # the specialist registry: which agent a card belongs to, and who may not claim it
    "registry", "specialists", "agent_for", "agent_named", "fenced",
]
