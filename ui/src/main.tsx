/* The app: a header, a board, and a drawer. That is the whole component tree.
 *
 * Deliberately flat. There is no router, no store and no provider: the UI has one screen and
 * one piece of shared state, and every layer of indirection between a click and a fetch is a layer
 * somebody has to read before they can change anything. */

import { StrictMode } from "react";
import type { Board as BoardData } from "./contracts";
import { createRoot } from "react-dom/client";
import { Activity } from "./components/Activity";
import { Board, type Grouping } from "./components/Board";
import { Context } from "./components/Context";
import { Header, type View } from "./components/Header";
import { Reports } from "./components/Reports";
import { TaskPanel } from "./components/TaskPanel";
import { remembered } from "./remembered";
import { useStudio } from "./useStudio";

function App(): JSX.Element {
  const studio = useStudio();
  /* View preferences, not data: they belong to the person and their browser, never to the server.
   * A second developer looking at the same repository has their own answer for both. */
  const [hideEmpty, setHideEmpty] = remembered("taskops-hide-empty", false);
  const [grouping, setGrouping] = remembered<Grouping>("taskops-grouping", "date");
  const [view, setView] = remembered<View>("taskops-view", "board");
  /* Remembered: this is reference material somebody chooses to keep pinned, not a thing they
   * are doing right now. Left open, it stays open tomorrow. */
  const [context, setContext] = remembered("taskops-context-open", false);


  return (
    <>
      <Header config={studio.config} board={studio.board} context={studio.context} live={studio.live}
              pulse={studio.pulse} view={view} onView={setView}
              hideEmpty={hideEmpty} onHideEmpty={setHideEmpty}
              onOpen={studio.openTask} />

      {/* Under the header and OUTSIDE `main`, so it is on screen whichever view is chosen —
        * which is the whole point. Filing it as a fourth tab would put the chapter in force
        * behind a click that nobody makes twice. */}
      <Context context={studio.context} open={context} onToggle={() => setContext(!context)} />

      {studio.error ? (
        <div className="banner">
          {studio.error}
          <button className="linkish" onClick={studio.refresh}>retry</button>
        </div>
      ) : null}

      <main>
        {view === "activity"
          ? <Activity onOpen={studio.openTask} />
          : view === "reports"
          ? <Reports readonly={studio.config?.readonly ?? false} narration={studio.narration} />
          : studio.board
            ? <Board board={studio.board} hideEmpty={hideEmpty} grouping={grouping}
                     onGrouping={setGrouping} onOpen={studio.openTask} />
            : <div className="loading dim">Reading the board…</div>}
      </main>

      {studio.open ? (
        <TaskPanel
          view={studio.open}
          readonly={studio.config?.readonly ?? false}
          people={peopleOn(studio.board)}
          onClose={() => studio.openTask(null)}
          onOpen={studio.openTask}
          /* The refetch after a write is NOT an optimisation of the live feed — it is what makes
           * the person's own action feel instant instead of arriving on the next tick. */
          onDone={studio.refresh}
        />
      ) : null}

      {/* Last, and outside `main`, so it slides OVER the content instead of reflowing it — and
        * mounted whatever the view is, which is what "reachable from anywhere" means here. */}
    </>
  );
}

/* Everybody this board has actually seen — who created a card, who holds one, who was given one.
 * Derived here rather than fetched: there is no registry of PEOPLE on the server, and the board
 * already carries every id it would contain. Sorted so the list does not reshuffle on a refetch. */
function peopleOn(board: BoardData | null): string[] {
  const seen = new Set<string>();
  for (const column of board?.columns ?? []) {
    for (const card of column.cards) {
      seen.add(card.task.created_by);
      if (card.task.assignee) seen.add(card.task.assignee);
      if (card.lease) seen.add(card.lease.actor);
    }
  }
  return [...seen].filter(Boolean).sort();
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<StrictMode><App /></StrictMode>);
