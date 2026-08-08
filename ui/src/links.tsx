/* Where the board points at the code — every link the dashboard draws to a
 * forge, and the +/− that rides beside a commit.
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
