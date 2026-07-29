/* The board: columns of cards, and nothing that is not on a card.
 *
 * EVERY column is shown by default, with a placeholder where one is empty. Hiding them was the first
 * version, on the theory that four of eight statuses are usually empty and showing them turns a
 * readable board into a row of placeholders. It reads as a BUG instead: somebody who cannot see a
 * `done` column cannot tell whether nothing is finished or whether the board has no such state, and
 * "where are my done cards" is the question it produced. So the hiding is a CHOICE the reader makes,
 * from the header, and it is off until they make it.
 *
 * `done` is grouped rather than listed. A board a few weeks old has more finished cards than every
 * other column combined, and a hundred-card list is a wall — it pushes the columns that need
 * attention off the screen and answers no question anybody asks. */

import type { Board as BoardData, Card as CardData, Status } from "../contracts";
import { Actor, COLUMN_LABEL, Counts, MARK, Priority, ago } from "./bits";

/* Grouped, and above which size. `done` because that is the column that grows without bound —
 * nothing ever leaves it — and the threshold so that a young board still reads as a plain list. */
const GROUPED: Status[] = ["done", "cancelled"];
const GROUP_FROM = 6;

export type Grouping = "date" | "feature";

export function Board({ board, hideEmpty, grouping, onGrouping, onOpen }: {
  board: BoardData;
  hideEmpty: boolean;
  grouping: Grouping;
  onGrouping: (how: Grouping) => void;
  onOpen: (id: string) => void;
}): JSX.Element {
  /* The empty-PROJECT case is still special: a board with no tasks at all wants instructions, not
   * eight empty columns. An empty COLUMN on a populated board is information. */
  if (board.total === 0) return <Empty />;
  const columns = hideEmpty ? board.columns.filter((c) => c.cards.length > 0) : board.columns;
  return (
    <div className="board">
      {columns.map((column) => {
        const grouped = GROUPED.includes(column.status) && column.cards.length >= GROUP_FROM;
        return (
          <section className={`column column-${column.status}`} key={column.status}>
            <header className="column-head">
              <span className="mark">{MARK[column.status]}</span>
              <h2>{COLUMN_LABEL[column.status]}</h2>
              <span className="tally">{column.cards.length}</span>
              {grouped ? <GroupingToggle how={grouping} onPick={onGrouping} /> : null}
            </header>
            <div className="cards">
              {column.cards.length === 0
                ? <p className="column-empty dim">Nothing here.</p>
                : grouped
                  ? <Grouped cards={column.cards} how={grouping} onOpen={onOpen} />
                  : column.cards.map((card) => (
                      <Card card={card} key={card.task.id} onOpen={onOpen} />
                    ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/* Two questions, and which one somebody is asking changes by the minute: "what landed today" is the
 * standup, "what did this feature cost" is the review. Date is the default because it is the one
 * that always works — a feature grouping over cards nobody grouped is one big bucket. */
function GroupingToggle({ how, onPick }: {
  how: Grouping;
  onPick: (how: Grouping) => void;
}): JSX.Element {
  return (
    <button className="group-by" title="how these are grouped"
            onClick={() => onPick(how === "date" ? "feature" : "date")}>
      {how === "date" ? "by date" : "by feature"}
    </button>
  );
}

/* The FIRST group is open and the rest are collapsed. Opening all of them would be the wall the
 * grouping exists to remove, and the newest bucket is the one somebody came to read. */
function Grouped({ cards, how, onOpen }: {
  cards: CardData[];
  how: Grouping;
  onOpen: (id: string) => void;
}): JSX.Element {
  const groups = how === "date" ? byDate(cards) : byFeature(cards);
  return (
    <>
      {groups.map(([label, members], index) => (
        <details className="group" key={label} open={index === 0}>
          <summary>
            <span className="group-label">{label}</span>
            <span className="tally">{members.length}</span>
          </summary>
          {members.map((card) => <Card card={card} key={card.task.id} onOpen={onOpen} />)}
        </details>
      ))}
    </>
  );
}

const ORDER = ["Today", "Yesterday", "This week", "This month", "Older"];

/* By when it was last touched, which for a finished card is when it finished.
 *
 * CALENDAR boundaries, not a rolling window. "Today" as "within 24 hours" puts last night's work
 * under today's heading, which is exactly the thing a person reads a date grouping to tell apart —
 * they know they finished those yesterday, and a board saying otherwise is a board lying to them.
 *
 * Buckets rather than one heading per day: thirty headings of one card each is the same wall with
 * more chrome on it. */
function byDate(cards: CardData[]): [string, CardData[]][] {
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  const today = midnight.getTime() / 1000;
  const named = (card: CardData): string => {
    const when = card.task.updated;
    if (when >= today) return "Today";
    if (when >= today - 86400) return "Yesterday";
    if (when >= today - 7 * 86400) return "This week";
    if (when >= today - 30 * 86400) return "This month";
    return "Older";
  };
  return collect(cards, named, ORDER);
}

/* A "feature" is what the cards themselves already say they belong to: a parent task if somebody
 * planned it that way, otherwise the first label. Neither is invented here — inferring one from
 * title prefixes would group by coincidence and be wrong in a way nobody could see. */
function byFeature(cards: CardData[]): [string, CardData[]][] {
  const named = (card: CardData): string =>
    card.task.parent ?? card.task.labels[0] ?? "Loose";
  return collect(cards, named, []);
}

function collect(cards: CardData[], named: (card: CardData) => string,
                 order: string[]): [string, CardData[]][] {
  const groups = new Map<string, CardData[]>();
  for (const card of cards) {
    const key = named(card);
    const bucket = groups.get(key);
    if (bucket) bucket.push(card);
    else groups.set(key, [card]);
  }
  const keys = [...groups.keys()];
  /* A declared order when there is one (Today before Older), biggest-first when there is not —
   * for features, the one with ten cards is the one worth opening. */
  keys.sort((a, b) => order.length
    ? order.indexOf(a) - order.indexOf(b)
    : groups.get(b)!.length - groups.get(a)!.length);
  return keys.map((key) => [key, groups.get(key)!]);
}

function Card({ card, onOpen }: { card: CardData; onOpen: (id: string) => void }): JSX.Element {
  const { task, lease } = card;
  return (
    <article
      className={`card${lease ? " held" : ""}`}
      onClick={() => onOpen(task.id)}
      /* A real button would be correct and would also put a focus ring on every card in a
       * fifty-card board. `tabIndex` + Enter gives the keyboard path without the visual cost. */
      tabIndex={0}
      role="button"
      onKeyDown={(keys) => { if (keys.key === "Enter") onOpen(task.id); }}
    >
      <div className="card-top">
        <Priority value={task.priority} />
        <code className="id">{task.id}</code>
        <Counts up={card.blocked_by} down={card.blocks} commits={card.commits} />
      </div>
      <p className="title">{task.title}</p>
      {lease ? (
        <div className="card-lease">
          <Actor id={lease.actor} />
          {lease.branch ? <code className="branch">{lease.branch}</code> : <span className="dim">no branch yet</span>}
        </div>
      ) : task.assignee ? (
        /* Only when nothing HOLDS it: a lease is the stronger fact (somebody is working on it
         * right now) and drawing both would say the same thing twice on a card with five lines. */
        <div className="card-lease">
          <Actor id={task.assignee} />
          <span className="dim">assigned</span>
        </div>
      ) : null}
      {task.labels.length > 0 ? (
        <div className="labels">
          {task.labels.map((label) => <span className="label" key={label}>{label}</span>)}
        </div>
      ) : null}
      <div className="card-foot dim">{ago(task.updated)}</div>
    </article>
  );
}

function Empty(): JSX.Element {
  return (
    <div className="empty">
      <h2>No tasks yet</h2>
      <p>
        Ask an agent to plan some work — <code>/taskops:plan</code> — or from a terminal:
      </p>
      <pre>{`echo '[{"title":"First task","spec":"What done looks like."}]' \\\n  | taskops plan -`}</pre>
    </div>
  );
}
