"""The access screen: what a BROWSER gets instead of a bare 401.

A `curl` or a `fetch` that is missing the token wants the error — a JSON body with a code in it,
which is what every caller in this repo already parses. A person who pasted a link into the
address bar wants a way IN, and `{"error": "a bearer token is required"}` rendered as raw text on
a white page is not one. So the same refusal is answered twice, by what asked for it.

WHY THIS LIVES OUTSIDE `policy`
    The policy decides. It does not render. It stays the single authority on "is this caller
    allowed", answering in the one shape the whole HTTP surface uses (`error_reply`), and it never
    grows a second output format — the day a second one appears, so does the question of which
    endpoints get which, and that question has no good answer.

    The alternative considered was a flag on `Policy` ("html_unlock=True") consulted inside
    `check`. It was rejected for the same reason: it puts a presentation decision in the module
    whose job is authorisation, and it makes every policy test carry a rendering concern.

    So the router asks, in one row: a refusal comes back from `policy.check`, and `instead` turns
    it into a page WHEN it is a 401 and the caller is a browser navigating. The signal is the
    status code, which is HTTP's own — not a private attribute the two modules have to agree on.

WHAT THE PAGE MAY SAY
    Nothing. It does not name the project, the repository, the actor, or any path — a caller who
    cannot prove a credential has no right to learn that `/axion/` is a real board and `/axiom/`
    is not, and a lock screen that shows the title of what it is locking has already leaked the
    thing worth leaking. (The mount reaches the page in a `<base>` tag, which is not a leak: it is
    the URL the caller themselves requested, echoed back so the stored credential is looked up
    under the same key the app uses.)

HOW A STORED CREDENTIAL GETS BACK IN
    A navigation carries no `Authorization` header — the browser has no way to attach one — so a
    token in `localStorage` is invisible to the server on the way in. The page is therefore also
    the BOOTSTRAP: it looks in storage, and if something is there it re-enters through the one
    channel a navigation does have, `?token=…` (the same query form `EventSource` relies on).

    Which means arriving here with a token already in the URL is proof that token was REFUSED —
    the server would have served the app otherwise. That is how a bad credential is detected
    without a second request, and the page says so and clears the stored value. The
    `sessionStorage` flag is the belt to that braces: whatever happens, this page redirects at
    most once per tab, so no failure mode can turn into a reload loop.
"""

from __future__ import annotations

from pathlib import Path

from ._wire import Reply, Request

__all__ = ["instead", "page", "is_navigation"]

TEMPLATE = Path(__file__).resolve().parent / "unlock.html"
"""The markup, beside the module rather than inside it.

A page's worth of HTML, CSS and JavaScript embedded in a byte string is a document living in a
code file: unreadable in an editor that would otherwise highlight it, and counted against this
module's line budget as if it were logic. It ships in the wheel through `package-data`, exactly
like the UI bundle, so an install serves the same screen a checkout does.
"""


def is_navigation(request: Request) -> bool:
    """A person pointing a browser at this, rather than code fetching from it.

    Three conditions, all necessary. A GET, because a refused POST is an API call whatever sent
    it. Not under `/api/`, because the app's own fetches must keep receiving the JSON error their
    handlers are written against. And `Accept: text/html`, which is the browser's own statement
    that it is rendering a document — `fetch` and `curl` do not send it, and the SPA's `fetch`
    calls in `api.ts` do not either.
    """
    return (request.method == "GET"
            and not request.path.startswith("/api/")
            and "text/html" in request.headers.get("accept", ""))


def instead(refusal: Reply, request: Request, base: str = "/") -> Reply:
    """The refusal, or the page in its place. Everything that is not a missing credential on a
    navigation passes straight through — 403 read-only, 429 rate-limited and every API 401 keep
    the JSON body they have always had."""
    if refusal.status != 401 or not is_navigation(request):
        return refusal
    return page(base)


def page(base: str = "/") -> Reply:
    """200, not 401, and deliberately.

    The request succeeded: this IS the page for that URL without a credential. A 401 would make
    the browser's own console shout, some proxies substitute their own error document, and any
    monitor treat a normal first visit as an outage.
    """
    # Read per request rather than at import: it is one small file off the page cache, and it
    # keeps a broken or missing template from taking the whole server down at start-up.
    body = TEMPLATE.read_bytes().replace(b"{{base}}", base.encode("utf-8"))
    return Reply(status=200, body=body,
                 headers={"Content-Type": "text/html; charset=utf-8",
                          # Never store a lock screen: a cached copy would be served over the
                          # board after the credential is accepted.
                          "Cache-Control": "no-store"})


