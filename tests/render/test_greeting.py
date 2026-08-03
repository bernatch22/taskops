"""The one line a PERSON sees when a session opens.

Every other thing the `SessionStart` hook produces goes to the model: `additionalContext` is
wrapped in a system reminder and never shown, and plain stdout is hidden too. So a session used
to open, the agent received the whole board, and the human watching had no way to tell taskops
had run at all.

Three shapes were shown to a real reader before this one, and each was rejected for a reason
that is now a test below: a four-section block arrived as one run-on paragraph, a run of
`label: value` segments read as a config dump, and a terse sentence still said "5 card(s) need
dispatch" — jargon. So what is pinned here is not a layout. It is that the line SAYS WHAT IT
MEANS, in words somebody who has never used taskops understands, and that it does not grow with
the board.
"""

from __future__ import annotations

import re
from typing import Any

from taskops.render import render_greeting
from taskops.render.greeting import FACES, SAYS

BARE = re.compile(r"\x1b\[[0-9;]*m")


def plain(said: str) -> str:
    """The line as a reader sees it — colour stripped, so an assertion about WORDS is not
    quietly also an assertion about where an escape sits."""
    return BARE.sub("", said)


def view(**over: Any) -> dict[str, Any]:
    return {"actor": "dev:ana", "held": [], "waiting": [], "messages": [], "board": "",
            "shared": False, "recent": [], "team": {"me": "ana", "others": []},
            "context": {"active": [], "milestone": None, "yours": None}, **over}


def chapter(title: str, horizon: str = "") -> dict[str, str]:
    """A MILESTONE literal, whose field is `title` and not `text`.

    It said `text` and the greeting read `fact["text"]`, so a test passed while the real call —
    handed an actual `Milestone` — raised `KeyError` on every session start. A literal standing in
    for a type has to carry that type's fields; this repository has the scar already.
    """
    return {"title": title, "horizon": horizon}


def goal(text: str, horizon: str = "") -> dict[str, str]:
    """A FACT literal — `yours`, the reader's own objective. Its field is `text`."""
    return {"text": text, "horizon": horizon}


def waiting(*moves: str) -> list[dict[str, str]]:
    return [{"move": move, "task": f"tk-{n}"} for n, move in enumerate(moves)]


def moved(actor: str, kind: str = "status", **body: Any) -> dict[str, Any]:
    return {"actor": actor, "kind": kind, "task": "tk-4f2a9c", "body": body or {"to": "review"}}


# ---- it says where you are, and what that means


def test_it_names_the_thing_that_is_running() -> None:
    """The complaint that produced this rewrite, in one assertion: a reader opening a session
    has to learn FROM THE LINE that a board is tracking the repository they are in. A status
    line whose first word is a count is a line for somebody who already knew."""
    said = plain(render_greeting(view(waiting=waiting("dispatch"))))
    assert said.startswith("taskops is tracking this project")


def test_no_move_reaches_the_screen_in_board_vocabulary() -> None:
    """`dispatch`, `specless`, `stalled` and `land` are schedule states. A person reading
    "5 card(s) need dispatch" learns a count and nothing else — which is what they said."""
    every = plain(render_greeting(view(waiting=waiting(*SAYS))))
    for move, means in SAYS.items():
        assert move not in every, f"{move!r} is vocabulary, not English"
        assert means in every


def test_a_move_from_a_newer_taskops_still_reads_as_English() -> None:
    """An ALLOW-list, not a translation attempt: a teammate on a newer version invents moves,
    and the failure mode of passing them through is the jargon this line exists to remove."""
    said = plain(render_greeting(view(waiting=waiting("teleported"))))
    assert "teleported" not in said and "1 waiting on somebody" in said


def test_it_is_ONE_line() -> None:
    """A four-section block was written first and arrived as a run-on paragraph on a real
    screen. Whatever `systemMessage` does with a newline, this never gives it one."""
    said = render_greeting(view(context={"active": [chapter("ship it", "2026-08-20")],
                                         "yours": goal("the parser")},
                                recent=[moved("dev:juan", "claimed")],
                                waiting=waiting("verify"), held=[{"task": "t"}],
                                board="https://boards.example.com/probe/"))
    assert "\n" not in said


def test_it_is_a_sentence_and_ends_like_one() -> None:
    """`a, b and c`, not `a, b, c` — the shape that made the previous version read as a dump."""
    said = plain(render_greeting(view(waiting=waiting("dispatch", "verify", "land"))))
    assert " and " in said and ", " in said and not said.rstrip().endswith(",")


def test_the_objective_leads_and_so_does_your_own() -> None:
    """Left out at first, on the argument that the model has it and whoever wrote it remembers.
    One real session killed that: you open a project you have not touched in a week and you do
    not remember — the same reason the board keeps a context strip on screen at all times."""
    said = plain(render_greeting(view(context={"active": [chapter("ship the importer", "2026-08-20")],
                                               "yours": goal("the parser")})))
    assert "the team is working towards ship the importer (by 08-20)" in said
    assert "you are on the parser" in said


def test_the_id_is_whole_enough_to_paste() -> None:
    """Same reason as the bar's: a nine-character id cut to eight resolves to nothing, and the
    only reason to print one on a first screen is that somebody can act on it."""
    said = plain(render_greeting(view(recent=[moved("dev:juan", "claimed")])))
    assert "tk-4f2a9c" in said


def test_your_own_moves_say_you() -> None:
    """The only place taskops abbreviates an actor: a first screen is where somebody is reading
    about themselves."""
    said = plain(render_greeting(view(recent=[moved("agent:ana/w1", "commit")])))
    assert "you committed" in said and "ana" not in said


def test_the_last_move_of_each_person_not_a_feed() -> None:
    """The question is "what changed while I was away", and nine commits by one worker answer
    it worse than two names do."""
    said = plain(render_greeting(view(recent=[moved("agent:juan/w1", "claimed"),
                                              moved("agent:ana/w1", "commit"),
                                              moved("agent:ana/w2", "commit"),
                                              moved("agent:ana/w3", "commit")])))
    assert said.count("you ") == 1, "one clause per PERSON, not per agent and not per event"
    assert "juan" in said


# ---- colour, which is decoration and must never be structure


def test_colour_is_present_and_removable() -> None:
    """Two escapes and no library. Stripping every one of them must leave the same sentence —
    if a reader's terminal shows them raw, what is left is still the message and not a stub."""
    said = render_greeting(view(context={"active": [chapter("ship it")], "yours": None},
                                waiting=waiting("dispatch")))
    assert "\x1b[" in said
    assert plain(said) == ("taskops is tracking this project on this machine only — the team "
                           "is working towards ship it. Right now: 1 ready to hand to an agent.")


# ---- the ceilings, which are the design


def test_no_more_than_two_faces_however_many_people_moved() -> None:
    said = plain(render_greeting(view(recent=[moved(f"dev:p{n}") for n in range(20)])))
    assert said.count("moved tk-") == FACES


def test_the_line_does_not_grow_with_the_board() -> None:
    """THE property. Forty cards and nine people cost what three do, because what is waiting is
    grouped by MEANING and people are capped."""
    small = plain(render_greeting(view(waiting=waiting("verify"), recent=[moved("dev:x")])))
    big = plain(render_greeting(view(waiting=waiting(*["verify"] * 40),
                                     recent=[moved(f"dev:p{n}") for n in range(9)])))
    # Bounded by ONE more clause and two more digits, not by nine people and forty cards.
    assert len(big) - len(small) < 40


def test_every_stated_fact_is_capped() -> None:
    """A sentence that grew with the length of somebody's objective would push the part that
    changes daily — what is waiting — off the right of the screen."""
    said = plain(render_greeting(view(context={"active": [chapter("x " * 90)],
                                               "yours": goal("y " * 90)},
                                      waiting=waiting("verify"))))
    assert said.count("…") == 2 and "1 waiting for somebody to review" in said
    # GOAL + MINE + the fixed prose around them. Prose costs about fifty characters more than
    # `label: value` did, and buys a line a reader does not have to be taught to read.
    assert len(said) < 240


# ---- and what it refuses to say


def test_a_project_with_no_board_says_nothing_at_all() -> None:
    """A repository nobody ran `taskops init` in must not have a line printed into every one
    of its sessions forever."""
    assert render_greeting({"actor": "", "held": [], "waiting": []}) == ""


def test_a_quiet_board_says_so() -> None:
    """"Nothing to do" and "the hook never ran" look identical on an empty screen, and they are
    not the same news."""
    assert plain(render_greeting(view())) == \
        "taskops is tracking this project on this machine only. Nothing is waiting on you."


def test_a_kind_this_version_never_heard_of_is_not_printed() -> None:
    """An ALLOW-list here too: a teammate on a newer taskops writes event kinds this one does
    not know, and a deny-list fills a first screen with whatever they added."""
    assert plain(render_greeting(view(recent=[moved("dev:ana", "from-the-future")]))) == \
        "taskops is tracking this project on this machine only. Nothing is waiting on you."


def test_it_says_whether_the_board_is_shared() -> None:
    """Everything after this clause means something different depending on the answer: on a
    shared board "5 ready to hand out" is five the whole team can see, and on a local one it is
    five nobody else knows about. Nothing downstream says which, so the opening has to."""
    # Read from `shared` and NOT from "is there a URL". A local project HAS one now — the
    # SessionStart hook starts its board — so the URL stopped being able to say which kind of
    # project this is, and a greeting that kept reading it called every local board a team's.
    alone = plain(render_greeting(view(waiting=waiting("dispatch"),
                                       board="http://127.0.0.1:50216/", shared=False)))
    shared = plain(render_greeting(view(waiting=waiting("dispatch"), shared=True,
                                        board="https://boards.example.com/probe/")))
    assert "on this machine only" in alone and "with your team" in shared


def test_the_board_url_carries_no_token() -> None:
    """This prints into a scrollback and whatever gets screen-shared next. `taskops open` is
    the command for a browser somebody chose to point at it."""
    said = plain(render_greeting(view(board="https://boards.example.com/probe/")))
    assert said.endswith("Board: https://boards.example.com/probe/") and "token" not in said


def test_a_local_board_is_offered_too_once_there_is_one() -> None:
    """This used to assert the opposite, and the opposite was right at the time: a local
    `taskops ui` was not running unless somebody started one, so printing its address would
    have been an address that refuses to connect. The fix was to START it — the hook does,
    before this is rendered — so the reason for the silence is gone and so is the silence."""
    said = plain(render_greeting(view(waiting=waiting("verify"),
                                      board="http://127.0.0.1:50216/")))
    assert said.endswith("Board: http://127.0.0.1:50216/")


def test_a_project_with_nowhere_to_look_still_offers_nothing() -> None:
    """The half of the old rule that survives: no board came up, so there is no address, and
    inventing one would be the connection-refused this was always about."""
    assert "http" not in render_greeting(view(waiting=waiting("verify")))
