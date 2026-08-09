/* The seam every smoke section is written against — `monitor/panels.ts`'s move,
 * applied to the harness.
 *
 * WHY THIS FILE EXISTS. The smoke list used to be ONE file that every UI card
 * APPENDED a section to, and in two days that cost four real incidents: a
 * 293-line conflict block between two cards that both appended at the tail
 * (tk-a1b7f2 × tk-63f919); the same merge auto-STACKING two `const reviewed`
 * declarations in one scope, caught only by tsc — the "clean" merge was the
 * dangerous one; two workers each numbering their section §9; and every
 * `main.tsx §N` cross-reference in the docs dangling, because the numbers were
 * append-order state. A section is now a FILE, named by what it pins — a slug,
 * never a number — and two cards adding coverage in parallel touch zero shared
 * lines.
 *
 * A section declares nothing but `run`. It gets the fixture, the `check` it
 * reports through, and the plumbing more than one section needs; everything
 * else it builds itself, in its own scope, which is what makes the collided
 * `const`s (`reviewed`, `handedBoard`) impossible by construction. */
import type { rows } from "../../src/pages/Worktrees";
import type { BoardPayload, CardPayload, GitDiff } from "../../src/types";

/** The fixture, as `tests/test_ui.py` writes it. */
export interface Fixture {
  board: BoardPayload;
  card: CardPayload;
  /** substrings the Monitor + Board markup must contain */
  expect_board: string[];
  /** substrings the dossier must contain */
  expect: string[];
  /** the same `board` verb, focused on a chapter that has LANDED */
  board_landed: BoardPayload;
  /** substrings that chapter must still be able to say for itself */
  expect_landed: string[];
  /** the /git door's own answer over a real clone, and its own no-repo refusal */
  git: { compare: GitDiff; no_repo: string; stale: string };
  /** two cards the board actually CLOSED: the reviewed one, then the `no_code`
   *  one. Their histories are where `submitted`, `reviewed` and `status` bodies
   *  come from — see `sections/thread-closing-note.tsx`. */
  closed: CardPayload[];
}

/** How a section reports: one line per claim, a failure carrying its own detail. */
export type Check = (name: string, ok: boolean, detail?: string) => void;

/** The plumbing. Everything here is used by MORE THAN ONE section — that is the
 *  only reason anything is in it. A helper one section needs stays in that
 *  section's file, where a parallel card can never collide with it. */
export interface Harness {
  /** the clock the whole run shares, so two sections cannot disagree by a second */
  now: number;
  /** cards the sections' `openCard` handlers were asked to open */
  opened: string[];
  /** the substring of `markup` between two testids — the assertions' scalpel */
  slice: (markup: string, from: string, to: string) => string;
  /** a repo the board can point at, used by the forge links AND by the diff */
  REPO: { host: string; slug: string; url: string };
  /** the worktree index the board derives, read by two views */
  named: ReturnType<typeof rows>;
}

/** What `sections/index.generated.ts` collects, in filename order. */
export type Section = (fixture: Fixture, check: Check, h: Harness) => Promise<void>;

/** The panes Monitor draws. Nova's own eight — nothing merged, nothing dropped
 *  for lack of a verb (`components/monitor/panels.ts`) — plus `pane-swarm`,
 *  which is this chapter's and is NOT one of Nova's: the topology pane is the
 *  ninth section, at the foot of the left column. */
export const PANES = [
  "pane-leases",
  "pane-throughput",
  "pane-health",
  "pane-dag",
  "pane-files",
  "pane-chapter",
  "pane-mentions",
  "pane-events",
  "pane-swarm",
];
