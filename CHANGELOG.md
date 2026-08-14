# Changelog

The source of truth for release notes — GitHub Releases are extracted from
here, never written twice.

## Unreleased — the forge enrols the team; GitHub is the owner's, and nobody else's

- **A STALLED row says how its holder went quiet, not just that it did.** A
  session limit took five workers at once and every stalled row read "quiet for
  1h", so deciding resume-vs-reassign meant opening each card. Stalled rows now
  carry `last_event = {kind, ago}` — the last event on the card's thread — and
  `commits`, the number of commits bound to the card, so "handed over and never
  heard from" (`edited`), "claimed then silent" (`claimed`), "said one thing then
  gone" (`comment`) and "three commits on the branch" are four different lines.
  Both are DERIVED per read (`verbs/_rows.py::forensics`) and ride on the stalled
  group alone, the way `waiting_on` rides on blocked: nothing new is stored, no
  cause of death is recorded — the lease's only heartbeat is MCP traffic — and
  every other board row is byte-identical to what it was. The MCP board prints
  them on the STALLED line (`mcp/boardview.py`).

- **The feed heals itself — the header no longer sticks on "offline".** The
  dashboard's live channel had two dead ends and both are removed
  (`ui/src/client.ts::subscribe`): a WebSocket that had opened and then dropped
  retried **exactly once** after 500ms and, if that single attempt did not open,
  fell back to SSE permanently; and the EventSource error handler only reported
  `onLive(false)`, so an EventSource that died fatally (`readyState` CLOSED — a
  non-200 while the server restarts) was **never retried by anything**. The page
  was then permanently offline and stale until a manual refresh. There is now one
  reconnect loop with no terminal state but `stop()`: WS retries with capped
  exponential backoff (500ms doubling to 8s), a fatally-closed SSE hands itself
  back to that loop, and coming back live pokes exactly one refetch — the
  transports' own `hello` frame — so staleness heals with the connection and
  never double-fetches. `subscribe` takes an injectable `Env`, and the state
  machine, including both removed dead ends, is pinned headlessly in
  `ui/smoke/sections/feed-reconnect.tsx`.
- **The board is animated, and says WHO is on each card.** When a refetch moves a
  tile to another column it now travels there instead of teleporting — FLIP
  (measure, invert, play) in `ui/src/components/board/flip.ts` + `useFlip.ts`,
  CSS transitions only, no animation library and no timers beyond the transition;
  `prefers-reduced-motion` skips the play, never the layout. And a card being
  worked shows its holder: **one** `shared/Avatar.tsx` disc now serves both the
  header presence row and the card tile, which previously coloured the same agent
  two different ways (four hash tones in the header, accent-vs-grey by role on the
  tile). The disc has two independent axes — the hue is derived from the actor
  string over 24 steps, because eight agents into four tones is a guaranteed
  collision, and `live` (the lease actually being held) is the emphasis, not the
  colour. The avatar travels with the tile in the animation.
- **A FLOW view beside the columns.** The Board page gains a `columns | flow`
  segmented control (`components/board/ViewToggle.tsx`, state on the page and in
  `localStorage` — not a route, and not a sixth tab: the flow IS the board, drawn
  differently). Flow draws the dependency graph left to right, agents on the
  nodes, with the geometry decided without a DOM (`components/flow/layout.ts`;
  `FlowView.tsx` measures and paints, and decides nothing). **Every edge ends on a
  blocked node**, and that is honesty rather than a shortcut: a `BoardRow` carries
  no `after`, and the one dependency fact the board payload holds is `waiting_on`,
  which `verbs/pulse.py` attaches to the BLOCKED group alone from
  `core/graph.py::blockers` — which filters to dependencies that have not closed.
  So bands come from a floor per state (done · in flight · waiting) raised by the
  longest open-blocker chain, never from the edges alone.
- **A finished chapter reads as a story, not a graveyard column.** Focusing a
  landed or fully-closed chapter in the dashboard now replaces the six kanban
  columns with a landing-timeline: cards in the order they landed, each with its
  closing line, diff-stat and worked time, under a header of aggregate stats.
  Completion is derived per read on the client from the board payload — no new
  verb, no new stored status — and the view is read-only, fed by the existing
  `activity` verb; an open chapter still shows the columns unchanged.
- **`taskops board forge <owner>/<repo>` declares AND syncs.** It used to record
  a fact; it now records it and then enrols the team behind it: one authenticated,
  paginated `GET /repos/<owner>/<repo>/collaborators?permission=<need>` with the
  owner's own token, then the PUBLIC `github.com/<login>.keys` per person, then a
  single `members.enroll` over `/rpc` carrying principals and key lines. **No
  GitHub token ever reaches a taskops host, and none is stored on either side** —
  it is a header on the owner's outgoing request and dies with the command.
  Re-running it re-syncs, and a run that changes nothing writes nothing.
- **The sync ADDS ONLY, and reports the rest.** A principal the batch did not
  name is printed as drift with the exact `taskops revoke --key SHA256:…` beside
  it, and nothing revokes itself: a principal enrolled by invite is not a GitHub
  login, and a pruning sync would retire them for existing. The owner is never in
  that list. A collaborator whose GitHub account publishes no ssh key is NAMED
  with `taskops invite <login>`, never skipped in silence. A key another
  principal already holds, or one that was revoked here, is reported and not
  written — a batch may not move a key off somebody who is not in it.
- **The dev's GitHub door is DELETED.** `POST /<board>/join/github`, the
  `--github` flag and the token discovery inside `join` are gone — not deprecated,
  not answering 410. It made every dev's own credential travel to a host that has
  no business seeing one, to prove a fact the owner already holds, and it asked
  for an ssh key from people who, having push over ssh, had published one already.
  A dev in a fresh clone now types **`taskops join`**, bare: their key was
  enrolled before they ever typed anything. Invites are unchanged, and a board
  that declared no forge is invite-only exactly as before.
- **The board says which forge opens it.** The declared forge rides on the
  `board` payload beside `visibility` — derived per read from the one event that
  declared it — and the dashboard draws it under the board's identity as
  `github.com/<owner>/<repo> · push`. A board with no forge sends no key at all,
  so every older reader works unchanged.
- **The clock stops deciding who is alive: a card is handed over, not expired.**
  `taskops_assign` now hands over a card even while its lease is still live
  (`verbs/assign.py`, `store/handover.py`) — the lease's only heartbeat is MCP
  traffic, so expiry could not tell a dead worker from one editing quietly.
  `stalled` is a report, never a mechanism; the orchestrator that spawned the
  process is the authority, and the card goes to a NAMED replacement in the same
  call. The worker's brief says so (`mcp/brief.py`). Still not a `recover`:
  nothing is resurrected, and nothing is taken by the passage of time.

## 0.3.3 — a clone joins with two words

- **`taskops join` reads the address the clone already carries.** v2 committed
  `.taskops/board.json` exactly as v1 did — and never read it back: a bare join
  resolved through the per-machine recorded remote, so a fresh clone died on
  "which host?" while holding the answer in its tree. Restored: inside a clone,
  `taskops join` (or `taskops join --github`, first time) is the whole
  onboarding. `taskops remote add` remains for a checkout that carries no
  address, or a join onto a different board.

## 0.3.2 — the window's address, prose that reads as prose, and a link that stays inside

- **`taskops ui` opens `http://127.0.0.1:<port>/`.** It used to hand out
  `/board/ui/?token=…`, which leaked two implementation details into the one URL
  a human types — `board` is only the name a window mounts its single board
  under, and `/ui/` was a door on a HOST, which has served no page since the
  dashboard moved to the binary. Worse, the page then rewrote the address bar to
  a path recomputed from that mount, so a refresh landed on `/` and got a JSON
  404. The board's own routes are unchanged and still hang off `/board`.
- **A markdown report is rendered as markdown.** `.md` reports — the ones written
  to be read — were served as their own source, hashes and pipes and all: the
  door typed them `text/plain` and the reader dropped them in a `<pre>`. The door
  now answers `text/markdown` and the dashboard draws them with the same renderer
  a card spec and a close note use. It needs no sandbox and gets none: that
  renderer builds React elements and emits no HTML, so raw markup inside a report
  is drawn as the characters it is. A self-contained HTML report still goes in
  the `allow-scripts`-only frame, and an unrecognised type still degrades to
  plain text.
- **The card's Worktree block opens the worktree, in the dashboard.** It offered
  a forge `compare ↗` — two branches on somebody else's website, rendered for a
  clone that may not be yours. It now opens the worktree diff view, reading your
  own clone, with the card's thread beside it. It needs no forge slug, so a board
  with no GitHub at all has it too.
- The chapter goal pane got a taller clamp — a long goal scrolls less.

## 0.3.1 — three chapters: reports, GitHub as an introduction, and the whole lifecycle

- **Reports.** A milestone's narration becomes part of the board: `taskops_activity`
  reads the whole story of N cards at once, `taskops_filed` records a report as
  `{path, title, milestone, sha}` — the CONTENT stays a file in `.taskops/reports/`
  and the list is a fold over the log, never a table. The dashboard lists a
  milestone's reports and renders one in a sandboxed iframe, served by a read-only
  `/git` door that hands back a committed file at a rev.
- **GitHub is the INTRODUCTION, never the credential.** `taskops join <board>
  --github` enrols your ssh key when you have push on the repo the board declared.
  The token is asked for once, travels in one request body, and is stored nowhere;
  what persists is a pubkey. A board opts in with `taskops board forge
  <owner>/<repo>` and opts back out with `--clear` — owner only, both ways. Absent
  a forge (how every board is born) that door does not exist.
- **The lifecycle runs backwards too.** `taskops board pull` brings a hosted board
  down as a snapshot — the same five steps as `push`, in reverse, over paging — and
  `taskops board rm` takes one off a host. `rm` REFUSES to destroy a history this
  checkout does not hold, judged on the host against the board's real event ids,
  and says which of the two ways out you want. There is no `--force` and
  `--discard-history` is not an alias for one.
- **Fixed: the dashboard flooded a remote board with requests.** The forward
  published a change frame on any answer carrying a `seq`, and every envelope
  carries one — so every READ announced a change, the page refetched, and the loop
  ran at coalesce speed. Reads no longer poke anybody.
- **The `taskops ui` window is a lease, not a pidfile.** A `flock` that dies with
  its holder, an identity check on `/healthz` before a browser is reopened, and a
  server that retires itself when no tab has been open for thirty minutes.
- **Fixed: a minted secret can no longer start with `-`**, which made roughly one
  invite in 64 unusable as a CLI flag value.
- A client that hangs up mid-response is no longer printed as a crash.

## 0.3.0 — the rewrite: derive, don't write

A ground-up rewrite of taskops (v1 was ~340 files; this is ~110 under
`src/taskops`, zero runtime dependencies). It follows 0.2.0 as a MINOR bump:
the public contract (CLI, MCP, storage) breaks completely, which in 0.x is a
minor, and nothing here claims 1.0 maturity yet. Nothing about v1's wire, CLI or
storage survives — this is a new product under the old console script.

- **Three stored statuses** (`open`, `done`, `dropped`); ready/doing/blocked/
  stalled/review/changes are all derived per read. No `recover` verb exists
  because nothing it would repair can happen: a dying worker's lease expires on
  its own.
- **Branches are inhabited, not switched**: one worktree per card, one
  integration worktree per milestone, `git switch` appears nowhere. Work
  reaches the trunk through `taskops_merge`, and a finished chapter lands with
  `taskops_merge milestone=` — the human's explicit call.
- **Nine MCP tools** are the only management interface; the CLI behaves like
  git — it connects, it never manages.
- **ssh-key login**: the server answers a challenge, `ssh-keygen -Y sign`
  signs it, `-Y verify` decides. No pip crypto dependency. `remote add` once,
  then every verb goes bare — `board create`, `board push`, `join <name>` —
  with the key discovered the way ssh discovers one. Keys exist so tokens do
  not travel: what lands on disk is a refreshing session, never a standing
  token. Boards joined before keys existed keep working untouched.
- **`taskops join <name>`** joins bare (registered key = the whole
  credential), `--invite <id>` enrols a new teammate's key in the same call,
  and the old `?token=`/`?invite=` URL form keeps working.
- **A public board is GitHub-public**: anonymous read, keyed write, no third
  state — and an anonymous crawl leaves the server's files byte-identical.
- **The dashboard** (`taskops ui`) is served from YOUR checkout: real diffs
  read from your own clone through a read-only `/git` door, cards as pull
  requests, chapters as compares. The committed bundle ships in the wheel, so
  `pip install` serves it with no node toolchain.
- **The board host is API-only**: `/rpc`, `/feed`, `/healthz`. It deliberately
  has no clone, so it serves no dashboard.
