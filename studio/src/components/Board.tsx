/* The board: columns of cards, and nothing that is not on a card.
 *
 * Empty columns are HIDDEN. On a real project four of the eight statuses are usually empty, and
 * showing them turns a readable board into a row of placeholders. The count in each heading is
 * what tells you the shape at a glance. */

import type { Board as BoardData, Card as CardData } from "../contracts";
import { Actor, COLUMN_LABEL, Counts, MARK, Priority, ago } from "./bits";

export function Board({ board, onOpen }: {
  board: BoardData;
  onOpen: (id: string) => void;
}): JSX.Element {
  const columns = board.columns.filter((column) => column.cards.length > 0);
  if (columns.length === 0) return <Empty />;
  return (
    <div className="board">
      {columns.map((column) => (
        <section className={`column column-${column.status}`} key={column.status}>
          <header className="column-head">
            <span className="mark">{MARK[column.status]}</span>
            <h2>{COLUMN_LABEL[column.status]}</h2>
            <span className="tally">{column.cards.length}</span>
          </header>
          <div className="cards">
            {column.cards.map((card) => (
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
