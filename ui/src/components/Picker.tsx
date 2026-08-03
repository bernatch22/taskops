/* The milestone PICKER — a pill above the columns, and the dropdown that switches chapter.
 *
 * It replaced a full-width strip that carried a sentence, a `+1`, a date and a card count in one
 * line, and every one of those was the same mistake: the strip was trying to BE the milestone
 * instead of pointing at it. You could not tell what a milestone was from looking at it, it took
 * the whole width to say one thing, and the only way to reach the second chapter was a modal.
 *
 * So this is a control, sized to its text and nothing more:
 *
 *   ╭─────────────────────────────╮ ╭───╮
 *   │ ◆ El importador ▾  ▬▬▬░ 3/7 │ │ ⓘ │
 *   ╰─────────────────────────────╯ ╰───╯
 *
 * The TITLE is what makes that possible and it is why the model grew one: a chapter used to be one
 * long sentence, so anything that had to fit it in a row cut it mid-word. The title names it, the
 * dropdown switches it, and the `ⓘ` opens the dashboard where the goal and the chapter's own rules
 * live. Three controls, three questions, and none of them is "read this paragraph in a toolbar".
 *
 * Picking one FILTERS THE BOARD — the columns stay, their cards change. That is the whole reason it
 * sits above them rather than in the header: it is a control over what is underneath it.
 */

import { useEffect, useRef, useState } from "react";

import type { Board, ContextView, Milestone } from "../contracts";

/* `◆` in force · `◐` reported finished, waiting for a person · `○` written down, not started.
 * The glyphs `render/milestones.py` prints, so a terminal and this screen say the same thing. */
export const MARK: Record<string, string> = {
  in_force: "◆", review: "◐", planned: "○", reached: "✓", abandoned: "—",
};

export const ALL = "";
/* "No filter" is the empty string, and a card with no chapter carries `""` as well — so the second
 * case needs a sentinel of its own rather than sharing one. A space cannot be a milestone id. */
export const LOOSE = " loose";

export function Picker({ context, board, picked, onPick, onDashboard, onProject }: {
  context: ContextView | null;
  board: Board | null;
  picked: string;
  onPick: (id: string) => void;
  onDashboard: () => void;
  onProject: () => void;
}): JSX.Element | null {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useOutside(box, () => setOpen(false));

  if (!context) return null;
  const chapters = [...context.active, ...context.planned];
  const loose = totalOf(context, "");
  /* A board with no chapter and nothing loose gets NO picker. A project that has not opened one is
   * not doing anything wrong, and a permanent control saying so is the app nagging forever. */
  if (!chapters.length && !loose) return null;

  const here = chapters.find((chapter) => chapter.id === picked) ?? null;
  const counts = here ? countOf(context, here.id) : null;
  return (
    <div className="picker" ref={box}>
      <button className={`pill${here?.state === "review" ? " pill-review" : ""}`}
              onClick={() => setOpen(!open)} aria-expanded={open}
              title={here ? "switch milestone" : "filter the board by milestone"}>
        <span className="pill-mark">{here ? MARK[here.state] : "●"}</span>
        <span className="pill-title">{here ? here.title : "All milestones"}</span>
        {counts && counts.total ? (
          <Progress done={counts.done} total={counts.total} />
        ) : (
          <span className="pill-count dim">{here ? "no cards" : `${board?.total ?? 0}`}</span>
        )}
        <span className="pill-caret dim">▾</span>
      </button>

      {/* Only when a chapter is actually picked. With `All` there is no single milestone whose
        * dashboard this would open, and a button that has to explain that is a button too many. */}
      {here ? (
        <button className="pill-info" onClick={onDashboard}
                title={`${here.title} — goal, rules, decisions, notes`}>ⓘ</button>
      ) : null}
      <button className="pill-project" onClick={onProject}
              title="what this project has decided — rules, decisions, and what the engine enforces">
        ◎
      </button>

      {open ? (
        <Menu context={context} board={board} chapters={chapters} loose={loose} picked={picked}
              onPick={(id) => { onPick(id); setOpen(false); }} />
      ) : null}
    </div>
  );
}

function Menu({ context, board, chapters, loose, picked, onPick }: {
  context: ContextView;
  board: Board | null;
  chapters: Milestone[];
  loose: number;
  picked: string;
  onPick: (id: string) => void;
}): JSX.Element {
  const working = whoIsWhere(board);
  const inForce = chapters.filter((chapter) => chapter.state !== "planned");
  const next = chapters.filter((chapter) => chapter.state === "planned");
  return (
    <div className="menu" role="listbox">
      <button className={`row${picked === ALL ? " on" : ""}`} onClick={() => onPick(ALL)}>
        <span className="row-mark">●</span>
        <span className="row-title">All milestones</span>
        <span className="tally">{board?.total ?? 0}</span>
      </button>

      {inForce.length ? <p className="menu-head">In force</p> : null}
      {inForce.map((chapter) => (
        <Row key={chapter.id} chapter={chapter} counts={countOf(context, chapter.id)}
             actors={working.get(chapter.id) ?? []} on={picked === chapter.id}
             onPick={() => onPick(chapter.id)} />
      ))}

      {next.length ? <p className="menu-head">Next <span className="dim">not started</span></p> : null}
      {next.map((chapter) => (
        <Row key={chapter.id} chapter={chapter} counts={countOf(context, chapter.id)}
             actors={working.get(chapter.id) ?? []} on={picked === chapter.id}
             onPick={() => onPick(chapter.id)} />
      ))}

      {loose ? (
        /* Only when there ARE loose cards: planned before this board had chapters, and real — in
         * somebody's queue. Hiding them makes a board look emptier than it is on the one day
         * somebody upgrades. */
        <button className={`row${picked === LOOSE ? " on" : ""}`} onClick={() => onPick(LOOSE)}>
          <span className="row-mark dim">·</span>
          <span className="row-title dim">No milestone</span>
          <span className="tally">{loose}</span>
        </button>
      ) : null}
    </div>
  );
}

function Row({ chapter, counts, actors, on, onPick }: {
  chapter: Milestone;
  counts: Counted;
  actors: string[];
  on: boolean;
  onPick: () => void;
}): JSX.Element {
  return (
    <button className={`row row-${chapter.state}${on ? " on" : ""}`} onClick={onPick}
            role="option" aria-selected={on}>
      <span className="row-mark">{MARK[chapter.state] ?? "·"}</span>
      <span className="row-title">{chapter.title}</span>
      {counts.total
        ? <Progress done={counts.done} total={counts.total} />
        : <span className="row-count dim">not started</span>}
      {actors.length ? (
        <span className="row-who dim">{actors.slice(0, 2).map(short).join(" ")}
          {actors.length > 2 ? ` +${actors.length - 2}` : ""}</span>
      ) : null}
      {/* The one state a machine cannot clear, said as the thing a person has to do. It is worth a
        * line of its own in the menu: nothing new starts under a chapter waiting to be closed. */}
      {chapter.state === "review" ? <span className="row-wait">waiting for a person</span> : null}
    </button>
  );
}

export function Progress({ done, total }: { done: number; total: number }): JSX.Element {
  const percent = total ? Math.round((done / total) * 100) : 0;
  return (
    <span className="progress" aria-label={`${done} of ${total} done`}>
      <span className="bar"><span className="fill" style={{ width: `${percent}%` }} /></span>
      <span className="count">{done}/{total}</span>
    </span>
  );
}

export interface Counted { total: number; done: number; review: number; ready: number; blocked: number }

/* One chapter's counts, folded into the numbers a row can show.
 *
 * SUMMED from the statuses, skipping `total` and `cancelled` — the same rule as `countLine` in
 * `facts.tsx` and for the same reasons: `total` is a key in that map rather than a status, so
 * summing cannot double-count it (a first version did, and one card rendered as "2"), and a
 * withdrawn card is not one of the cards — left in, it makes a finished chapter read as unfinished
 * forever. */
export function countOf(context: ContextView, id: string): Counted {
  const raw = context.counts[id] ?? {};
  const total = Object.entries(raw)
    .filter(([status]) => status !== "cancelled" && status !== "total")
    .reduce((sum, [, n]) => sum + n, 0);
  return {
    total,
    done: raw.done ?? 0,
    review: raw.review ?? 0,
    ready: raw.ready ?? 0,
    blocked: raw.blocked ?? 0,
  };
}

function totalOf(context: ContextView, id: string): number {
  return countOf(context, id).total;
}

/* Which actors are working in which chapter, from the board itself.
 *
 * The LEASE first and the assignee second, the order a card draws them: a lease means somebody is
 * on it right now, an assignment means it is waiting for them. Derived here because the server has
 * no registry of who is where and should not — the board already says it. */
export function whoIsWhere(board: Board | null): Map<string, string[]> {
  const seen = new Map<string, Set<string>>();
  for (const column of board?.columns ?? []) {
    for (const card of column.cards) {
      const who = card.lease?.actor ?? card.task.assignee;
      if (!who) continue;
      const bucket = seen.get(card.task.milestone) ?? new Set<string>();
      bucket.add(who);
      seen.set(card.task.milestone, bucket);
    }
  }
  return new Map([...seen].map(([id, who]) => [id, [...who].sort()]));
}

/* `agent:berna/one` → `berna/one`. The prefix is identical on every row, so printing it is noise
 * in the one place with the least room for any. */
export function short(actor: string): string {
  return actor.includes(":") ? actor.slice(actor.indexOf(":") + 1) : actor;
}

/* Close on a click anywhere else and on Escape. A dropdown that only closes by picking something is
 * a dropdown that traps somebody who opened it to look. */
function useOutside(box: React.RefObject<HTMLDivElement>, close: () => void): void {
  useEffect(() => {
    const onClick = (event: MouseEvent): void => {
      if (box.current && !box.current.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent): void => { if (event.key === "Escape") close(); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [box, close]);
}
