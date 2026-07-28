/* The app: a header, a board, and a drawer. That is the whole component tree.
 *
 * Deliberately flat. There is no router, no store and no provider: the studio has one screen and
 * one piece of shared state, and every layer of indirection between a click and a fetch is a layer
 * somebody has to read before they can change anything. */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Activity } from "./components/Activity";
import { Board, type Grouping } from "./components/Board";
import { Header, type View } from "./components/Header";
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

  return (
    <>
      <Header config={studio.config} board={studio.board} live={studio.live}
              pulse={studio.pulse} view={view} onView={setView}
              hideEmpty={hideEmpty} onHideEmpty={setHideEmpty}
              onOpen={studio.openTask} />

      {studio.error ? (
        <div className="banner">
          {studio.error}
          <button className="linkish" onClick={studio.refresh}>retry</button>
        </div>
      ) : null}

      <main>
        {view === "activity"
          ? <Activity onOpen={studio.openTask} />
          : studio.board
            ? <Board board={studio.board} hideEmpty={hideEmpty} grouping={grouping}
                     onGrouping={setGrouping} onOpen={studio.openTask} />
            : <div className="loading dim">Reading the board…</div>}
      </main>

      {studio.open ? (
        <TaskPanel
          view={studio.open}
          readonly={studio.config?.readonly ?? false}
          onClose={() => studio.openTask(null)}
          onOpen={studio.openTask}
          /* The refetch after a write is NOT an optimisation of the live feed — it is what makes
           * the person's own action feel instant instead of arriving on the next tick. */
          onDone={studio.refresh}
        />
      ) : null}
    </>
  );
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<StrictMode><App /></StrictMode>);
