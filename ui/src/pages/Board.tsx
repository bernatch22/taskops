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
 * Read-only, absolutely: the tiles are buttons that open the drawer. No
 * drag-and-drop, no status control, no write verb reachable from this page —
 * the UI does not move cards (milestone rule 1). */
import type { BoardPayload, BoardRow } from "../types";
import { Column } from "../components/board/Column";
import type { Chip, Tone } from "../components/board/CardTile";
import { CardTile, shortActor } from "../components/board/CardTile";

export interface BoardProps {
  board: BoardPayload;
  openCard: (id: string) => void;
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
  ];
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

export function Board({ board, openCard }: BoardProps): React.JSX.Element {
  return (
    <div style={scroll} data-testid="board">
      <div style={rail}>
        {columns(board).map((col) => (
          <Column key={col.name} name={col.name} tone={col.tone} count={col.tiles.length}>
            {col.tiles.map((tile) => (
              <CardTile
                key={tile.row.id}
                row={tile.row}
                chip={tile.chip}
                marker={tile.marker}
                note={tile.note}
                waitingOn={tile.waitingOn}
                onOpen={openCard}
              />
            ))}
          </Column>
        ))}
      </div>
    </div>
  );
}

export default Board;
