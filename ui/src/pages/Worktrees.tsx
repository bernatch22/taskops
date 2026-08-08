/* The third view — Nova's WORKTREES section, as an INDEX OF PULL REQUESTS.
 *
 * Two columns, 50/50, and under them three note cards. It answers the one
 * question the kanban cannot: not "what state is this card in" but "what is on
 * disk right now, who is carrying it, and has it reached the trunk". The left
 * column is what is still in flight, the right one is what is finished — and
 * that is the whole fold, because a worktree only ever means one of those two
 * things to the reader looking for it.
 *
 * It used to be a five-column TABLE — branch, card, directory, commits, status —
 * and clicking a row opened the card Dossier. Both are gone. A tree is a pull
 * request, so a row is a tile carrying the four facts you choose one by (branch,
 * title, author, chapter) and its ONLY action is opening ITS diff, full width,
 * in this view's own second surface. The directory is `TREE_DIR + id` by
 * construction and the commit count has never had a source (`panels.ts`) — two
 * columns' worth of width spent on a string nobody reads and an em dash.
 *
 * DERIVED FROM `board.groups`, exactly like `pages/Board.tsx::columns` — same
 * mechanism, different fold. There is no second read, no client-side status
 * computation and no worktree verb: `pulse.py::run` already grouped every card
 * by the move it needs, and this file only says which block and which pill each
 * group gets. Inside a block the groups keep `GROUP_ORDER` (`types.ts`), which
 * is the order the board itself builds them in and therefore the order to ACT
 * in — a view that reorders them is contradicting the board.
 *
 *     ready        take                          neutral
 *     in progress  doing · reviewing             accent
 *                  stalled                       danger — an owner, nobody running it
 *     blocked      blocked                       danger, soft
 *     done         merge   (NOT in the trunk)    warn — the group the board waits on
 *     merged       done    (closed AND in it)    ok
 *
 * `stalled` shares the "in progress" state and NOT its tone, on the Board's own
 * rule: a stalled card is in flight — it has an owner — and nobody is running
 * it. Drawn identically to a running one it reads as progress; it is the
 * opposite.
 *
 * TWO SUB-BLOCKS PER COLUMN, and not three. Each column splits on the ONE fact
 * its pills do not already carry:
 *   · left — somebody is on this tree, or nobody is. `working` is every group
 *     with an owner (`doing`, `reviewing`, `stalled`, `review`, `changes`);
 *     `waiting` is every group without one (`take`, `blocked`). That is what
 *     decides whether you may pick it up, and it is not readable off a pill.
 *   · right — it is finished and NOT in the trunk, or it is in it. `merge` leads
 *     because it is the group the board is WAITING for.
 * A third block would have to split `blocked` off `take`, or `stalled` off
 * `doing` — and both of those distinctions are already the row's own pill and
 * tone, in colour, on every row. A heading that repeats the pill is one more
 * thing to read and no more information. An empty sub-block is not drawn at all
 * (a heading over nothing is a fact about the layout, not about the board); an
 * empty COLUMN says so in a sentence.
 *
 * Read-only, absolutely: a row is a button, and what it opens is THIS view's own
 * full-width diff page — not the card Dossier. That was the bug: clicking a tree
 * landed the reader in a 900px drawer about the CARD, with the diff crammed into
 * a pane inside it. The selection is one `useState` here; when it is set, the
 * index is replaced (an early return), and `onBack` clears it. There is no
 * router, no history entry and no modal. `onOpen` is gone from the props
 * deliberately: the drawer is not reachable from this view at all, so it cannot
 * come back by accident.
 *
 * `LIST_CAP` deliberately does NOT apply — this is a full-height view like the
 * Board, not a pane inside a grid, so the columns grow and the page scrolls. */
import { useState } from "react";
import { PaneButton } from "../components/monitor/Pane";
import {
  TREE_DIR,
  type ThreadProps,
  type Tone,
  type WorktreeRow,
  type WorktreesProps,
} from "../components/monitor/panels";
/* The second surface, in its own file. Re-exported here because this page is
 * what renders it and the smoke harness reaches for it through this module. */
import { WorktreeDiff } from "./WorktreeDiff";
import { TONE_BG, TONE_FG } from "../components/board/CardTile";
import { ownerOf, shortActor } from "../format";
import { Ext, compareUrl } from "../links";
import type { BoardGroups, BoardRow, GroupName, Milestone } from "../types";

export type { WorktreesProps };
export { WorktreeDiff };

/** WHO carries a tree, from the row the index already has.
 *
 *  `holder` first, then `assignee`, and that order is the fact itself: `holder`
 *  is the LIVE lease — the process that has the directory open right now —
 *  while `assignee` is only who it was handed to, which is all a stalled or
 *  handed-in row still has (`types.ts::BoardRow`). Taking the assignee when a
 *  holder exists would name a hand-over that a running worker has already
 *  superseded.
 *
 *  Two values out of one string, because they answer two different questions:
 *  `ownerOf` folds `agent:berna/w1` → `dev:berna` (the ownership
 *  `http/auth.py::authorize` enforces on the wire) and that is WHO TO TALK TO;
 *  `shortActor` gives `w1`, WHICH PROCESS holds the tree. An actor that is a
 *  dev already yields no worker — see `WorktreeRow.dev`. */
function owner(row: BoardRow): { dev: string | null; worker: string | null } {
  const actor = row.holder ?? (row.assignee || "");
  if (!actor) return { dev: null, worker: null };
  return {
    dev: ownerOf(actor),
    worker: actor.startsWith("agent:") ? shortActor(actor) : null,
  };
}

/** The chapter a row belongs to, RESOLVED — id from the row, words from the
 *  payload's own `milestones` list, joined here and nowhere else.
 *
 *  Two ways to get nothing, and neither one prints the id: a board one version
 *  behind sends no `milestone` on the row at all, and a chapter that has aged
 *  past `milestones`' cap is an id this payload cannot name. `ms-9f21` on screen
 *  is not information, it is the join failing out loud. */
function chapter(row: BoardRow, titles: Map<string, string>): WorktreeRow["milestone"] {
  const id = row.milestone ?? "";
  const title = id ? titles.get(id) : undefined;
  return id && title ? { id, title } : null;
}

function treeRow(
  row: BoardRow,
  status: string,
  tone: Tone,
  titles: Map<string, string>,
): WorktreeRow {
  return {
    id: row.id,
    title: row.title,
    milestone: chapter(row, titles),
    ...owner(row),
    // Construction, not a fetch: `gitwork/trees.py` pins every card's worktree
    // to `.taskops/trees/<id>` for life. There is no directory on the wire, and
    // no row draws it any more — it is kept because it is the tree's identity
    // on disk and `WorktreeDiffProps.row` is this same shape.
    dir: TREE_DIR + row.id,
    // No source on the row — see the field's own note in panels.ts.
    commits: null,
    status,
    tone,
  };
}

/** The pill each group wears — the tone table above, as code, ONCE.
 *
 *  `review` and `changes` are not among the five states Nova's pill draws, and
 *  they are not dropped either: a handed-in card still inhabits its worktree and
 *  its branch still exists, so it is IN PROGRESS here — that is the fact this
 *  view reports. The Board page is where their three review sub-states are told
 *  apart; here they are one directory on disk. `mentions` is the one group with
 *  no entry: it is not a card row. */
const PILL: Record<Exclude<GroupName, "mentions">, readonly [string, Tone]> = {
  merge: ["done, not merged", "warn"],
  review: ["in progress", "accent"],
  changes: ["in progress", "accent"],
  stalled: ["in progress · stalled", "danger"],
  take: ["ready", "neutral"],
  doing: ["in progress", "accent"],
  reviewing: ["in progress", "accent"],
  blocked: ["blocked", "danger"],
  done: ["merged", "ok"],
};

type Block = { title: string; groups: readonly (keyof typeof PILL)[] };

/** What a column with nothing in it says, per column — the sentence, and under
 *  it the ONE call that would fill it.
 *
 *  BOTH columns get it and not only the left: a chapter with nothing merged yet
 *  has the mirror-image problem, and that is the far more common state at the
 *  START of a chapter — exactly when somebody is watching this screen. */
const EMPTY: Record<string, { said: string; move: string }> = {
  "In progress": {
    said: "No card is open on this chapter, so no worktree is pinned to one. A directory appears here the moment a card exists, and it keeps it.",
    move: "taskops_assign hands a card to a worker",
  },
  Merged: {
    said: "Nothing has been integrated yet. A card lands here the moment taskops_merge task= takes it into the chapter.",
    move: "taskops_merge task= is the orchestrator's call",
  },
};

/** The two columns and their sub-blocks. Every group list is in `GROUP_ORDER`,
 *  so the rows inside a block arrive in the order the board builds them. */
const COLUMNS: readonly { title: string; blocks: readonly Block[] }[] = [
  {
    title: "In progress",
    blocks: [
      { title: "working", groups: ["review", "changes", "stalled", "doing", "reviewing"] },
      { title: "waiting", groups: ["take", "blocked"] },
    ],
  },
  {
    title: "Merged",
    blocks: [
      { title: "done, not merged", groups: ["merge"] },
      { title: "merged", groups: ["done"] },
    ],
  },
];

function fold(
  groups: BoardGroups,
  block: Block,
  titles: Map<string, string>,
): WorktreeRow[] {
  return block.groups.flatMap((name) => {
    const [status, tone] = PILL[name];
    // `?? []`: the `done` group postdates the other nine (types.ts), so a board
    // older than a1d1005 sends no such key and that block simply has no rows to
    // draw — which is the truth about what that payload can say.
    return (groups[name] ?? []).map((r) => treeRow(r, status, tone, titles));
  });
}

/** `milestones` is OPTIONAL and defaults to none: a caller that has not been
 *  taught to pass the chapters gets exactly the index it got before, with every
 *  row's chapter `null`.
 *
 *  Exported flat, every tree in one array, because that is what a caller asking
 *  "which trees exist" wants; the screen asks the same question per block. */
export function rows(
  groups: WorktreesProps["groups"],
  milestones: readonly Milestone[] = [],
): WorktreeRow[] {
  const titles = new Map(milestones.map((m) => [m.id, m.title]));
  return COLUMNS.flatMap((c) => c.blocks.flatMap((b) => fold(groups, b, titles)));
}

/** The three note cards — the design's `treeNotes`.
 *
 *  Every sentence is LIFTED from this repo's own `CLAUDE.md` (idea 2, "Branches
 *  are inhabited, not switched"). None of it is written for this page: the
 *  screen states the rule the board already enforces, in the words it is already
 *  enforced in, so the two cannot drift into saying different things. */
const NOTES: readonly { title: string; body: string }[] = [
  {
    title: "Branches are inhabited, not switched",
    body: "git switch appears nowhere. Each branch is pinned to a directory for life; “changing branch” is cd.",
  },
  {
    title: "A third lock nobody has to remember",
    body: "Git itself refuses the same branch in two worktrees — one worker each, one worktree each.",
  },
  {
    title: "A card merges into its chapter, never main",
    body: "taskops_merge task= takes no target: merging a CARD to main cannot be expressed. A finished milestone lands with taskops_merge milestone= — the human’s explicit call.",
  },
];

/* ── the design's own geometry, transcribed ───────────────────────────────── */

const page: React.CSSProperties = {
  height: "100%",
  overflowY: "auto",
  padding: "0 24px 26px",
};

const head: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  marginBottom: "14px",
};

/** The column SHELL. `display: flex` + `column` is not decoration: it is what
 *  lets the empty body claim `flex: 1` and centre itself inside whatever height
 *  the row hands this panel. */
const shell: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

/** 50/50 as drawn — but `auto-fit` with a 360px floor, so the pair collapses to
 *  ONE column on a narrow window instead of squeezing two unreadable ones.
 *
 *  `stretch`, NOT `start`. It used to be `start`, and on a landed chapter that
 *  read as a render that failed: `IN PROGRESS` collapsed to the height of one
 *  sentence while `MERGED` ran 900px down beside it. Two panels of wildly
 *  different height, one of them almost empty, is not a layout. Stretched, the
 *  two shells are one object and the empty one has space to fill — which is why
 *  the empty body below is centred rather than pinned to the top. When both
 *  columns carry rows nothing changes: a grid item that is as tall as the row
 *  stretches to exactly its own height. */
const split: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
  gap: "16px",
  alignItems: "stretch",
};

/** The empty body — centred in whatever the sibling column made this panel.
 *
 *  A dashed `--hair` field marks the area as INTENTIONALLY empty; the design
 *  system's own hairline, no invented hue, no illustration and no icon. The
 *  heading and its count above are untouched, so the two columns still rhyme. */
const emptyBody: React.CSSProperties = {
  flex: "1 1 auto",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: "8px",
  textAlign: "center",
  minHeight: "180px",
  margin: "0 20px 20px",
  padding: "26px 22px",
  border: "1px dashed var(--hair)",
  borderRadius: "12px",
  fontSize: "12.5px",
  color: "var(--text-3)",
  lineHeight: 1.6,
};

const columnHead: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: "12px",
  padding: "14px 20px",
  fontSize: "11.5px",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--text-3)",
};

const blockHead: React.CSSProperties = {
  padding: "9px 20px",
  borderTop: "1px solid var(--hair)",
  background: "var(--pane-2)",
  fontSize: "11px",
  color: "var(--text-3)",
};

const clip: React.CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const notes: React.CSSProperties = {
  marginTop: "18px",
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))",
  gap: "12px",
};

/** One tree: the four facts, and one action.
 *
 *  The whole tile is a `<button>` that selects the tree. The compare anchor is
 *  its SIBLING and not its child — an `<a>` inside a `<button>` is invalid HTML
 *  and unreachable by keyboard — and it sits in the row's own flex layout, so a
 *  board with no slug simply has one fewer flex item and nothing shifts. */
function Row({
  w,
  base,
  repo,
  onOpen,
}: {
  w: WorktreeRow;
  base: string;
  repo: WorktreesProps["repo"];
  onOpen: (id: string) => void;
}): React.JSX.Element {
  // The row's branch IS its card id (`WorktreeRow`); the base is the chapter's
  // integration branch, and with no chapter in focus the forge falls back to its
  // own default branch. No slug → `null` → no anchor at all, which is the
  // chapter's rule: a dead link is worse than none.
  const diff = compareUrl(repo, w.id, base);
  return (
    <div style={{ display: "flex", alignItems: "stretch" }}>
      <PaneButton
        cardId={w.id}
        onOpen={onOpen}
        testId="worktree-row"
        pad="13px 20px"
        style={{ flex: "1 1 auto", minWidth: 0, width: "auto" }}
      >
        <span
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "10px",
          }}
        >
          <span className="mono" style={{ fontSize: "12px", color: "var(--accent)" }}>
            {w.id}
          </span>
          <span
            data-status={w.status}
            style={{
              fontSize: "10.5px",
              padding: "3px 10px",
              borderRadius: "20px",
              background: TONE_BG[w.tone],
              color: TONE_FG[w.tone],
              whiteSpace: "nowrap",
            }}
          >
            {w.status}
          </span>
        </span>
        <span
          style={{
            ...clip,
            display: "block",
            marginTop: "6px",
            fontSize: "14px",
            fontWeight: 450,
            letterSpacing: "-0.025em",
          }}
        >
          {w.title}
        </span>
        {/* The dev is the sentence's subject and the worker its qualifier, so
            they are drawn in that weight: the person in `--text-2`, the process
            a shade back in `--text-3`. Same line, two colours — distinguishable
            without a column and without a label nobody needs twice per row. */}
        <span
          className="mono"
          data-testid="worktree-owner"
          style={{
            ...clip,
            display: "block",
            fontSize: "11px",
            marginTop: "5px",
            color: w.dev ? "var(--text-2)" : "var(--text-3)",
          }}
        >
          {w.dev ?? "nobody — free to take"}
          {w.worker ? <span style={{ color: "var(--text-3)" }}>{` · ${w.worker}`}</span> : null}
        </span>
        {/* The chapter, or NOTHING. An unresolvable id is not drawn at all
            (`chapter()`), so this line is absent rather than showing `ms-9f21`. */}
        {w.milestone ? (
          <span
            data-testid="worktree-chapter"
            style={{
              ...clip,
              display: "block",
              fontSize: "11.5px",
              marginTop: "4px",
              color: "var(--text-3)",
            }}
          >
            {`⌗ ${w.milestone.title}`}
          </span>
        ) : null}
      </PaneButton>
      {diff ? (
        <Ext
          href={diff}
          title={`${base || "the trunk"}...${w.id}`}
          style={{
            display: "flex",
            alignItems: "center",
            padding: "0 18px",
            borderTop: "1px solid var(--hair)",
            color: "var(--accent)",
            fontSize: "12px",
          }}
        >
          <span data-testid="worktree-compare">↗</span>
        </Ext>
      ) : null}
    </div>
  );
}

function Column({
  title,
  blocks,
  base,
  repo,
  onOpen,
}: {
  title: string;
  blocks: readonly { title: string; rows: WorktreeRow[] }[];
  base: string;
  repo: WorktreesProps["repo"];
  onOpen: (id: string) => void;
}): React.JSX.Element {
  const total = blocks.reduce((n, b) => n + b.rows.length, 0);
  const empty = EMPTY[title] ?? EMPTY["In progress"]!;
  return (
    <section style={shell} data-testid="worktree-column" data-column={title}>
      <div style={columnHead}>
        <span>{title}</span>
        <span>{total === 1 ? "1 tree" : `${total} trees`}</span>
      </div>
      {total === 0 ? (
        <div data-testid="worktrees-empty" style={emptyBody}>
          <span style={{ maxWidth: "34em" }}>{empty.said}</span>
          {/* The move that would fill this column — NAMED, not offered. This
              dashboard has exactly ONE write and it is the comment box, so a
              button here would be a second one; the call belongs in the
              orchestrator's session, which is where it is refused or works. */}
          <span className="mono" style={{ fontSize: "11.5px", color: "var(--text-2)" }}>
            {empty.move}
          </span>
        </div>
      ) : (
        blocks
          .filter((b) => b.rows.length > 0)
          .map((b) => (
            <div key={b.title}>
              <div style={blockHead} data-testid="worktree-block">
                {b.title}
              </div>
              {b.rows.map((w) => (
                <Row key={w.id} w={w} base={base} repo={repo} onOpen={onOpen} />
              ))}
            </div>
          ))
      )}
    </section>
  );
}

/** The selection, optionally CONTROLLED — and the card behind it.
 *
 *  It used to be one `useState` in this file, on the reasoning that nothing
 *  outside the page could act on it. Something can: the tab bar. Selecting
 *  "Worktrees" while a tree is open has to return to the index, and that event
 *  happens in `App.tsx`, so the state belongs there (`App.tsx::selectTab`).
 *
 *  Both props are OPTIONAL and the internal state remains the fallback, so a
 *  caller that knows nothing about them — the smoke harness renders this page
 *  with `groups` alone — gets exactly the page it had. `ThreadProps` rides
 *  through untouched, straight to `WorktreeDiff`. */
type Controlled = ThreadProps & {
  openTree?: string | null;
  onOpenTree?: (id: string | null) => void;
};

export function Worktrees({
  groups,
  milestones = [],
  repo,
  milestoneBranch = "",
  reader,
  openTree,
  onOpenTree,
  ...thread
}: WorktreesProps & Controlled): React.JSX.Element {
  const [own, setOwn] = useState<string | null>(null);
  const selected = onOpenTree ? (openTree ?? null) : own;
  const select = onOpenTree ?? setOwn;
  const titles = new Map(milestones.map((m) => [m.id, m.title]));

  /* The early return: when a tree is selected the index is REPLACED, full
   * width. Not a modal over it, not a drawer beside it.
   *
   * A selection whose row is gone — the board polled and the card merged out of
   * the groups this page folds — falls through to the index instead of drawing a
   * page about nothing. The reader is where they would have landed by pressing
   * back, which is the honest resolution of a row that no longer exists. */
  const open = selected ? (rows(groups, milestones).find((w) => w.id === selected) ?? null) : null;
  if (open) {
    return (
      <WorktreeDiff
        row={open}
        base={milestoneBranch}
        repo={repo}
        reader={reader}
        onBack={() => select(null)}
        {...thread}
      />
    );
  }
  return (
    <div style={page} data-testid="worktrees">
      <div style={head}>
        <h2 style={{ margin: 0, fontSize: "19px", fontWeight: 500, letterSpacing: "-0.035em" }}>
          Worktrees
        </h2>
        <span style={{ fontSize: "12.5px", color: "var(--text-3)" }}>
          One branch, one directory, permanent
        </span>
      </div>

      <div style={split}>
        {COLUMNS.map((c) => (
          <Column
            key={c.title}
            title={c.title}
            blocks={c.blocks.map((b) => ({ title: b.title, rows: fold(groups, b, titles) }))}
            base={milestoneBranch}
            repo={repo}
            onOpen={select}
          />
        ))}
      </div>

      <div style={notes}>
        {NOTES.map((n) => (
          <div
            key={n.title}
            style={{
              borderRadius: "16px",
              background: "var(--pane)",
              border: "1px solid var(--hair)",
              padding: "18px",
            }}
          >
            <div
              style={{
                fontSize: "14.5px",
                fontWeight: 500,
                letterSpacing: "-0.025em",
                marginBottom: "8px",
              }}
            >
              {n.title}
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-2)", lineHeight: 1.6 }}>
              {n.body}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Worktrees;
