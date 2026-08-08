/* The third view — Nova's WORKTREES section (Taskops Nova.dc.html lines 536-568).
 *
 * One table, five columns, and under it three note cards. It answers the one
 * question the kanban cannot: not "what state is this card in" but "what is on
 * disk right now, who is carrying it, and has it reached the trunk". The WHO is
 * two facts on one mono line inside the Card cell — the dev to talk to and the
 * worker process holding the directory; see `GRID` for why it is not a column.
 *
 * DERIVED FROM `board.groups`, exactly like `pages/Board.tsx::columns` — same
 * mechanism, different fold. There is no second read, no client-side status
 * computation and no worktree verb: `pulse.py::run` already grouped every card
 * by the move it needs, and this file only says which pill each group wears.
 * The rows are emitted in `GROUP_ORDER` (`types.ts`), which is the order the
 * board itself builds them in and therefore the order to ACT in — a view that
 * reorders them is contradicting the board.
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
 * Read-only, absolutely: a row is a button and the only thing it does is open
 * the Dossier. `LIST_CAP` deliberately does NOT apply — this is a full-height
 * view like the Board, not a pane inside a grid, so the table grows and the
 * page scrolls. */
import { PaneButton } from "../components/monitor/Pane";
import {
  TREE_DIR,
  type Tone,
  type WorktreeRow,
  type WorktreesProps,
} from "../components/monitor/panels";
import { TONE_BG, TONE_FG } from "../components/board/CardTile";
import { ownerOf, shortActor } from "../format";
import { Ext, compareUrl, hasRepo } from "../links";
import type { BoardRow } from "../types";

export type { WorktreesProps };

/** WHO carries a tree, from the row the table already has.
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

function tree(row: BoardRow, status: string, tone: Tone): WorktreeRow {
  return {
    id: row.id,
    title: row.title,
    ...owner(row),
    // Construction, not a fetch: `gitwork/trees.py` pins every card's worktree
    // to `.taskops/trees/<id>` for life. There is no directory on the wire.
    dir: TREE_DIR + row.id,
    // No source on the row — see the field's own note in panels.ts.
    commits: null,
    status,
    tone,
  };
}

export function rows(groups: WorktreesProps["groups"]): WorktreeRow[] {
  return [
    ...groups.merge.map((r) => tree(r, "done, not merged", "warn")),
    // `review` and `changes` are not in the five states Nova's pill draws, and
    // they are not dropped either: a handed-in card still inhabits its worktree
    // and its branch still exists, so it is IN PROGRESS on this table — that is
    // the fact this view reports. The Board page is where their three review
    // sub-states are told apart; here they are one directory on disk.
    ...groups.review.map((r) => tree(r, "in progress", "accent")),
    ...groups.changes.map((r) => tree(r, "in progress", "accent")),
    ...groups.stalled.map((r) => tree(r, "in progress · stalled", "danger")),
    ...groups.take.map((r) => tree(r, "ready", "neutral")),
    ...groups.doing.map((r) => tree(r, "in progress", "accent")),
    ...groups.reviewing.map((r) => tree(r, "in progress", "accent")),
    ...groups.blocked.map((r) => tree(r, "blocked", "danger")),
    // `?? []`: the `done` group postdates the other nine (types.ts), so a board
    // older than a1d1005 sends no such key and this table simply has no merged
    // rows to draw — which is the truth about what that payload can say.
    ...(groups.done ?? []).map((r) => tree(r, "merged", "ok")),
  ];
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

const GRID = "130px minmax(0,1fr) 240px 92px 124px";

/* WHO carries the tree is folded INTO the Card cell — a mono line under the
 * title — and is NOT a sixth column. The five widths above are Nova's, drawn;
 * the table already spends its ONE elastic track on the title, so a real column
 * would have to take its width from that track (`minmax(0,1fr)` is what makes
 * the long titles legible) and every other cell is a fixed pixel width the
 * design chose.
 *
 * The mono second line is the design's OWN vocabulary for exactly this pair:
 * Live leases prints `<card-id> → <actor>` as an 11px mono line under its title
 * (`components/monitor/LiveLeases.tsx`), so a reader who has seen the Monitor
 * has already learnt to read this line. Here the id is redundant — it is the
 * Branch column, one cell to the left — so the line carries the two halves of
 * the answer instead: `dev:berna · e4`.
 *
 * And it has to compose with tk-3939c9's SIXTH column, which is real and
 * conditional: `LINK_COL` is appended to `GRID` only when the board carries a
 * slug. A second conditional column would make the grid string a four-way
 * product of two unrelated switches, and the compare anchor is laid out
 * ABSOLUTELY against the row's right edge — a column that only sometimes sits
 * between the pill and that anchor would move a link that is positioned in
 * pixels. Folding leaves that geometry untouched: the grid is the same string,
 * with or without ownership. */

/* The compare column, added ONLY when the board carries a slug.
 *
 * A row is a `<button>` — it opens the dossier — and an `<a>` inside a
 * `<button>` is invalid HTML and unreachable by keyboard, so the link cannot
 * simply be dropped into the Status cell. It is a RESERVED sixth column in the
 * grid (header and row alike, so the five columns stay aligned to the pixel)
 * with the anchor laid over it, absolutely, from the row's own wrapper.
 *
 * With no slug the column does not exist: `linked` is false, both templates are
 * `GRID` verbatim, no wrapper cell is emitted and the table is byte-for-byte
 * what it was. That is the chapter's third rule as a layout. */
const LINK_COL = "46px";

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

const shell: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
};

const headerRow: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: GRID,
  gap: "16px",
  padding: "13px 20px",
  fontSize: "11.5px",
  color: "var(--text-3)",
  borderBottom: "1px solid var(--hair)",
};

/** The row itself. `PaneButton` already owns the hover, the `all: unset` reset
 *  and the hairline; the grid is this table's, so it rides in as `style`. The
 *  design's separator is a border-BOTTOM and PaneButton draws a border-top, so
 *  the two are swapped here — same hairline between the same rows, and the
 *  header's own bottom border stands in for the first one. */
const rowGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: GRID,
  gap: "16px",
  alignItems: "center",
  borderTop: "none",
  borderBottom: "1px solid var(--hair)",
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

export function Worktrees({
  groups,
  onOpen,
  repo,
  milestoneBranch = "",
}: WorktreesProps): React.JSX.Element {
  const list = rows(groups);
  const linked = hasRepo(repo);
  const columns = linked ? `${GRID} ${LINK_COL}` : GRID;
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

      <div style={shell}>
        <div style={{ ...headerRow, gridTemplateColumns: columns }}>
          <div>Branch</div>
          <div>Card</div>
          <div>Directory</div>
          <div style={{ textAlign: "right" }}>Commits</div>
          <div style={{ textAlign: "right" }}>Status</div>
          {linked ? <div /> : null}
        </div>
        {list.length === 0 ? (
          <div
            data-testid="worktrees-empty"
            style={{
              padding: "22px 20px 26px",
              fontSize: "12.5px",
              color: "var(--text-3)",
              lineHeight: 1.6,
            }}
          >
            No card is open on this chapter, so no worktree is pinned to one. A
            directory appears here the moment a card exists, and it keeps it.
          </div>
        ) : (
          list.map((w) => {
            // The row's branch IS its card id (`WorktreeRow`); the base is the
            // chapter's integration branch, and with no chapter in focus the
            // forge falls back to its own default branch.
            const diff = compareUrl(repo, w.id, milestoneBranch);
            return (
          <div key={w.id} style={{ position: "relative" }}>
            <PaneButton
              cardId={w.id}
              onOpen={onOpen}
              testId="worktree-row"
              pad="14px 20px"
              style={{ ...rowGrid, gridTemplateColumns: columns }}
            >
              <span className="mono" style={{ fontSize: "12px", color: "var(--accent)" }}>
                {w.id}
              </span>
              <span style={{ minWidth: 0, display: "block" }}>
                <span
                  style={{
                    ...clip,
                    display: "block",
                    fontSize: "14px",
                    fontWeight: 450,
                    letterSpacing: "-0.025em",
                  }}
                >
                  {w.title}
                </span>
                {/* The dev is the sentence's subject and the worker its
                    qualifier, so they are drawn in that weight: the person in
                    `--text-2`, the process a shade back in `--text-3`. Same
                    line, two colours — distinguishable without a second column
                    and without a label nobody needs twice per row. */}
                <span
                  className="mono"
                  data-testid="worktree-owner"
                  style={{
                    ...clip,
                    display: "block",
                    fontSize: "11px",
                    marginTop: "4px",
                    color: w.dev ? "var(--text-2)" : "var(--text-3)",
                  }}
                >
                  {w.dev ?? "nobody — free to take"}
                  {w.worker ? (
                    <span style={{ color: "var(--text-3)" }}>{` · ${w.worker}`}</span>
                  ) : null}
                </span>
              </span>
              <span
                className="mono"
                style={{ ...clip, fontSize: "11px", color: "var(--text-3)" }}
              >
                {w.dir}
              </span>
              {/* No payload behind this column — it renders the em dash, never a
                  number nobody sent. */}
              <span
                className="mono num"
                data-testid="worktree-commits"
                style={{ fontSize: "13px", textAlign: "right", color: "var(--text-3)" }}
              >
                {w.commits ?? "—"}
              </span>
              <span style={{ textAlign: "right" }}>
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
              {linked ? <span /> : null}
            </PaneButton>
            {diff ? (
              <Ext
                href={diff}
                title={`${milestoneBranch || "the trunk"}...${w.id}`}
                style={{
                  position: "absolute",
                  right: "20px",
                  top: 0,
                  bottom: 0,
                  display: "flex",
                  alignItems: "center",
                  color: "var(--accent)",
                  fontSize: "12px",
                }}
              >
                <span data-testid="worktree-compare">↗</span>
              </Ext>
            ) : null}
          </div>
            );
          })
        )}
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
