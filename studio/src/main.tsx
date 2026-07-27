/* The app: a header, a board, a fleet, and a drawer. That is the whole component tree.
 *
 * Deliberately flat. There is no router, no store and no provider: the studio has one screen and
 * one piece of shared state, and every layer of indirection between a click and a fetch is a layer
 * somebody has to read before they can change anything. */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Board } from "./components/Board";
import { Fleet } from "./components/Fleet";
import { Header } from "./components/Header";
import { TaskPanel } from "./components/TaskPanel";
import { useStudio } from "./useStudio";

function App(): JSX.Element {
  const studio = useStudio();
  return (
    <>
      <Header config={studio.config} board={studio.board} live={studio.live}
              pulse={studio.pulse} onOpen={studio.openTask} />

      {studio.error ? (
        <div className="banner">
          {studio.error}
          <button className="linkish" onClick={studio.refresh}>retry</button>
        </div>
      ) : null}

      <main>
        {studio.board ? <Board board={studio.board} onOpen={studio.openTask} />
                      : <div className="loading dim">Reading the board…</div>}
        {studio.fleet ? <Fleet fleet={studio.fleet} onOpen={studio.openTask} /> : null}
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
