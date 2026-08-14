/* The kanban — five columns DERIVED from `board.groups`, and nothing else.
 *
 * There is no second read and no client-side status computation: `pulse.py::run`
 * already answered the only question this page asks, and it answered it grouped
 * by the move each card needs. All this file does is fold nine groups into the
 * five columns a human reads left to right.
 *
 *     Ready      take
 *     In flight  doing + stalled          stalled carries a danger marker
 *     Review     review + reviewing + changes    three sub-state chips, one column
 *     Blocked    blocked                  with what each one waits on
 *     To merge   merge                    done, and NOT in the trunk
 *
 * The folding is the fix, not decoration. v1's board drew the seven STORED
 * statuses by plain equality and its teardown (~/taskops/docs/teardown/
 * server-and-ui.md §6, "Verification, as the owner complains") lists the cost:
 * `landed` was an rpc verb and an event that nothing in the UI rendered, so
 * "done but not in the trunk" was invisible; and `review` was one column with no
 * sub-state, so "handed over, nobody checking" and "being verified" drew
 * identically — while the server already computed the split. Both are groups
 * here, so both are on screen, and neither can be lost by a renderer that only
 * knows how to draw what it is handed.
 *
 * TWO WAYS TO READ IT, one payload. A segmented control at the top switches
 * between these columns and the FLOW (`components/flow/`), which draws the same
 * nine groups as a dependency graph left to right. The columns say WHAT each
 * card is; the flow says WHY — which card unblocks which. Columns is the
 * default and stays byte-identical, which `BoardColumns` below exists to make
 * provable; the choice is page state, remembered in one localStorage key, and
 * NOT a tab (a tab would file the flow beside Monitor and Actors as if it were
 * another page with another payload).
 *
 * Read-only, absolutely: the tiles are buttons that open the drawer. No
 * drag-and-drop, no status control, no write verb reachable from this page —
 * the UI does not move cards (milestone rule 1). */
import { useState } from "react";

import type { BoardPayload, BoardRow } from "../types";
import { Column } from "../components/board/Column";
import type { Chip, Tone } from "../components/board/CardTile";
import { CardTile } from "../components/board/CardTile";
import { useFlip } from "../components/board/useFlip";
import { ViewToggle } from "../components/board/ViewToggle";
import type { BoardView } from "../components/board/ViewToggle";
import { FlowView } from "../components/flow/FlowView";
import { shortActor } from "../format";

/** Where the choice of view is remembered. One key, and the same
 *  `taskops:` prefix `theme.ts` and `client.ts` use. */
export const VIEW_KEY = "taskops:board-view";

/** The narrow slice of `localStorage` this page needs — injectable for the same
 *  reason `client.ts::subscribe`'s Env is: the smoke renders headlessly and
 *  must be able to drive both shapes without a browser. */
export interface ViewStore {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

/** Columns is the DEFAULT, and anything unreadable is columns too: a stored
 *  value from a future version, a storage that throws (Safari private mode),
 *  no storage at all. The flow is the second way to read the board and never
 *  the one a reader lands on without having asked for it. */
export function rememberedView(store: ViewStore | undefined): BoardView {
  try {
    return store?.getItem(VIEW_KEY) === "flow" ? "flow" : "columns";
  } catch {
    return "columns";
  }
}

export interface BoardProps {
  board: BoardPayload;
  openCard: (id: string) => void;
  /** the remembered `columns | flow` choice; the real `localStorage` in the app */
  store?: ViewStore | undefined;
  /** Cards a comment landed on moments ago — `toasts/useToasts.ts::pulsing`,
   *  derived from the live toast stack and passed straight through to the tile.
   *  Nothing is stored, nothing is counted, and an empty set (the default, and
   *  what a reader who asked for less motion always gets) draws the board
   *  exactly as it drew before this existed. */
  recent?: ReadonlySet<string> | undefined;
}

/** A row, plus everything the tile must show that the row alone does not say —
 *  which group it came from. Derived once, here; never re-derived downstream. */
interface Tile {
  row: BoardRow;
  chip?: Chip | undefined;
  marker?: Tone | undefined;
  note?: string | undefined;
  waitingOn?: readonly string[] | undefined;
}

interface Col {
  name: string;
  tone: Tone;
  tiles: Tile[];
}

/** `text` on a review row is empty and on a changes row it is the reviewer's
 *  words; a reviewing row carries who is holding the REVIEW lease. Both are
 *  shown verbatim — the reason travelled with the row for a reason. */
function checkedBy(holder: string | null): string | undefined {
  return holder ? `checked by ${shortActor(holder)}` : undefined;
}

export function columns(board: BoardPayload): Col[] {
  const g = board.groups;
  return [
    {
      name: "Ready",
      tone: "neutral",
      tiles: g.take.map((row) => ({ row })),
    },
    {
      name: "In flight",
      tone: "accent",
      tiles: [
        ...g.doing.map((row) => ({ row, chip: { label: "running", tone: "ok" } as Chip })),
        // The whole reason these two share a column: a stalled card is IN
        // flight — it has an owner — and nobody is running it. Mixed in
        // invisibly it reads as progress; it is the opposite.
        ...g.stalled.map((row) => ({
          row,
          chip: { label: "stalled", tone: "danger" } as Chip,
          marker: "danger" as Tone,
        })),
      ],
    },
    {
      name: "Review",
      tone: "warn",
      tiles: [
        ...g.review.map((row) => ({
          row,
          chip: { label: "waiting", tone: "warn" } as Chip,
          note: row.text || undefined,
        })),
        ...g.reviewing.map((row) => ({
          row,
          chip: { label: "being checked", tone: "accent" } as Chip,
          note: checkedBy(row.holder),
        })),
        ...g.changes.map((row) => ({
          row,
          chip: { label: "changes requested", tone: "danger" } as Chip,
          note: row.text || undefined,
        })),
      ],
    },
    {
      name: "Blocked",
      tone: "danger",
      tiles: g.blocked.map((row) => ({ row, waitingOn: row.waiting_on })),
    },
    {
      name: "To merge",
      tone: "ok",
      tiles: g.merge.map((row) => ({
        row,
        chip: { label: "not in trunk", tone: "ok" } as Chip,
        marker: "ok" as Tone,
      })),
    },
    {
      // Closed AND in the trunk. Nothing to do here — it is the only screen on
      // which finished work exists at all, and without it a chapter's whole
      // history lives in the event log and nowhere a person can look.
      // `?? 0` / `?? []`: both arrived in one commit and a board older than it
      // sends neither (types.ts). Absent collapses to the plain "Done" header
      // over an empty column — the honest reading of a payload that cannot say.
      name: (() => {
        const shown = (g.done ?? []).length;
        const total = board.done_total ?? 0;
        return total > shown ? `Done · ${shown} of ${total}` : "Done";
      })(),
      tone: "neutral",
      tiles: (g.done ?? []).map((row) => ({ row, chip: { label: "in trunk", tone: "ok" } as Chip })),
    },
  ];
}

/** Which tile draws its chapter, and with what words — decided ONCE for the
 *  whole view, keyed by card id.
 *
 *  Two rules, and both are about the view rather than the tile:
 *
 *  1. The JOIN. `BoardRow.milestone` is the chapter's ID (`verbs/pulse.py::_row`)
 *     and `board.milestones` carries `{id, title, …}` — the same join
 *     `pages/Worktrees.tsx::chapter()` does, against the same list, and there is
 *     no second behaviour: an id that does not resolve draws NOTHING. A board
 *     one version behind sends no `milestone` on the row, and a chapter aged
 *     past `milestones`' cap is an id this payload cannot name; `ms-9f21` on a
 *     tile is not information, it is the join failing out loud.
 *
 *  2. WHETHER to draw at all: only when the rows IN VIEW span more than one
 *     chapter. With a chapter in focus every tile would carry the same label and
 *     the header already says which chapter you are reading — noise on every
 *     card in every column. So the count is over what is on SCREEN, not over how
 *     many chapters the board has: the picker sends "All milestones" and one
 *     chapter's worth of rows just as easily.
 *
 *  A row that does not resolve is not counted either: it contributes no chapter
 *  to the view, so it cannot be the second one that turns every label on. */
export function chapterLabels(board: BoardPayload, cols: readonly Col[]): Map<string, string> {
  const titles = new Map(board.milestones.map((m) => [m.id, m.title]));
  const labels = new Map<string, string>();
  const seen = new Set<string>();
  for (const col of cols) {
    for (const tile of col.tiles) {
      const id = tile.row.milestone ?? "";
      const title = id ? titles.get(id) : undefined;
      if (!title) continue;
      labels.set(tile.row.id, title);
      seen.add(id);
    }
  }
  return seen.size > 1 ? labels : new Map();
}

const scroll: React.CSSProperties = {
  height: "100%",
  overflowX: "auto",
  overflowY: "hidden",
  padding: "0 24px 26px",
};

const rail: React.CSSProperties = {
  display: "grid",
  gridAutoFlow: "column",
  gridAutoColumns: "minmax(278px, 1fr)",
  gap: "14px",
  height: "100%",
  minHeight: "540px",
};

/** The kanban, whole and untouched by the toggle above it.
 *
 *  Extracted from `Board` rather than left inline so that "columns is
 *  byte-identical when selected" is a claim a test can make: the smoke renders
 *  this alone and asserts the Board's markup CONTAINS it, character for
 *  character. A second way to read the board must not cost the first one a
 *  pixel. */
export function BoardColumns({ board, openCard, recent }: BoardProps): React.JSX.Element {
  const cols = columns(board);
  const chapters = chapterLabels(board, cols);
  /* The board MOVES. Every tile hands its element over by card id, and after
     each commit the hook plays the ones that changed place from where they were
     to where the payload put them (`components/board/flip.ts` argues it, and
     holds every part of it that can be decided without a browser).
     Read-only still: this animates what the server said, it does not move a
     card and there is no drag handle. */
  const flip = useFlip();
  return (
    <div style={scroll} data-testid="board">
      <div style={rail}>
        {cols.map((col) => (
          <Column key={col.name} name={col.name} tone={col.tone} count={col.tiles.length}>
            {col.tiles.map((tile) => (
              <CardTile
                key={tile.row.id}
                row={tile.row}
                chip={tile.chip}
                marker={tile.marker}
                note={tile.note}
                waitingOn={tile.waitingOn}
                chapter={chapters.get(tile.row.id)}
                tileRef={flip.register(tile.row.id)}
                recentComment={recent?.has(tile.row.id) ?? false}
                onOpen={openCard}
              />
            ))}
          </Column>
        ))}
      </div>
    </div>
  );
}

const shell: React.CSSProperties = {
  height: "100%",
  display: "grid",
  gridTemplateRows: "auto minmax(0, 1fr)",
};

/** The page: one control, and one of two ways to read the same payload.
 *
 *  There is no second fetch and no second derivation — the flow folds the SAME
 *  nine groups (`components/flow/layout.ts`), so the two views cannot disagree
 *  about what the board says, only about how it reads. */
export function Board({ board, openCard, store, recent }: BoardProps): React.JSX.Element {
  const [view, setView] = useState<BoardView>(() =>
    rememberedView(store ?? (typeof window === "undefined" ? undefined : window.localStorage)),
  );
  const choose = (next: BoardView): void => {
    setView(next);
    try {
      (store ?? (typeof window === "undefined" ? undefined : window.localStorage))?.setItem(
        VIEW_KEY,
        next,
      );
    } catch {
      /* a storage that refuses to write is not a reason to refuse the view */
    }
  };
  return (
    <div style={shell}>
      <div style={{ padding: "0 24px 12px" }}>
        <ViewToggle active={view} onSelect={choose} />
      </div>
      {view === "flow" ? (
        <FlowView board={board} openCard={openCard} />
      ) : (
        <BoardColumns board={board} openCard={openCard} recent={recent} />
      )}
    </div>
  );
}

export default Board;
