"""`taskops status`, drawn — a panel when `rich` is installed, plain text when it is not.

Two painters, ONE set of facts: `_rows` turns the contract into `(label, value, style)`
and neither painter is allowed to decide what goes on the screen. That is what keeps the
two outputs from drifting into different commands, which is what happens the moment a
"pretty" version starts showing something the fallback does not.

`rich` is an OPTIONAL EXTRA (`pip install taskops-cli[pretty]`) and the import is guarded
here, at the only place that wants it. taskops is installed into every agent's environment
on every machine, so a hard dependency here is a dependency everywhere — and a status
command that cannot run because a rendering library is missing would be a bad trade.

Colour is a PARAMETER, not something this module works out. `render/` never asks whether
it is talking to a terminal or reads `NO_COLOR`: the transport that owns stdout knows, and
a renderer that guessed could not be tested from a literal dict.
"""

from __future__ import annotations

from ..contracts.status import Reports, Status, Sync
from ._text import ago, span, truncate

__all__ = ["render_status"]

_ANSI = {"bold": "1", "dim": "2", "italic": "3", "red": "31", "green": "32",
         "yellow": "33", "magenta": "35", "cyan": "36"}
"""Style name -> SGR code. The names are rich's, so the fallback speaks the pretty
painter's vocabulary rather than inventing a second one nobody can cross-check."""

Row = tuple[str, str, str]


def render_status(status: Status, *, colour: bool = True) -> str:
    """The whole project in one block. `colour=False` is byte-plain — no escapes at all."""
    rows = _rows(status)
    try:
        return _panel(status, rows, colour)
    except ImportError:
        return _flat(status, rows, colour)


def _panel(status: Status, rows: list[Row], colour: bool) -> str:
    """The rich path: a bordered panel around a right-aligned label column.

    Rendered through a capture at a FIXED width rather than printed, because this
    function returns a string like every other renderer — and because a width taken
    from the real terminal would make the golden output depend on the window.
    """
    from rich import console, panel, table, text

    grid = table.Table.grid(padding=(0, 2))
    grid.add_column(justify="right", style="dim", no_wrap=True)
    for label, value, style in rows:
        grid.add_row(label, text.Text(value, style=style))
    framed = panel.Panel(grid, title=text.Text(status["project"], style="bold"),
                         subtitle=text.Text(status["actor"], style="dim"),
                         border_style="cyan", padding=(0, 1), width=88)
    screen = console.Console(width=90, force_terminal=colour, no_color=not colour)
    with screen.capture() as captured:
        screen.print(framed)
    return captured.get().rstrip("\n")


def _flat(status: Status, rows: list[Row], colour: bool) -> str:
    """The stdlib path: the same rows, aligned, with SGR codes only when asked."""
    width = max(len(label) for label, _, _ in rows)
    body = [f"  {label.rjust(width)}  {_ink(value, style, colour)}"
            for label, value, style in rows]
    return "\n".join([_ink(f"{status['project']} — status", "bold", colour), "", *body])


def _ink(text: str, style: str, colour: bool) -> str:
    code = _ANSI.get(style, "")
    return f"\033[{code}m{text}\033[0m" if colour and code else text


def _rows(status: Status) -> list[Row]:
    """Every line of the report, in the order somebody reads them: who am I, what is
    the shape of the work, what is MINE, who else is in here, what is stuck."""
    rows: list[Row] = [("project", f"{status['project']}  ·  {status['actor']}", "bold")]
    if status["objective"]:
        # Absent until the objective feature lands, and absent is NOTHING — never a
        # placeholder row that teaches the reader to skip that line forever.
        rows.append(("objective", status["objective"], "italic"))
    flight = sum(status["counts"].get(name, 0) for name in ("claimed", "review"))
    rows.append(("board", f"{status['total']} card(s)  ·  {status['ready']} ready  ·  {flight}"
                          f" in flight  ·  {status['blocked']} blocked  ·  "
                          f"{status['counts'].get('done', 0)} done", ""))
    rows += _mine(status)
    rows += [("fleet", f"{w['actor']}  {w['task']}  {truncate(w['title'], 32)}"
                       f"  ({span(w['left'])} left)",
              "yellow" if w["expiring"] else "magenta") for w in status["others"]]
    if stuck := status["bottleneck"]:
        rows.append(("blocking", f"{stuck['task']}  {truncate(stuck['title'], 38)}  "
                                 f"→ {stuck['blocks']} waiting", "yellow"))
    if status["idle"]:
        rows.append(("idle", f"{status['idle']} open, untouched {status['idle_days']}d+", "dim"))
    return rows + [_reports(status["reports"]), _sync(status["sync"])]


def _mine(status: Status) -> list[Row]:
    """This actor's claims, green while healthy and red when the lease is nearly out.

    The one row that is printed even when it is empty: "nothing claimed" beside the
    command that fixes it is the whole reason somebody typed `status` before working.
    """
    if not status["mine"]:
        return [("yours", "nothing claimed — `taskops next` picks one", "dim")]
    return [("yours", f"{card['task']}  {truncate(card['title'], 38)}"
                      f"  ({card['state']}, {span(card['left'])} left)",
             "red" if card["expiring"] else "green") for card in status["mine"]]


def _reports(reports: Reports) -> Row:
    """Green only when yesterday is both written AND narrated — a generated file with
    no prose is a different gap from no file, and one colour for both hides it."""
    done, written = reports["yesterday_narrated"], reports["yesterday_written"]
    note = "narrated" if done else "written, no narration" if written else "not written"
    return ("reports", f"{reports['today_events']} event(s) today  ·  "
                       f"{reports['yesterday']} {note}", "green" if done else "yellow")


def _sync(sync: Sync) -> Row:
    """Yellow the moment this machine holds work nobody else can see."""
    if not sync["host"]:
        return ("sync", "local only — no remote configured", "dim")
    when = ago(sync["last_sync"]) if sync["last_sync"] else "never"
    state = f"{sync['ahead']} event(s) to push" if sync["ahead"] else "in sync"
    return ("sync", f"{sync['host']}  ·  {state}  ·  last {when}",
            "yellow" if sync["ahead"] else "green")
