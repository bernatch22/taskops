/* The app: a header, a board, and a drawer. That is the whole component tree.
 *
 * Deliberately flat. There is no router, no store and no provider: the UI has one screen and
 * one piece of shared state, and every layer of indirection between a click and a fetch is a layer
 * somebody has to read before they can change anything. */

import { StrictMode, useState } from "react";
import type { Board as BoardData } from "./contracts";
import { createRoot } from "react-dom/client";
import { Activity } from "./components/Activity";
import { Board, type Grouping } from "./components/Board";
import { Header, type View } from "./components/Header";
import { MilestoneModal } from "./components/MilestoneModal";
import { ALL, Picker } from "./components/Picker";
import { ProjectModal } from "./components/ProjectModal";
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
  /* Which chapter the board is showing. A VIEW preference and remembered, like hiding empty
   * columns: it is what somebody is working on this week, and losing it on every reload would make
   * the whole feature something you use once. `ALL` is one click away and always visible, which is
   * what keeps a remembered filter from being a trap. */
  const [picked, setPicked] = remembered("taskops-milestone", ALL);
  /* The two modals are NOT remembered, and that is the difference from the filter: a filter is a
   * decision about what you are working on, a modal is a thing you opened to read. */
  const [dashboard, setDashboard] = useState(false);
  const [project, setProject] = useState(false);
  const chapters = [...(studio.context?.active ?? []), ...(studio.context?.planned ?? [])];
  const here = chapters.find((chapter) => chapter.id === picked) ?? null;


  return (
    <>
      <Header config={studio.config} board={studio.board} context={studio.context} live={studio.live}
              pulse={studio.pulse} view={view} onView={setView}
              hideEmpty={hideEmpty} onHideEmpty={setHideEmpty}
              onOpen={studio.openTask} />

      {/* Above the columns and only over the BOARD, because it is a control over what is
        * underneath it: picking a chapter filters those columns. On the activity and report views
        * there is nothing for it to filter, and a control that does nothing is a thing to wonder
        * about. */}
      {view === "board" ? (
        <Picker context={studio.context} board={studio.board} picked={picked} onPick={setPicked}
                onDashboard={() => setDashboard(true)} onProject={() => setProject(true)} />
      ) : null}

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
                     chapter={picked} chapters={chapters} onClear={() => setPicked(ALL)}
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

      {/* The three subjects of the model, one modal each and never a tab: a chapter's facts end
        * with it, a project's do not, and a person's are theirs. `People` in the header owns the
        * third. Mounted last so they slide OVER the board instead of reflowing it. */}
      {dashboard && here && studio.context ? (
        <MilestoneModal chapter={here} context={studio.context} board={studio.board}
                        onClose={() => setDashboard(false)} />
      ) : null}
      {project && studio.context ? (
        <ProjectModal context={studio.context} repo={studio.config?.repo ?? ""}
                      onClose={() => setProject(false)} />
      ) : null}
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
