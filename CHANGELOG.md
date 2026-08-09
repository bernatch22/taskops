# Changelog

The source of truth for release notes — GitHub Releases are extracted from
here, never written twice.

## 2.0.0 — the rewrite: derive, don't write

A ground-up rewrite of taskops (v1 was ~340 files; this is ~110 under
`src/taskops`, zero runtime dependencies). Nothing about v1's wire, CLI or
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
