#!/bin/sh
# The live smoke for a taskops board HOST. Read-only, no credential, no state:
# every request below is a GET, a `board` read or a git ref ADVERTISEMENT, so it
# is safe to run against production at any time, including from a laptop that
# never joined the board.
#
# ONE thing this script deliberately does NOT do: a real push round-trip. It
# would need a scratch board, and creating one is a WRITE on somebody's
# production host with an owner credential this script must not want — and a
# throwaway branch pushed to a real board could never be cleaned up, because the
# host refuses ref deletions BY DESIGN (§16: that permanence is the chapter).
# There is no safe destructive line to ship here, so the receive door is pinned
# by what it must answer a caller with no credential — 401 + WWW-Authenticate,
# section (g) — and the round-trip itself lives in the suite
# (`tests/test_topology.py`), against a host it created.
#
#   sh smoke.sh                                  # the author's host, defaults below
#   sh smoke.sh <host> <public-board> <private-board> <card-branch> <landed-branch>
#
# Every assertion is here because it FAILED once, in production, against a real
# reader — the comment above each one says which report it comes from. Nothing
# is asserted because it seemed prudent: a smoke list that grows by taste stops
# being read, and a green line that never could have gone red is a lie about
# coverage. It exits non-zero on the FIRST failure, so the first red line is the
# whole diagnosis.
#
# `pass` prints what was actually observed, never just OK — a smoke you cannot
# read the evidence out of is a smoke you end up re-running by hand anyway.

set -eu

HOST=${1:-taskops.bernardocastro.dev}
BOARD=${2:-taskops-v2}
PRIVATE=${3:-axion}
BRANCH=${4:-tk-32d2ba}
# A card whose branch was PRUNED on the forge while its work sits in the trunk —
# the fault that turned the pull mirror inside out (§16, 2026-08-31). The host
# holds the history now and never prunes, so this ref must answer forever.
LANDED=${5:-tk-dfaff7}

BASE="https://$HOST"
C="curl -sS -m 15"

fail() { printf '\nFAIL  %s\n      %s\n' "$1" "$2" >&2; exit 1; }
pass() { printf 'ok    %s\n        %s\n' "$1" "$2"; }
head_ln() { printf '\n-- %s\n' "$1"; }

# ── (e) the host itself ───────────────────────────────────────────────────────
# First, because every failure below is ambiguous until this one is green: a
# 502 from the proxy and a broken board answer the same shape of nothing.
head_ln "healthz — the host is up"
body=$($C "$BASE/healthz") || fail "GET /healthz" "no answer from $BASE"
case $body in
  *'"ok": true'*|*'"ok":true'*) pass "GET /healthz" "$body" ;;
  *) fail "GET /healthz" "$body" ;;
esac

# ── (a) the board's own address IS the page ───────────────────────────────────
# Reported 2026-08-31: the page was at /<board>/ui/ and /<board>/ was a 404 —
# the shortest address on the host, the one a person types, answered nothing.
# Asserted on the BARE path too: /<board> without the trailing slash is what
# gets pasted into Slack, and a router that only handles one of the two looks
# fine in a browser (it follows the redirect) and breaks every copied link.
head_ln "the page at the board's own address"
for path in "/$BOARD/" "/$BOARD"; do
  page=$($C "$BASE$path") || fail "GET $path" "no answer"
  case $page in
    *'app.js'*) pass "GET $path" "html referencing app.js ($(printf %s "$page" | wc -c | tr -d ' ') bytes)" ;;
    *) fail "GET $path" "not the page: $(printf %s "$page" | head -c 200)" ;;
  esac
done
# And its assets resolve from that address: the page's own links are relative
# (./app.js off index.html), so they arrive as board TAILS and the router has to
# tell them from the machine doors. If this 404s, the page loads unstyled and
# blank with nothing in the server log to say why.
for asset in app.js style.css; do
  code=$($C -o /dev/null -w '%{http_code} %{content_type}' "$BASE/$BOARD/$asset") \
    || fail "GET /$BOARD/$asset" "no answer"
  case $code in
    200*) pass "GET /$BOARD/$asset" "$code" ;;
    *) fail "GET /$BOARD/$asset" "$code" ;;
  esac
done

# ── (b) a bare `Bearer` reads a PUBLIC board ──────────────────────────────────
# THE fault of this chapter, shipped in 0.5.0 and reported 2026-08-31: the page
# sends `Authorization: "Bearer " + token()`, so with no token the header
# arrives as `Bearer`, and the old extractor returned the literal string
# "Bearer" as somebody's token — "unknown credential — run: taskops join" to a
# reader who presented nothing. Anonymous reads worked only with NO header at
# all, which no browser client can express. Both shapes are asserted: the
# no-header stranger (what the suite always tested) and the bare bearer (what
# every browser actually sends).
head_ln "a bare Bearer is no credential — public board reads"
rpc() { # rpc <path> [<authorization value>]
  if [ $# -gt 1 ]; then
    $C -o /dev/null -w '%{http_code}' -X POST "$BASE$1" \
      -H 'Content-Type: application/json' -H "Authorization: $2" \
      -d '{"verb": "board", "args": {}}'
  else
    $C -o /dev/null -w '%{http_code}' -X POST "$BASE$1" \
      -H 'Content-Type: application/json' -d '{"verb": "board", "args": {}}'
  fi
}
code=$(rpc "/$BOARD/api/rpc" "Bearer") || fail "POST /$BOARD/api/rpc (bare Bearer)" "no answer"
[ "$code" = 200 ] || fail "POST /$BOARD/api/rpc (bare Bearer)" "HTTP $code — the 0.5.0 fault is back"
pass "POST /$BOARD/api/rpc  Authorization: Bearer" "HTTP 200"
code=$(rpc "/$BOARD/api/rpc") || fail "POST /$BOARD/api/rpc (no header)" "no answer"
[ "$code" = 200 ] || fail "POST /$BOARD/api/rpc (no header)" "HTTP $code"
pass "POST /$BOARD/api/rpc  no Authorization" "HTTP 200"
# The other half of that fix, and the reason it is not a one-line
# generalisation: a credential that WAS presented and does not check out still
# refuses loudly. "Unparseable is anonymous" would turn an expired token into a
# silent read-only downgrade instead of a sentence naming the way back in.
body=$($C -X POST "$BASE/$BOARD/api/rpc" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer not-a-token' -d '{"verb": "board", "args": {}}') \
  || fail "POST with a wrong token" "no answer"
case $body in
  *'unknown credential'*) pass "POST /$BOARD/api/rpc  Bearer not-a-token" "refused: unknown credential" ;;
  *) fail "POST with a wrong token" "$body" ;;
esac

# ── (c) a PRIVATE board still refuses ─────────────────────────────────────────
# The wall moved for public boards; it must not have moved here. And the
# SENTENCE matters as much as the status: somebody who presented nothing is told
# how to join, which is a different answer from "unknown credential".
head_ln "a private board still refuses the same stranger"
body=$($C -X POST "$BASE/$PRIVATE/api/rpc" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer' -d '{"verb": "board", "args": {}}') \
  || fail "POST /$PRIVATE/api/rpc" "no answer"
# Grepped for `no credential` and NOT for `taskops join`: both refusals name
# that command, so the looser grep passes on the 0.5.0 fault itself — where a
# private board answered `unknown credential` to a stranger who presented
# nothing. The whole point is WHICH sentence comes back.
case $body in
  *'no credential'*) pass "POST /$PRIVATE/api/rpc  Authorization: Bearer" "refused: no credential — run: taskops join" ;;
  *) fail "POST /$PRIVATE/api/rpc" "expected the no-credential refusal, got: $body" ;;
esac

# ── (d) a card branch renders a diff from the board's own git ─────────────────
# The hosted window's whole point: a reader with NO clone. Before the host had
# git of its own, every diff fell through the UI's cascade to a forge link — a
# blank presented as the window. Written for the pull mirror (2026-08-30) and
# kept verbatim through the reversal (2026-08-31, §16): the SOURCE moved from a
# mirror of the forge to `<root>/<board>/repo.git`, and the assertion did not,
# which is the point — the reader's URL is the contract, not the plumbing. A
# tk-* branch on purpose: `master` is fetched by any clone, and what this catches
# is a host whose git holds nothing but the trunk.
head_ln "a card branch diffs from the board's own git"
body=$($C "$BASE/$BOARD/api/git/commit/$BRANCH") || fail "GET git/commit/$BRANCH" "no answer"
case $body in
  *'"patch"'*) pass "GET /$BOARD/api/git/commit/$BRANCH" "a diff ($(printf %s "$body" | wc -c | tr -d ' ') bytes)" ;;
  *) fail "GET git/commit/$BRANCH" "no diff: $(printf %s "$body" | head -c 300)" ;;
esac

# ── (f) every 0.5.0 address still answers ─────────────────────────────────────
# Links were pasted the day they existed, .mcp.json files are configured against
# them, four legacy-bearer production boards speak them, and `taskops ui`'s
# upstream forward builds them. An old address that 404s in silence is this
# chapter's own rule broken.
head_ln "the 0.5.0 addresses, unprefixed"
code=$($C -o /dev/null -w '%{http_code}' "$BASE/$BOARD/ui/") || fail "GET /$BOARD/ui/" "no answer"
[ "$code" = 200 ] || fail "GET /$BOARD/ui/" "HTTP $code"
pass "GET /$BOARD/ui/" "HTTP 200"
code=$(rpc "/$BOARD/rpc" "Bearer") || fail "POST /$BOARD/rpc" "no answer"
[ "$code" = 200 ] || fail "POST /$BOARD/rpc" "HTTP $code"
pass "POST /$BOARD/rpc" "HTTP 200"
code=$($C -o /dev/null -w '%{http_code}' "$BASE/$BOARD/git/commit/$BRANCH") \
  || fail "GET /$BOARD/git/commit/$BRANCH" "no answer"
[ "$code" = 200 ] || fail "GET /$BOARD/git/commit/$BRANCH" "HTTP $code"
pass "GET /$BOARD/git/commit/$BRANCH" "HTTP 200"
# /feed is a stream that never ends by design, so this reads the HEADERS and
# hangs up. curl's own timeout is therefore EXPECTED here and not a failure —
# what is asserted is the content type, which is what tells an SSE client it may
# start reading.
headers=$(curl -sS -m 3 -D - -o /dev/null "$BASE/$BOARD/feed" 2>/dev/null || true)
case $headers in
  *event-stream*) pass "GET /$BOARD/feed" "text/event-stream" ;;
  *) fail "GET /$BOARD/feed" "no event-stream header: $(printf %s "$headers" | tr '\r\n' '  ')" ;;
esac

# ── (g) the board's OWN git — clone, and the wall in front of a push ──────────
# The reversal of 2026-08-31 (ARCHITECTURE §16, "The host becomes the remote"):
# the host holds the board's git at /<board>/repo.git and GitHub became the
# outbound copy. Every line here is a ref ADVERTISEMENT — git's first request,
# the one `git clone` and `git ls-remote` begin with — so nothing is fetched,
# nothing is written, and no credential is offered. GIT_TERMINAL_PROMPT=0 so a
# door that challenges fails the assertion instead of hanging on a password
# prompt nobody is at the keyboard for.
head_ln "the board's own git at /<board>/repo.git"
export GIT_TERMINAL_PROMPT=0
# A PUBLIC board clones anonymously: read follows the board's visibility exactly
# as /rpc does, and running no verb it leaves no presence row (§11's invisible
# write). `ls-remote` is the whole clone handshake minus the pack.
refs=$(git ls-remote "$BASE/$BOARD/repo.git" 2>&1) || \
  fail "git ls-remote $BASE/$BOARD/repo.git" "$(printf %s "$refs" | tr '\n' ' ' | head -c 300)"
case $refs in
  *refs/heads/*) pass "git ls-remote /$BOARD/repo.git  (anonymous)" \
    "$(printf %s "$refs" | grep -c 'refs/') ref(s) advertised" ;;
  *) fail "git ls-remote /$BOARD/repo.git" "no refs advertised: $(printf %s "$refs" | head -c 300)" ;;
esac

# An anonymous PUSH is refused, and the SHAPE of the refusal is the assertion,
# not just the fact of it: git volunteers Basic only after a 401 bearing
# WWW-Authenticate, so a 409 (which is what every other write door answers)
# reads to git as "the URL is broken" and it never sends the credential it was
# holding. Both halves are checked — the status and the header.
recv="$BASE/$BOARD/repo.git/info/refs?service=git-receive-pack"
got=$(curl -sS -m 15 -D - -o /dev/null "$recv" 2>/dev/null) || fail "GET receive-pack advert" "no answer"
code=$(printf %s "$got" | sed -n '1s/[^ ]* \([0-9][0-9]*\).*/\1/p')
[ "$code" = 401 ] || fail "GET /$BOARD/repo.git receive-pack (anonymous)" \
  "HTTP $code — an anonymous push is a write and must be refused (§11)"
case $got in
  *[Ww][Ww][Ww]-[Aa]uthenticate*[Bb]asic*) pass "GET /$BOARD/repo.git receive-pack (anonymous)" \
    "HTTP 401 + WWW-Authenticate: Basic — git will now offer the helper's token" ;;
  *) fail "GET /$BOARD/repo.git receive-pack (anonymous)" \
    "401 with no WWW-Authenticate: git would never send its credential" ;;
esac

# And a PRIVATE board is not clonable by a stranger either — the visibility rule
# is one rule asked by one more door, so this must refuse exactly as /rpc did in
# section (c), with the same 401 shape git understands.
got=$(curl -sS -m 15 -D - -o /dev/null \
  "$BASE/$PRIVATE/repo.git/info/refs?service=git-upload-pack" 2>/dev/null) \
  || fail "GET /$PRIVATE/repo.git upload-pack" "no answer"
code=$(printf %s "$got" | sed -n '1s/[^ ]* \([0-9][0-9]*\).*/\1/p')
[ "$code" = 401 ] || fail "GET /$PRIVATE/repo.git upload-pack (anonymous)" \
  "HTTP $code — a private board is not world-clonable"
pass "GET /$PRIVATE/repo.git upload-pack (anonymous)" "HTTP 401"

# ── (h) a LANDED card still renders its diff ─────────────────────────────────
# Reported 2026-08-31 against the pull mirror, and the reason this chapter
# exists: `tk-dfaff7`'s branch was pruned on the forge when its chapter landed,
# so the board — whose git was a --mirror of the forge — lost the diff of work
# that is intact in the trunk. The host holds the history now and refuses ref
# deletions, so this URL must answer for the life of the board.
head_ln "a card whose branch was pruned on the forge"
body=$($C "$BASE/$BOARD/api/git/commit/$LANDED") || fail "GET git/commit/$LANDED" "no answer"
case $body in
  *'"patch"'*) pass "GET /$BOARD/api/git/commit/$LANDED" \
    "a diff ($(printf %s "$body" | wc -c | tr -d ' ') bytes)" ;;
  *) fail "GET git/commit/$LANDED" "no diff: $(printf %s "$body" | head -c 300)" ;;
esac

printf '\nall green — %s, board %s\n' "$HOST" "$BOARD"
