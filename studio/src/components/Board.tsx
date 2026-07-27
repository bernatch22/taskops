/* The board: columns of cards, and nothing that is not on a card.
 *
 * EVERY column is shown, always, with a placeholder where one is empty. Hiding them was the first
 * version, on the theory that four of eight statuses are usually empty and showing them turns a
 * readable board into a row of placeholders. It reads as a BUG instead: somebody who cannot see a
 * `done` column cannot tell whether nothing is finished or whether the board has no such state, and
 * "where are my done cards" is the question it produced. */

import type { Board as BoardData, Card as CardData } from "../contracts";
import { Actor, COLUMN_LABEL, Counts, MARK, Priority, ago } from "./bits";

export function Board({ board, onOpen }: {
  board: BoardData;
  onOpen: (id: string) => void;
}): JSX.Element {
  /* The empty-PROJECT case is still special: a board with no tasks at all wants instructions, not
   * eight empty columns. An empty COLUMN on a populated board wants to be visible. */
  if (board.total === 0) return <Empty />;
  return (
    <div className="board">
      {board.columns.map((column) => (
        <section className={`column column-${column.status}`} key={column.status}>
          <header className="column-head">
            <span className="mark">{MARK[column.status]}</span>
            <h2>{COLUMN_LABEL[column.status]}</h2>
            <span className="tally">{column.cards.length}</span>
          </header>
          <div className="cards">
            {column.cards.length === 0
              ? <p className="column-empty dim">Nothing here.</p>
              : column.cards.map((card) => (
                  <Card card={card} key={card.task.id} onOpen={onOpen} />
                ))}
          </div>
        </section>
      ))}
    </div>
  );
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
