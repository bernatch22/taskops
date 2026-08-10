# Changelog

The source of truth for release notes — GitHub Releases are extracted from
here, never written twice.

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
