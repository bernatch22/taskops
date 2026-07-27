"""Messages addressed to one actor — the agent-to-agent channel, as text.

Its own module because of WHERE it appears: at the top of a claim, and inside a session
brief. Both are places an agent reads before doing anything, which is the whole point — a
message read after the work is a message that cost the work.
"""

from __future__ import annotations

from ..contracts import Inbox
from ._text import ago

__all__ = ["render_inbox"]


def render_inbox(inbox: Inbox) -> str:
    """The messages, or "" when there are none.

    Empty string rather than "no messages": this gets embedded in other renders, and a
    line saying nothing happened is a line every caller then has to decide to strip.
    """
    if not inbox["messages"]:
        return ""
    lines = [f"**{e['actor']}** on {e['task']} ({ago(e['ts'])}): "
             f"{e['body'].get('text', '')}" for e in inbox["messages"]]
    return "\n".join([f"### 📬 {len(inbox['messages'])} message(s) for you", "",
                      "\n\n".join(lines)])
