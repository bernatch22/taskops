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
from ._ghlink import links, read_link, remove_link, write_link
from ._project import locate
from ._range import Selector, parse_date
from ._sessions import mint, opens, resolve
from .accounts import authenticate
from .ask import ask, search
from .claim import next_task
from .dispatch import DispatchResult, dispatch
from .dossier import digest, read_report, report_path, write_report
from .edit import edit
from .exchange import MAX_BATCH, MAX_PAGE, accept_events, pull_events
from .feed import follow, is_wire
from .guard import Verdict, check_command, check_commit
from .index import report_index
from .ingest import ingest_branch, ingest_commit
from .log import session_log
from .login import is_session, login, logins, logout, session_of
from .plan import plan
from .pushpull import Exchange, pull, push
from .recover import Recovered, recover
from .remote import add_remote, read_remote, remove_remote, require_remote
from .report import activity, board, day, fleet, period, standup
from .reportfile import read_report_file, write_report_file
from .session import Brief, brief, checkout, inbox, track
from .setup import InitReport, init
from .sync import rebuild, sync
from .update import update

__all__ = [
    # the five MCP tools
    "plan", "next_task", "update", "edit", "ask", "search", "board", "standup", "fleet", "activity",
    "day", "period", "Selector",
    "dispatch", "DispatchResult", "write_report", "read_report", "digest", "report_path",
    "report_index", "recover", "Recovered",
    # the remote exchange: events and report files over HTTP
    "accept_events", "pull_events", "MAX_BATCH", "MAX_PAGE",
    "read_report_file", "write_report_file",
    # the CLI verbs the hooks call
    "init", "InitReport", "check_commit", "check_command", "Verdict",
    "ingest_commit", "ingest_branch",
    "brief", "Brief", "inbox", "checkout", "track", "sync", "rebuild", "follow", "locate", "session_log",
    # the remote: one server, and the two verbs that converge with it
    "add_remote", "read_remote", "require_remote", "remove_remote", "push", "pull", "Exchange",
    # signing in: one GitHub login per machine, a session per server
    "login", "logout", "logins", "session_of", "is_session",
    # the live narration: started in the background, watched on the wire
    "narration", "is_wire", "parse_date",
    # who you are: a GitHub login, the sessions it mints, the repository a board is linked to
    "authenticate", "mint", "resolve", "opens",
    "links", "read_link", "write_link", "remove_link",
]
