/* Where the board points at the code — every link the dashboard draws to a
 * forge, the +/− that rides beside a commit, and THE CASCADE that decides which
 * of those a reader actually gets.
 *
 * ── The cascade, declared once ─────────────────────────────────────────────
 *
 *     numstat (already on the event) → /git patch → forge link → one sentence
 *
 * Four steps, one function (`cascade()`), one module. It lives HERE and not in a
 * `diff.ts` of its own because steps three and four are already this file's
 * subject — the slug, the templates, the "no slug, no anchor" rule — and a
 * second module owning "what to show when there is no patch" would be two places
 * to read before you know what the pane does. `Patch.tsx` DRAWS a step; it never
 * decides which one, and it holds no fallback of its own.
 *
 * ── Availability is discovered, never configured ───────────────────────────
 *
 * Whether the diff exists is a fact about the HOST, not about a card: `taskops
 * ui` sits in a repo and mounts /git; `taskops serve` sits in a boards directory
 * and answers /git from a per-board MIRROR of the declared forge — or refuses,
 * for a board with no forge (ARCHITECTURE.md §16, "The hosted window"). Either
 * way the client's move is the same. There is no setting to read and no probe
 * to run — the FIRST refusal whose words are `gitdoor.py::NO_REPO` flips it for
 * the session, and from then on nothing asks again.
 *
 * So the memory is a module-level `let`, and the lifetime is the argument: one
 * page load talks to exactly one host, which is precisely the lifetime of this
 * module. React state would re-discover per component (every commit row probing
 * the same 404); a context would be a provider, a hook and a test double for one
 * boolean.
 *
 * It is NOT the v1 sin this client was rebuilt away from. That was `api.ts`
 * reading `document`, `location` and `localStorage` AT MODULE SCOPE, so
 * importing the file needed three globals faked before its first line. Nothing
 * here is read at import: the value is a literal `true`, and only an answer
 * already received can change it. Under `react-dom/server` the harness imports
 * this module, renders, and the flag never moves.
 *
 * ── The switch ─────────────────────────────────────────────────────────────
 *
 * `BoardPayload.repo` (`verbs/project.py::_value`, via `pulse.py::run`) is the
 * whole feature. It is absent for TWO real reasons — a board one version behind
 * never recorded it, and a repo with no `origin` never will — and both mean the
 * same thing to a reader: draw plain text. So every builder here returns
 * `string | null`, and every caller renders an anchor or renders exactly what it
 * rendered before. There is no third state, no disabled anchor and no `href=""`:
 * NO SLUG → NO LINKS, and nothing else changes (the chapter's third rule).
 *
 * ── Why `host` is a VALUE and not a second code path ───────────────────────
 *
 * `gitwork/remote.py` stores `{host, slug, url}` and says why in its own words:
 * a link is not `f"{url}/commit/{sha}"` everywhere — GitHub's is exactly that,
 * GitLab's is `/-/commit/{sha}`. The host is the key that picks a TEMPLATE, so
 * a non-GitHub forge is a row in `BY_HOST` below, never an `if` in a renderer.
 * Undoing that here — parsing `url`, or branching on "is this github" at a call
 * site — would throw away the only reason the field is stored.
 *
 * The fallback for an unknown host is the GitHub shape rather than nothing:
 * gitea, forgejo and GitHub Enterprise all serve `/commit/<sha>` and
 * `/compare/<base>...<head>` at their own domain, so a self-hosted forge works
 * by default and GitLab — the one that differs — is named.
 *
 * ── The trunk the UI does not know ─────────────────────────────────────────
 *
 * A milestone compares against the TRUNK, and the trunk is not on the board:
 * `gitwork/trees.py::base_ref` resolves it from the repo (origin/main, master,
 * …) and no verb sends it. Guessing "main" on a screen would be the UI asserting
 * a git fact it cannot know — exactly what the chapter's first rule forbids. So
 * `compare()` takes an OPTIONAL base and omits it when there is none: on the
 * GitHub shape `/compare/<head>` is a real page whose base is the repository's
 * own default branch, which is the trunk, decided by the side that knows.
 */

import { useEffect, useState } from "react";

import type { GitDiff, GitFile } from "./types";

/** The stored shape, structurally — `BoardPayload.repo` assigns to this. It is
 *  declared here rather than imported so this module is the seam and not a
 *  second consumer of one; `types.ts` keeps the payload's own annotation. */
export interface Repo {
  host: string;
  slug: string;
  url: string;
}

/** What a forge calls its two pages. Paths only — the base is `repo.url`. */
interface Templates {
  commit: (sha: string) => string;
  compare: (head: string, base: string) => string;
}

const GITHUB: Templates = {
  commit: (sha) => `commit/${sha}`,
  compare: (head, base) => (base ? `compare/${base}...${head}` : `compare/${head}`),
};

const GITLAB: Templates = {
  commit: (sha) => `-/commit/${sha}`,
  compare: (head, base) => (base ? `-/compare/${base}...${head}` : `-/compare/${head}`),
};

const BY_HOST: Record<string, Templates> = {
  "github.com": GITHUB,
  "gitlab.com": GITLAB,
};

function templates(host: string): Templates {
  return BY_HOST[host] ?? (host.includes("gitlab") ? GITLAB : GITHUB);
}

/** A repo with an actual slug, or null. Both `undefined` (an older board) and
 *  `null` (a repo with no origin) arrive here and say the same thing. */
function web(repo: Repo | null | undefined): Repo | null {
  return repo && repo.slug ? repo : null;
}

/** Whether this board can link at all — the one boolean a LAYOUT may branch on.
 *
 *  A renderer that only draws an anchor asks `commitUrl`/`compareUrl` for a
 *  string and needs nothing else. A renderer that must RESERVE room for one
 *  (the Worktrees table's link column) has to know before it has a row, and
 *  this is that question asked once instead of five times. */
export function hasRepo(repo: Repo | null | undefined): boolean {
  return web(repo) !== null;
}

/** `https://<host>/<slug>/commit/<sha>` — or null, and then no anchor. */
export function commitUrl(repo: Repo | null | undefined, sha: string): string | null {
  const found = web(repo);
  if (found === null || !sha) return null;
  return `${found.url}/${templates(found.host).commit(sha)}`;
}

/** The PR-diff view with no PR: `compare/<base>...<head>`.
 *
 *  `base` is optional on purpose — see the header. A card compares against its
 *  milestone branch (both are on `CardPayload`); a milestone against the trunk,
 *  which only the forge knows. */
export function compareUrl(
  repo: Repo | null | undefined,
  head: string,
  base = "",
): string | null {
  const found = web(repo);
  if (found === null || !head) return null;
  return `${found.url}/${templates(found.host).compare(head, base)}`;
}

/** An outward anchor. New tab, `rel="noopener"`, and that is the only reason
 *  this exists as a component: one place gets it right rather than five. */
export function Ext({
  href,
  title,
  style,
  children,
}: {
  href: string;
  title?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <a
      data-testid="ext"
      href={href}
      title={title}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: "inherit", textDecoration: "none", ...style }}
    >
      {children}
    </a>
  );
}

/* ── the +/− ──────────────────────────────────────────────────────────────── */

/** `{path: [added, deleted] | null}`, as `gitwork/bind.py::parse_numstat` writes
 *  it. `null` is a BINARY file — git prints `-` there, and "cannot be counted"
 *  is not "nothing changed". */
export type Counts = Record<string, [number, number] | null>;

/** Read a numstat off an untyped event body.
 *
 *  `Event.body` is `Record<string, unknown>` and a `commit` event is where the
 *  thread's numstat comes from, so the shape is CHECKED rather than asserted:
 *  a board that ever wrote a different one draws no figure instead of `NaN`. */
export function readNumstat(value: unknown): Counts | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const counts: Counts = {};
  for (const [path, entry] of Object.entries(value as Record<string, unknown>)) {
    if (entry === null) {
      counts[path] = null;
      continue;
    }
    if (!Array.isArray(entry) || entry.length < 2) return null;
    const [added, deleted] = entry as unknown[];
    if (typeof added !== "number" || typeof deleted !== "number") return null;
    counts[path] = [added, deleted];
  }
  return Object.keys(counts).length > 0 ? counts : null;
}

export interface Totals {
  added: number;
  deleted: number;
  /** files git could not count — binaries. NEVER folded into a zero. */
  binary: number;
  files: number;
}

export function totals(counts: Counts): Totals {
  let added = 0;
  let deleted = 0;
  let binary = 0;
  for (const entry of Object.values(counts)) {
    if (entry === null) binary += 1;
    else {
      added += entry[0];
      deleted += entry[1];
    }
  }
  return { added, deleted, binary, files: Object.keys(counts).length };
}

/** `+12 −3 · 1 binary`, beside a commit subject.
 *
 *  COLOUR. Added and deleted are a STATUS pair, not two categorical series, so
 *  they wear the design system's reserved good/critical tokens (`--ok`,
 *  `--danger` — `TONE_FG` in CardTile.tsx) and no hue of their own; the dataviz
 *  rule that status colours are reserved cuts both ways, and inventing a green
 *  here would be a sixth palette entry in a system that has five. Neither figure
 *  is colour-ALONE either: the `+` and the `−` carry the meaning with the CSS
 *  off, which is the same rule stated for legends.
 *
 *  A binary file is drawn in neutral ink and counted as FILES, never as `+0 −0`:
 *  the payload's `null` means git could not count it. Saying "0" there would be
 *  the UI making a claim the board did not. */
export function Numstat({ counts }: { counts: Counts | null }): React.JSX.Element | null {
  if (counts === null) return null;
  const sum = totals(counts);
  const title = `${sum.files} file${sum.files === 1 ? "" : "s"}`;
  return (
    <span
      className="mono"
      data-testid="numstat"
      title={title}
      style={{ fontSize: "11px", whiteSpace: "nowrap", display: "inline-flex", gap: "6px" }}
    >
      {sum.added > 0 || sum.binary < sum.files ? (
        <span style={{ color: "var(--ok)" }}>+{sum.added}</span>
      ) : null}
      {sum.deleted > 0 || sum.binary < sum.files ? (
        <span style={{ color: "var(--danger)" }}>−{sum.deleted}</span>
      ) : null}
      {sum.binary > 0 ? (
        <span data-testid="numstat-binary" style={{ color: "var(--text-3)" }}>
          {sum.binary} binary
        </span>
      ) : null}
    </span>
  );
}

/* ── the cascade: numstat → /git → forge → a sentence ─────────────────────── */

/** What to ask the door for. A commit diffs against its FIRST parent and a
 *  compare is merge-base(base, head) → head; both spellings are decided in
 *  `gitwork/diff.py` and neither is expressible here, which is the point. */
export type GitTarget =
  | { kind: "commit"; ref: string }
  | { kind: "compare"; base: string; head: string };

/** The route under the board's base — `http/server.py::_git` strips `git/` and
 *  `http/gitdoor.py::answer` reads the rest.
 *
 *  Every ref is percent-encoded because a branch name contains `/`
 *  (`ms/the-chapter`) and the door `unquote`s what it gets; `...` is the
 *  separator and stays literal, since it is the route's grammar and not part of
 *  either ref. */
export function gitRoute(target: GitTarget, path?: string): string {
  const tail =
    target.kind === "commit"
      ? `commit/${encodeURIComponent(target.ref)}`
      : `compare/${encodeURIComponent(target.base)}...${encodeURIComponent(target.head)}`;
  return `git/${tail}` + (path ? `?path=${encodeURIComponent(path)}` : "");
}

/** The door's THIRD question: one committed file's bytes at a rev.
 *
 *  `GET <board>/git/file/<rev>?path=<repo-relative>` — `http/gitdoor.py::_file`.
 *
 *  It is a function of its own and NOT a third member of `GitTarget`, which was
 *  the first thing tried. `GitTarget` is the cascade's vocabulary: every value
 *  of it has a forge page (`gitForge` switches on it) and a patch to draw. A
 *  file at a rev has neither — there is no `…/blob/<sha>/<path>` step in this
 *  cascade and no diff at the end of it — so adding a `kind: "file"` would have
 *  made `gitForge`'s `else` silently answer `compare` for it, and every consumer
 *  of `DiffStep` would need a branch that can never fire. Different question,
 *  different route builder, same door.
 *
 *  `rev` and `path` are both percent-encoded: a rev may be a branch name with a
 *  `/` in it, and a path always has several. The door `unquote`s both. */
export function fileRoute(rev: string, path: string): string {
  return `git/file/${encodeURIComponent(rev)}?path=${encodeURIComponent(path)}`;
}

/** The card's HEAD for a diff — the recorded sha when there is one, else the
 *  branch name.
 *
 *  ── Why a sha at all, when the host keeps every branch forever ────────────
 *
 *  Because "forever" started on a date. The host holds the board's own git and
 *  prunes nothing (ARCHITECTURE §16, "The host becomes the remote"), so a
 *  branch name is a durable handle again — for every card pushed since. A card
 *  worked BEFORE that, whose `tk-*` branch was pruned on the forge when its
 *  chapter landed and never reached this host, has no branch anywhere; its
 *  commits are in the trunk that was pushed, and a sha is the only name that
 *  still finds them. That is the reported failure (tk-dfaff7), and it is
 *  permanent history: no later push grows the branch back.
 *
 *  ── Why prefer the sha even when the branch exists ────────────────────────
 *
 *  A sha names the same bytes forever; a branch names whatever its tip is now.
 *  For a card that is still being worked those are the same thing, and for a
 *  card that CLOSED the sha is more honest — the diff a reader opens on a
 *  landed card is the work that landed, not wherever a reused branch has since
 *  moved to. And the sha is already on the payload (`CardPayload.commits`,
 *  `verbs/_context.py::dossier` — a `commit` event's body per card, oldest
 *  first, so the LAST is the newest): nothing is invented here and no event was
 *  added for this.
 *
 *  It is the HEAD only. The base stays the milestone's branch, which the board
 *  records as a name and nothing else — there is no recorded sha for "where the
 *  chapter was", and a merge-base against the chapter's tip is what the compare
 *  wants anyway. */
export function cardHead(
  commits: readonly { sha?: unknown }[] | null | undefined,
  branch: string,
): string {
  const last = commits && commits.length > 0 ? commits[commits.length - 1] : null;
  const sha = last && typeof last.sha === "string" ? last.sha : "";
  return sha || branch;
}

/** The forge page for the same target — step THREE, in the same vocabulary as
 *  step two, so a caller never has to translate between them. */
export function gitForge(repo: Repo | null | undefined, target: GitTarget): string | null {
  return target.kind === "commit"
    ? commitUrl(repo, target.ref)
    : compareUrl(repo, target.head, target.base);
}

/** The words `http/gitdoor.py::NO_REPO` opens with. Matching a PHRASE and not a
 *  code is deliberate: the code is `not_found`, which an unknown ref also
 *  answers, and the two mean opposite things — one says "never ask this host
 *  again", the other says "ask again for a different ref". The seam wrote those
 *  words for this reader (tk-d50e0a's close note says so). */
const NO_REPO = "serves boards, not a repository";

/** Discovered, once, for the session. See the header. */
let hostHasClone = true;

export function gitAvailable(): boolean {
  return hostHasClone;
}

/** Called with a refusal's message. Only the no-repo words move it, and it only
 *  ever moves one way: a host does not grow a clone mid-session. */
export function noteGitRefusal(message: string): void {
  if (message.includes(NO_REPO)) hostHasClone = false;
}

/** Tests only — the flag is module state and a second case must start clean. */
export function resetGitAvailability(): void {
  hostHasClone = true;
}

/** The four steps, as values. `loading` and `none` are drawn too: a pane that
 *  shows nothing while it waits, or nothing when it failed, is the "empty pane
 *  pretending" the chapter's fifth rule forbids. */
export type DiffStep =
  | { step: "loading" }
  | { step: "patch"; diff: GitDiff; forge: string | null }
  | { step: "forge"; href: string; why: string }
  | { step: "none"; why: string };

/** Why there is no patch, in the reader's terms.
 *
 *  A refusal the door actually sent WINS, verbatim. Two of them say things this
 *  side could not know and must not paraphrase: "this host serves boards, not a
 *  repository" (`gitdoor.py::NO_REPO`) and "that branch is not in your clone yet
 *  — `git fetch origin tk-…` brings it" (`gitdoor.py::STALE`). The second is the
 *  everyday one on a SHARED board: the board travels over HTTP and the code
 *  travels by git, so a card somebody else closed an hour ago has a branch this
 *  clone has never seen. Neither is an error — one is this host being what it
 *  is, the other is this disk being where it is — and the honest, actionable
 *  sentence is the server's, which is why nothing here rewrites it.
 *
 *  Only when there is no refusal to quote (nothing was asked, or the flag
 *  already learned this host has no clone in an earlier pane) does this side
 *  speak for itself. */
function why(refusal?: string | null): string {
  if (refusal) return refusal;
  return hostHasClone
    ? "this host could not read that diff"
    : "this host has neither a checkout nor a mirror for this board, so there is no repository here to read a diff from";
}

/** THE CASCADE. One function, four returns, in order. Everything that draws a
 *  diff anywhere in this dashboard comes through here. */
export function cascade(
  repo: Repo | null | undefined,
  target: GitTarget,
  state: { diff: GitDiff | null; loading: boolean; refusal?: string | null },
): DiffStep {
  const forge = gitForge(repo, target);
  const reason = why(state.refusal);
  if (state.loading) return { step: "loading" };
  // 2 · the real patch. `truncated` carries the forge link with it rather than
  //     replacing it: a cut patch is still the best thing on screen.
  if (state.diff !== null) return { step: "patch", diff: state.diff, forge };
  // 3 · the forge, when this board has a slug at all.
  if (forge !== null) return { step: "forge", href: forge, why: reason };
  // 4 · the sentence. No anchor, no pane, no apology.
  return { step: "none", why: `${reason}, and this board has no remote to link out to` };
}

/** What `useGitDiff` needs of a client — declared structurally, like `Repo`
 *  above, so this module stays a leaf that `client.ts` happens to satisfy. */
export interface GitReader {
  git<T>(route: string): Promise<T>;
}

/** Ask the door for one range, lazily.
 *
 *  `on` is the laziness: a commit row passes `false` until it is expanded, and
 *  nothing is fetched for a patch nobody opened. It never fires when the session
 *  already learned this host has no clone — that is the "no per-render probing"
 *  half of the rule, and the reason the flag is checked HERE rather than in each
 *  component.
 *
 *  A refusal is not surfaced as an error: it teaches the flag, is KEPT as words
 *  for `cascade()` to quote, and then resolves to `diff: null`, which IS the
 *  cascade's third step. The pane says the honest sentence; nothing throws into
 *  a render. Keeping the message is what lets "not in your clone yet — git fetch
 *  origin tk-… brings it" reach the reader: only the door knows which ref was
 *  missing, and a sentence composed on this side would have to guess. */
export function useGitDiff(
  reader: GitReader | null | undefined,
  target: GitTarget,
  on: boolean,
  path?: string,
): { diff: GitDiff | null; loading: boolean; refusal: string | null } {
  const [diff, setDiff] = useState<GitDiff | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const route = gitRoute(target, path);

  useEffect(() => {
    // Per EFFECT, not a ref shared across them: an answer that lands after the
    // route changed is answering a question nobody is asking any more, and
    // writing it would show one ref's patch under another's heading.
    let mine = true;
    if (!reader || !on || !gitAvailable()) {
      setDiff(null);
      setRefusal(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    reader
      .git<GitDiff>(route)
      .then((answer) => {
        if (mine) {
          setDiff(answer);
          setRefusal(null);
        }
      })
      .catch((failure: unknown) => {
        const said = failure instanceof Error ? failure.message : "";
        noteGitRefusal(said);
        if (mine) {
          setDiff(null);
          setRefusal(said || null);
        }
      })
      .finally(() => {
        if (mine) setLoading(false);
      });
    return () => {
      mine = false;
    };
  }, [reader, route, on]);

  return { diff, loading, refusal };
}

/** Ask the door for ONE report's bytes — `useGitDiff`'s sibling, same rules.
 *
 *  Per OPEN, not per board: a report is fetched when a reader opens that row and
 *  never with the board payload. `null` is the closed state and clears
 *  everything, so backing out of a report cannot leave the previous one's text
 *  on screen under the next one's title — the `mine` latch is the same
 *  stale-answer guard, for the same reason (an answer that lands after the
 *  selection moved is answering a question nobody is asking).
 *
 *  It shares `gitAvailable()`/`noteGitRefusal()` with the diff hook rather than
 *  keeping a flag of its own: whether this HOST has a clone is one fact about
 *  one page load, and a second memory of it would probe a `taskops serve` host
 *  the first hook already learned about. A refusal is kept as WORDS, never
 *  thrown into a render — only the door knows which rev is missing from this
 *  clone, and it names the `git fetch` that brings it. */
export function useGitFile(
  reader: GitReader | null | undefined,
  at: { sha: string; path: string } | null,
): { file: GitFile | null; loading: boolean; refusal: string | null } {
  const [file, setFile] = useState<GitFile | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const route = at ? fileRoute(at.sha, at.path) : "";

  useEffect(() => {
    let mine = true;
    if (!reader || !route || !gitAvailable()) {
      setFile(null);
      setRefusal(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setFile(null); // never the previous report's bytes under this one's title
    reader
      .git<GitFile>(route)
      .then((answer) => {
        if (mine) {
          setFile(answer);
          setRefusal(null);
        }
      })
      .catch((failure: unknown) => {
        const said = failure instanceof Error ? failure.message : "";
        noteGitRefusal(said);
        if (mine) {
          setFile(null);
          setRefusal(said || null);
        }
      })
      .finally(() => {
        if (mine) setLoading(false);
      });
    return () => {
      mine = false;
    };
  }, [reader, route]);

  return { file, loading, refusal };
}
