#!/bin/sh
# The live smoke for a taskops board HOST. Read-only, no credential, no state:
# every request below is a GET or a `board` read, so it is safe to run against
# production at any time, including from a laptop that never joined the board.
#
#   sh smoke.sh                                  # the author's host, defaults below
#   sh smoke.sh <host> <public-board> <private-board> <card-branch>
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

# ── (d) a card branch renders a diff from the forge mirror ────────────────────
# The hosted window's whole point: a reader with NO clone. Before the mirror,
# every diff fell through the UI's cascade to a forge link — a blank presented
# as the window. A tk-* branch on purpose: `master` is fetched by any clone, and
# the failure this catches is a mirror whose on-demand fetch never ran, which
# only shows on a ref the mirror did not have at clone time.
head_ln "a card branch diffs from the mirror"
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

printf '\nall green — %s, board %s\n' "$HOST" "$BOARD"
