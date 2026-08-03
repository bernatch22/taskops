"""The server's front page: the list of boards you can reach, and the way in when you cannot.

Split out of `root` when it outgrew that module's line budget, and the split is a real one:
`root` is the ROUTES this server owns above any project, and this is the one thing it serves
that a person looks at. They change for different reasons — a new endpoint is not a redesign.

**No build step, no bundle, no dependency, and that is load-bearing.** This page has to work on
a server whose UI was never compiled, because "the boards are at these URLs" is exactly what
somebody needs when something is wrong. It is a few kilobytes of inline HTML and it has no
opinion about the studio, which is a separate application served per board.

**It lists NOTHING without a session.** Served to anyone, it is an instruction and not an index:
naming the boards would hand every visitor the enumeration that the per-project bare 404 exists
to deny. With a session it asks `/api/projects` and renders what comes back — the list is
computed by the SERVER from that session and never guessed by the JavaScript.

What each row shows is deliberately what costs nothing: the name, the repository behind it when
there is one, and when it last moved. A count of open cards would mean opening every board's
sqlite to draw a front page, and this is the page that must still answer when a board's cache is
the broken thing.
"""

from __future__ import annotations

__all__ = ["PAGE"]

PAGE = """<!doctype html><meta charset="utf-8"><title>taskops</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{color-scheme:light dark;--ink:#12151c;--dim:#6b7280;--faint:#9aa1ae;--line:#e2e5ea;
       --card:#fff;--bg:#f7f8fa;--go:#4f9c00}
 @media (prefers-color-scheme:dark){:root{--ink:#e6e8ee;--dim:#8b93a7;--faint:#5b6479;
       --line:#262c39;--card:#171a21;--bg:#0f1115;--go:#b8ff3a}}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,
      -apple-system,"Segoe UI",system-ui,sans-serif}
 main{max-width:40rem;margin:0 auto;padding:9vh 1.25rem 4rem}
 header{display:flex;align-items:center;gap:.6rem;margin-bottom:.25rem}
 .logo{display:grid;place-items:center;width:28px;height:28px;border-radius:8px;
       background:var(--go);color:#0d1207;font-weight:700}
 h1{font-size:1.05rem;margin:0;letter-spacing:-.01em}
 .who{color:var(--dim);font-size:.85rem;margin:0 0 1.6rem 2.2rem}
 mark{background:none;color:var(--ink);font-weight:600}
 ul{list-style:none;padding:0;margin:0 0 1.75rem}
 li{margin:0 0 .5rem}
 li a{display:flex;align-items:center;gap:.7rem;padding:.7rem .9rem;text-decoration:none;
      color:inherit;background:var(--card);border:1px solid var(--line);border-radius:9px}
 li a:hover{border-color:var(--faint)}
 .name{font-weight:600;letter-spacing:-.01em}
 .repo{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--faint);
       overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .when{margin-left:auto;flex:none;color:var(--faint);font-size:.78rem}
 .go{flex:none;color:var(--faint)}
 .hint{color:var(--dim);font-size:.88rem;margin:0 0 .5rem}
 code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--card);
      border:1px solid var(--line);border-radius:6px;padding:.15rem .4rem;user-select:all}
 .box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:1.1rem}
 form{display:flex;gap:.5rem;margin:.9rem 0 0}
 input{flex:1;min-width:0;font:inherit;font-size:.9rem;padding:.45rem .6rem;color:inherit;
       background:var(--bg);border:1px solid var(--line);border-radius:7px}
 button{font:inherit;font-size:.9rem;padding:.45rem .95rem;border-radius:7px;cursor:pointer;
        border:1px solid transparent;background:var(--go);color:#0d1207;font-weight:600}
 .empty{color:var(--dim);font-size:.9rem;margin:0 0 1.6rem}
</style>
<main>
 <header><span class="logo">t</span><h1>taskops</h1></header>
 <p class="who" id="who">checking your session…</p>
 <ul id="boards"></ul>
 <div class="box" id="way-in" hidden>
   <p class="hint">To get in, on your machine:</p>
   <p><code id="cmd">taskops login</code></p>
   <p class="hint" style="margin:.9rem 0 0">Already have a session? Paste it:</p>
   <form id="f"><input id="key" placeholder="session" autocomplete="off"
     spellcheck="false"><button>Enter</button></form>
 </div>
</main>
<script>
 var K = "taskops.session";
 var who = document.getElementById("who"), list = document.getElementById("boards");
 var wayIn = document.getElementById("way-in");
 document.getElementById("cmd").textContent =
   "taskops login " + location.protocol + "//" + location.host;

 function ago(ts){
   if(!ts) return "";
   var s = Math.max(0, Date.now()/1000 - ts);
   if(s < 90) return "just now";
   if(s < 5400) return Math.round(s/60) + "m ago";
   if(s < 172800) return Math.round(s/3600) + "h ago";
   return Math.round(s/86400) + "d ago";
 }
 function esc(t){ var d = document.createElement("div"); d.textContent = t; return d.innerHTML; }

 function show(s){
   fetch("api/projects", {headers:{Authorization:"Bearer "+s}}).then(function(r){
     if(!r.ok){ localStorage.removeItem(K); throw 0; } return r.json();
   }).then(function(d){
     who.innerHTML = "signed in as <mark>" + esc(d.login) + "</mark>";
     wayIn.hidden = true;
     if(!d.projects.length){
       list.innerHTML = "";
       who.insertAdjacentHTML("afterend",
         '<p class="empty">No boards here yet — <code>taskops board create &lt;name&gt;</code>'
         + ' in the project you want one for.</p>');
       return;
     }
     list.innerHTML = d.projects.map(function(p){
       return '<li><a href="' + p.path + '?token=' + encodeURIComponent(s) + '">'
            + '<span class="name">' + esc(p.name) + '</span>'
            + (p.github ? '<span class="repo">' + esc(p.github) + '</span>' : '')
            + '<span class="when">' + ago(p.updated) + '</span>'
            + '<span class="go">&rsaquo;</span></a></li>';
     }).join("");
   }).catch(function(){
     who.textContent = "not signed in";
     list.innerHTML = "";
     wayIn.hidden = false;
   });
 }

 document.getElementById("f").onsubmit = function(e){
   e.preventDefault();
   var v = document.getElementById("key").value.trim();
   if(v){ localStorage.setItem(K, v); show(v); }
 };

 var given = new URLSearchParams(location.search).get("token");
 if(given){
   localStorage.setItem(K, given);
   history.replaceState(null, "", location.pathname);
 }
 var have = given || localStorage.getItem(K);
 if(have){ show(have); } else { who.textContent = "not signed in"; wayIn.hidden = false; }
</script>
"""
"""The whole front page.

`fetch("api/projects")` is RELATIVE on purpose — the page is served at `/`, so it resolves
correctly whatever hostname or proxy prefix is in front of it.

Each board link carries `?token=<session>`, and that is what makes the link WORK without the
studio bundle learning anything: the app already takes its credential from that parameter, and
the mount exchanges a session for the project's own token before any route sees it. The project
token itself never reaches the browser.

`?token=` is also ACCEPTED here, which is what makes `taskops open --projects` land on a list
instead of on a prompt asking for something the caller demonstrably already had. It is adopted
into `localStorage` and then removed from the address bar with `replaceState`, so the credential
does not survive in history, in a bookmark, or in whatever gets screen-shared next.

Every value from the server goes through `esc` before it reaches `innerHTML`. A board name is
constrained to `[a-z0-9-]` and a `github` slug to its own pattern, so nothing here can currently
carry a bracket — which is exactly the reasoning that makes the next field somebody adds the
one that does.
"""
