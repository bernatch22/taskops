"""The server's front door: `GET /`, and the two calls a login is made of.

Everything under `/<project>/` is one board behind one secret. This module is what sits ABOVE
that: the page a person reaches when they type the hostname, and the endpoints that turn a
GitHub token into a session. It is the only part of the server that is not about one project,
which is why it is not in `router` — that one is built per project and mounted.

**The page lists NOTHING without a session.** Served to anyone, it is an instruction and not
an index: naming the boards would hand every visitor the enumeration the per-project 404 is
built to deny. With a session in `localStorage` it asks `/api/projects` and renders the links
that came back — the list is computed by the server from the session, never guessed by the JS.

**HTML inline, no bundle, no dependency.** This page must work on a server whose UI was never
built, because "the boards are at these URLs" is exactly what you need when something is
wrong. It is a few hundred bytes and has no build step; the studio is untouched by it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..._errors import TaskopsError
from ...usecases._sessions import resolve
from ...usecases.accounts import authenticate
from ._wire import Reply, Request, error_reply, json_reply

__all__ = ["root_route", "bearer", "PAGE"]

PAGE = """<!doctype html><meta charset="utf-8"><title>taskops</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{color-scheme:light dark}
 body{font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;max-width:44rem;
      margin:12vh auto;padding:0 1.5rem}
 h1{font-size:1.1rem;letter-spacing:.02em;margin:0 0 .2rem}
 p,li{color:#888} a{color:inherit}
 code{background:#8883;padding:.1rem .35rem;border-radius:.25rem}
 ul{list-style:none;padding:0;margin:1.5rem 0}
 li{margin:.35rem 0} li a{font-size:1rem;color:inherit;text-decoration:none}
 li a:hover{text-decoration:underline}
 input{font:inherit;padding:.4rem .5rem;width:22rem;max-width:100%;
       border:1px solid #8886;border-radius:.25rem;background:transparent;color:inherit}
 button{font:inherit;padding:.4rem .8rem;border-radius:.25rem;border:1px solid #8886;
        background:transparent;color:inherit;cursor:pointer}
</style>
<h1>taskops</h1>
<p id="who">checking your session…</p>
<ul id="boards"></ul>
<p>to get in, on your machine:</p>
<p><code>taskops login https://<span id="host"></span></code></p>
<p>or paste a session here:</p>
<p><input id="key" placeholder="session" autocomplete="off"><button id="go">enter</button></p>
<script>
 var K = "taskops.session";
 document.getElementById("host").textContent = location.host;
 function show(s){
   fetch("api/projects", {headers:{Authorization:"Bearer "+s}}).then(function(r){
     if(!r.ok){ localStorage.removeItem(K); throw 0; } return r.json();
   }).then(function(d){
     document.getElementById("who").textContent = "signed in as " + d.login;
     document.getElementById("boards").innerHTML = d.projects.map(function(p){
       return '<li><a href="' + p.path + '?token=' + encodeURIComponent(s) + '">'
              + p.name + '</a></li>';
     }).join("");
   }).catch(function(){
     document.getElementById("who").textContent = "not signed in";
   });
 }
 document.getElementById("go").onclick = function(){
   var v = document.getElementById("key").value.trim();
   if(v){ localStorage.setItem(K, v); show(v); }
 };
 var have = localStorage.getItem(K);
 if(have){ show(have); } else { document.getElementById("who").textContent="not signed in"; }
</script>
"""
"""The whole front page. `fetch("api/projects")` is RELATIVE on purpose — the page is served
at `/`, so it resolves to `/api/projects` whatever hostname or proxy prefix is in front.

Each board link carries `?token=<session>`, which is what makes the link WORK without the
studio bundle learning anything: the app already takes its credential from that parameter,
and the mount exchanges a session for the project's own token before any route sees it. The
project token itself never reaches the browser."""


def root_route(home: Path, request: Request) -> Reply | None:
    """The routes that belong to the server rather than to a project, or None to fall through.

    None and not a 404: everything this does not name is a project path, and answering here
    would take `/axion/api/board` away from the mount.
    """
    if request.path in ("", "/"):
        return Reply(status=200, body=PAGE.encode("utf-8"),
                     headers={"Content-Type": "text/html; charset=utf-8"})
    if request.path == "/api/auth/github" and request.method == "POST":
        return _login(home, request)
    if request.path == "/api/projects" and request.method == "GET":
        return _projects(home, request)
    return None


def _login(home: Path, request: Request) -> Reply:
    """`{"github_token": …}` in, `{login, session, projects}` out. The typed error carries its
    own status, so 403 (no repository) and 502 (GitHub did not answer) are one line of code."""
    token = str(request.payload().get("github_token") or "")
    try:
        return json_reply(authenticate(home, token))
    except TaskopsError as err:
        return error_reply(err.http_status, str(err), err.code)


def _projects(home: Path, request: Request) -> Reply:
    """What this session opens. The paths are built here so a client never assembles a URL."""
    found: dict[str, Any] | None = resolve(home, bearer(request))
    if found is None:
        return error_reply(401, "that session is unknown or has expired — run "
                                "`taskops login <url>` again", "unauthorized")
    names: list[str] = list(found.get("projects") or [])
    return json_reply({"login": found.get("login", ""),
                       "projects": [{"name": name, "path": f"/{name}/"} for name in names]})


def bearer(request: Request) -> str:
    """The presented credential, header or query. `?token=` is accepted for the same reason
    `Policy` accepts it: `EventSource` cannot send a header, and a rule that holds for one
    path is a rule somebody moves."""
    told = request.headers.get("authorization", "")
    return told[7:].strip() if told.lower().startswith("bearer ") else request.param("token")
